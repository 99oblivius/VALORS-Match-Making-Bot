# VALORS Match Making Bot - Discord based match making automation and management service
# Copyright (C) 2024 99oblivius, <projects@oblivius.dev>
#
# This file is part of VALORS Match Making Bot.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import uuid
from datetime import datetime, timedelta, timezone
from functools import partial
from typing import Any, Dict, List, Tuple
import asyncio
import base64
import re

from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import aiohttp
import unicodedata

from nextcord import Embed, Guild, Role, Interaction, Message, Member, RoleTags

from config import VALORS_THEME1, VALORS_THEME2
from utils.models import MMBotMatchPlayers, MMBotRanks, MMBotMatches, MMBotUserMatchStats, Side, MMBotQueueUsers
from utils.logger import Logger as log

def lerp(a, b, t) -> float:
    return a + (b - a) * t

def format_duration(seconds, short: bool=False):
    intervals = (
        ('days', 86400),
        ('hours', 3600),
        ('minutes', 60),
        ('seconds', 1))
    result = []
    for name, count in intervals:
        value = seconds // count
        seconds -= value * count
        if short:
            if value != 0: result.append(f"{value:.0f}{name[0]}")
        else:
            if value == 1: name = name.rstrip('s')
            if value != 0: result.append(f"{value:.0f} {name}")
    return ' '.join(result) if result else "0 seconds"

def extract_late_time(message: str) -> int:
    if not message.startswith("Late by "):
        return 0
    
    duration_str = message[8:]  # Remove "Late by " prefix
    total_seconds = 0
    parts = duration_str.split()
    
    for i in range(0, len(parts), 2):
        value = int(parts[i])
        unit = parts[i+1].rstrip('s')  # Remove 's' from plural units
        
        if unit == "day":
            total_seconds += value * 86400
        elif unit == "hour":
            total_seconds += value * 3600
        elif unit == "minute":
            total_seconds += value * 60
        elif unit == "second":
            total_seconds += value
    return total_seconds

def get_ratio_color(ratio):
    if ratio >= 0.95:
        return 0x00ff00  # Green
    elif ratio >= 0.80:
        return 0xffff00  # Yellow
    else:
        return 0xff0000  # Red

def get_ratio_interpretation(ratio):
    if ratio >= 0.95:
        return "Excellent punctuality! Keep it up!"
    elif ratio >= 0.80:
        return "Good punctuality, but there's room for improvement."
    else:
        return "Punctuality needs significant improvement."

def add_stats_field(embed, name, stats, is_duration=False):
    value = f"Average: {format_stat(stats['average'], is_duration)}\n"
    value += f"Median: {format_stat(stats['median'], is_duration)}\n"
    value += f"Min: {format_stat(stats['min'], is_duration)}\n"
    value += f"Max: {format_stat(stats['max'], is_duration)}\n"
    value += f"Standard Deviation: {format_stat(stats['std_dev'], is_duration)}"
    embed.add_field(name=name, value=value, inline=False)

def format_stat(value, is_duration):
    if value is None:
        return "N/A"
    if is_duration:
        return format_duration(int(value))
    return f"{value:.0f}"

def format_mm_attendance(users: List[MMBotMatchPlayers]):
    return "\n".join([f"{'🟢' if user.accepted else '🔴'} <@{user.user_id}>" for user in users])

def replace_wide_chars_with_space(text):
    return ''.join(' ' if unicodedata.east_asian_width(char) in ('F', 'W') else char for char in text)

def format_team(team: bool) -> str:
    return 'B' if team else 'A'

def shifted_window(l: list, range: int=1) -> list:
    l = l + l[:range - 1]
    return l[0:range]

def generate_auth_url(cache, guild_id: int, user_id: int, platform: str) -> str:
    token = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    cache.hmset(token, {'guild_id': guild_id, 'discord_uuid': user_id, 'expires_at': expires_at.isoformat(), 'platform': platform})
    cache.expire(token, 300)
    return f"https://api.valorsleague.org/mm-auth/{platform}/{token}"

def abandon_cooldown(count: int, last_abandon: datetime | None=None) -> int:
    if last_abandon is None:
        last_abandon = datetime.now(timezone.utc)
    
    cooldown_end = last_abandon
    if count == 0:
        return 0
    elif count == 1:
        cooldown_end += timedelta(hours=2)
    elif count == 2:
        cooldown_end += timedelta(hours=6)
    elif count == 3:
        cooldown_end += timedelta(days=1)
    else:
        cooldown_end += timedelta(days=3)

    cooldown_seconds = (cooldown_end - datetime.now(timezone.utc)).total_seconds()
    return max(0, int(cooldown_seconds))

def get_rank_role(guild: Guild, ranks: List[MMBotRanks], mmr: int) -> Role:
    ranks = sorted([(r.mmr_threshold, guild.get_role(r.role_id)) for r in ranks], key=lambda x: x[0])
    return next((role for threshold, role in reversed(ranks) if mmr > threshold), None)

def next_rank_role(guild: Guild, ranks: List[MMBotRanks], mmr: int) -> Tuple[Role, int]:
    sorted_ranks = sorted([(r.mmr_threshold, guild.get_role(r.role_id)) for r in ranks], key=lambda x: x[0])
    
    for threshold, role in sorted_ranks:
        if mmr < threshold:
            return role, threshold - mmr
    
    return None, None

def get_rank_color(guild: Guild, mmr: int, ranks: List[MMBotRanks]) -> str:
    def to_rgb(color):
        return ((color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF)

    def euclidean(c1, c2):
        r1, g1, b1 = to_rgb(c1)
        r2, g2, b2 = to_rgb(c2)
        return (r1-r2)**2 + (g1-g2)**2 + (b1-b2)**2

    def closest_color_code(color, target_colors=ANSI_TARGET_COLORS, dist=euclidean):
        return target_colors[min(target_colors, key=partial(dist, color))]

    sorted_ranks = sorted(ranks, key=lambda x: x.mmr_threshold, reverse=True)

    for rank in sorted_ranks:
        if mmr >= rank.mmr_threshold:
            role = guild.get_role(rank.role_id)
            if role and role.color:
                color_code = closest_color_code(role.color.value)
                return f"\u001b[1;{color_code}m"
    
    return "\u001b[1;30m"

def create_queue_embed(queue_users: List[MMBotQueueUsers]) -> Embed:
    queue_users.sort(key=lambda u: u.queue_expiry)
    embed = Embed(title="Queue", color=VALORS_THEME1)
    message_lines = []
    for n, item in enumerate(queue_users, 1):
        message_lines.append(f"{n}. <@{item.user_id}> `expires `<t:{item.queue_expiry}:R>")
    embed.add_field(name=f"{len(queue_users)} in queue", value=f"{'\n'.join(message_lines)}\u2800")
    return embed

async def fetch_avatar(session: aiohttp.ClientSession, cache, url: str, size: tuple):
    cache_key = f'discord_avatar:{sanitize_url_for_redis(url)}'
    cached_avatar = cache.get(cache_key)
    if cached_avatar:
        try:
            image_data = base64.b64decode(cached_avatar)
            image_buffer = BytesIO(image_data)
            image_buffer.seek(0)
            img = Image.open(image_buffer)
            img.load()
            return img
        except Exception as e:
            log.warning(f"Invalid cached avatar for {url}: {repr(e)}")
            cache.delete(cache_key)
    
    try:
        async with session.get(url.split('?')[0]) as resp:
            if resp.status == 200:
                avatar_data = await resp.read()
                try:
                    avatar = Image.open(BytesIO(avatar_data))
                    avatar = avatar.convert('RGBA').resize(size, Image.LANCZOS)
                    
                    buffer = BytesIO()
                    avatar.save(buffer, format="PNG")
                    buffer.seek(0)
                    cache.set(cache_key, base64.b64encode(buffer.getvalue()), ex=86400)  # Cache for 1 day
                    
                    return avatar
                except Exception as e:
                    log.error(f"Failed to process avatar from {url}: {e}")
            else:
                log.error(f"Failed to fetch avatar from {url}. Status: {resp.status}")
    except Exception as e:
        log.error(f"Error fetching avatar from {url}: {e}")
    raise ValueError(f"Failed to fetch avatar from {url}")

def sanitize_url_for_redis(url):
    match = re.search(r'/(\d+)/([a-zA-Z0-9_-]+\.[a-zA-Z0-9]+)', url)
    if match:
        return f"{match.group(1)}:{match.group(2)}"
    return url

async def fetch_all_avatars(cache, guild, players, size):
    async with aiohttp.ClientSession() as session:
        tasks = []
        for player in players:
            member = guild.get_member(player.user_id)
            if member:
                task = fetch_avatar(session, cache, str(member.display_avatar), size)
                tasks.append(task)
        return await asyncio.gather(*tasks)

def create_gradient(width, height, start_color, end_color, horizontal=True):
    base = Image.new('RGBA', (width, height), start_color)
    top = Image.new('RGBA', (width, height), end_color)
    mask = Image.new('L', (width, height))
    mask_data = []
    for y in range(height):
        for x in range(width):
            if horizontal:
                distance = abs(x - width/2) / (width/2)
            else:
                distance = y / height
            mask_data.append(int(255 * distance))
    mask.putdata(mask_data)
    return Image.composite(base, top, mask)

def create_ping_bars(ping):
    img = Image.new('RGBA', (15, 15), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    bar_color = (0, 255, 0, 255) if ping < 50 else (255, 255, 0, 255) if ping < 100 else (255, 0, 0, 255)
    bar_count = 3 if ping < 50 else 2 if ping < 100 else 1
    for i in range(bar_count):
        draw.rectangle([i*5, 15-i*5-5, i*5+3, 15], fill=bar_color)
    return img

async def log_moderation(interaction: Interaction, channel_id: int, title: str, message: str | None=None):
    log_channel = interaction.guild.get_channel(channel_id)
    embed = Embed(title=title, description=message, color=VALORS_THEME2)
    embed.set_author(name=interaction.user.name, icon_url=interaction.user.avatar.url)
    embed.timestamp = datetime.now(timezone.utc)
    await log_channel.send(embed=embed)

async def generate_score_image(cache, guild: Guild, match: MMBotMatches, match_stats: List[MMBotUserMatchStats]):
    width, height = 800, 221
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("assets/fonts/Prime Regular.otf", 18)
        score_font = ImageFont.truetype("assets/fonts/Prime Regular.otf", 32)
        time_font = ImageFont.truetype("assets/fonts/Prime Regular.otf", 14)
        legend_font = ImageFont.truetype("assets/fonts/Prime Regular.otf", 14)
    except IOError:
        font = ImageFont.load_default()
        score_font = ImageFont.load_default()
        time_font = ImageFont.load_default()
        legend_font = ImageFont.load_default()

    header_height = 50
    legend_height = 20  # Height for the legend row
    row_height = 30

    # Create header gradients (emanating from center outwards)
    left_color, right_color = (0, 100, 200, 255), (200, 75, 75, 255)
    header_gradient = create_gradient(width, header_height, (0, 0, 0, 15), (0, 0, 0, 250), horizontal=True)
    img.paste(header_gradient, (0, 0), header_gradient)
    
    # Add color overlays for team colors
    left_overlay = Image.new('RGBA', (width // 2, header_height), left_color[:3] + (100,))
    right_overlay = Image.new('RGBA', (width // 2, header_height), right_color[:3] + (100,))
    img.paste(left_overlay, (0, 0), left_overlay)
    img.paste(right_overlay, (width // 2, 0), right_overlay)

    if match.b_side == Side.CT:
        left_score, right_score = match.b_score, match.a_score
    else:
        left_score, right_score = match.a_score, match.b_score
    
    # Draw scores (spread out from the center)
    draw.text((width // 2 - 30, header_height // 2 + 3), str(left_score), fill=(255, 255, 255, 255), font=score_font, anchor="rm")
    draw.text((width // 2 + 30, header_height // 2 + 3), str(right_score), fill=(255, 255, 255, 255), font=score_font, anchor="lm")

    # Draw match_id and map
    map_name = f'[{match.id}] {match.map}'
    map_rect = draw.textbbox((header_height // 2, header_height // 2), map_name, font=font, anchor="lm")
    draw.rectangle((map_rect[0]-5, map_rect[1]-3, map_rect[2]+5, map_rect[3]+3), fill=(0, 0, 0, 128))    
    draw.text((header_height // 2, header_height // 2), map_name, fill=(255, 255, 255, 255), font=font, anchor="lm")

    # Draw timer
    if match.end_timestamp:
        duration = match.end_timestamp - match.start_timestamp
        minutes, seconds = divmod(duration.seconds, 60)
        timer_text = f"{minutes:02d}:{seconds:02d}"
        time_rect = draw.textbbox((width - header_height // 2 - 5, header_height // 2), timer_text, font=time_font, anchor="mm")
        draw.rectangle((time_rect[0]-5, time_rect[1]-3, time_rect[2]+5, time_rect[3]+3), fill=(0, 0, 0, 128))
        draw.text((width - header_height // 2 - 5, header_height // 2), timer_text, fill=(255, 255, 255, 255), font=time_font, anchor="mm")

    # Draw legend row
    legend_y = header_height
    legend_color = (0, 0, 0, 200)  # Semi-transparent black
    draw.rectangle([(0, legend_y), (width, legend_y + legend_height)], fill=legend_color)

    # Draw legend text
    legend_texts = ["S", "D", "K"]
    for side in range(2):  # 0 for left side, 1 for right side
        x = width // 2 - 45 if side == 0 else width - 45
        for text in legend_texts:
            draw.text((x, legend_y + legend_height // 2), text, fill=(200, 200, 200, 255), font=legend_font, anchor="rm")
            x -= 40

    # Sort players by score
    team_a = sorted([s for s in match_stats if s.ct_start], key=lambda x: x.score, reverse=True)
    team_b = sorted([s for s in match_stats if not s.ct_start], key=lambda x: x.score, reverse=True)

    # Fetch all avatars concurrently
    avatar_size = (row_height - 2, row_height - 2)
    team_a_avatars = await fetch_all_avatars(cache, guild, team_a, avatar_size)
    team_b_avatars = await fetch_all_avatars(cache, guild, team_b, avatar_size)

    # Create large gradients for rows
    left_gradient = create_gradient(width, height, (*left_color[:3], 220), (*left_color[:3], 5))
    right_gradient = create_gradient(width, height, (*right_color[:3], 220), (*right_color[:3], 5))

    def draw_team(team, avatars, start_x, is_right_aligned):
        y = header_height + legend_height  # Start below the legend row
        gradient = right_gradient if is_right_aligned else left_gradient
        for i, (stats, avatar) in enumerate(zip(team, avatars)):
            # Draw row background
            row_mask = Image.new('L', (width // 2, row_height), 255)
            img.paste(gradient.crop(
                (0, y - header_height, width // 2, y - header_height + row_height)), 
                      (start_x, y), row_mask)

            # Draw thin colored lines
            line_color = right_color if is_right_aligned else left_color
            draw.line([(start_x, y), (start_x + width//2, y)], fill=line_color, width=1)
            draw.line([(start_x, y + row_height), (start_x + width//2, y + row_height)], fill=line_color, width=1)

            member = guild.get_member(stats.user_id)
            if member:
                if avatar:
                    avatar_x = start_x + (2 if is_right_aligned else 5)
                    img.paste(avatar, (avatar_x, y + 2), avatar)

                text_color = (255, 255, 255, 255)
                name_x = start_x + row_height + 6
                draw.text((name_x, y + row_height // 2), member.display_name[:16], fill=text_color, font=font, anchor="lm")

                stats_x = start_x + width // 2 - 45
                for stat_text in (stats.score, stats.deaths, stats.kills):
                    draw.text((stats_x, y + row_height // 2), f'{stat_text}', fill=text_color, font=font, anchor="rm")
                    stats_x -= 40

                # Draw ping bars
                ping_bars = create_ping_bars(stats.ping)
                ping_x = start_x + (width // 2 - 20 if is_right_aligned else width // 2 - 20)
                img.paste(ping_bars, (ping_x, y + row_height // 2 - 7), ping_bars)

            y += row_height

    draw_team(team_a, team_a_avatars, 0, False)
    draw_team(team_b, team_b_avatars, width // 2, True)

    # Draw color center lines
    draw.line([(width // 2 - 2, header_height), (width // 2 - 2, height)], fill=left_color, width=2)
    draw.line([(width // 2, header_height), (width // 2, height)], fill=right_color, width=2)

    img_byte_arr = BytesIO()
    img.save(img_byte_arr, format='PNG')
    return img_byte_arr.getvalue()

def generate_score_text(guild: Guild, persistent_stats: Dict[int, Dict[str, Any]]):
    scores = "```ansi\n"
    header = "CT         |   K/D/S  | T         |   K/D/S "
    scores += f"\u001b[1m{header}\u001b[0m\n{'─' * len(header)}\n"
    
    def name_formatted(user_id):
        member = guild.get_member(user_id)
        if not member: return " "*10
        name = member.display_name
        return (name[:10] + '…' if len(name) > 11 else name).ljust(11)
    
    def kda_formatted(stats):
        return f"{stats['kills']}/{stats['deaths']}/{stats['score']}".rjust(8)
    
    scores += '\n'.join(
        f" \u001b[1;34m{name_formatted(team_a['user_id'])} \u001b[0m{kda_formatted(team_a)} | \u001b[1;31m{name_formatted(team_b['user_id'])} \u001b[0m{kda_formatted(team_b)}"
        for team_a, team_b in zip(
            sorted([stats | {"user_id": user_id} for user_id, stats in persistent_stats.items() if stats['ct_start']], key=lambda x: x['score'], reverse=True), 
            sorted([stats | {"user_id": user_id} for user_id, stats in persistent_stats.items() if not stats['ct_start']], key=lambda x: x['score'], reverse=True)))
    return scores + "```"


ANSI_TARGET_COLORS = {
    0x4E5057: "30",
    0xC34139: "31",
    0x88972E: "32",
    # 0xAE8B2D: "33",
    0x4689CC: "34",
    0xC24480: "35",
    # 0x519F98: "36",
    # 0xFFFFFF: "37",

    # 0x0F2C37: "40;30",
    0x9A4D2D: "41;30",
    0x4D6169: "42:30",
    0x586B74: "43:30",
    0x6F8085: "44:30",
    0x5C65A5: "45:30",
    0x79888B: "46:30",
    0xD5D5C9: "47:30",

    0x302E35: "40;31",
    # 0xBE502C: "41;31",
    0x716468: "42;31",
    0x7A6F74: "43;31",
    0x928384: "44;31",
    0x7F67A3: "45;31",
    0xA28B89: "46;31",
    0xF3D5C6: "47;31",

    0x274033: "40;32",
    0xB0632A: "41;32",
    0x667664: "42;32",
    0x6F7F6E: "43;32",
    # 0x86947E: "44;32",
    0x7279A0: "45;32",
    # 0x929E87: "46;32",
    0xE5E3C1: "47;32",

    0x2D3C33: "40;33",
    0xB95F29: "41;33",
    0x6C7266: "42;33",
    0x767D71: "43;33",
    # 0x8E9180: "44;33",
    0x7A76A0: "45;33",
    0x9B9C88: "46;33",
    0xEADEBC: "47;33",

    0x1A3F56: "40;34",
    0xA35E4A: "41;34",
    0x577285: "42;34",
    # 0x607D93: "43;34",
    0x7690A2: "44;34",
    0x6476C1: "45;34",
    0x839BAA: "46;34",
    0xD7DFDF: "47;34",

    0x342F45: "40;35",
    # 0xBD503B: "41;35",
    0x6F6475: "42;35",
    0x7A6F81: "43;35",
    0x928291: "44;35",
    0x7F67B0: "45;35",
    0xA08998: "46;35",
    0xF0D3D1: "47;35",

    0x1B4048: "40;36",
    0xA5633F: "41;36",
    0x59777B: "42;36",
    0x648186: "43;36",
    # 0x799596: "44;36",
    0x667BB5: "45;36",
    0x88A09F: "46;36",
    0xDAE4D5: "47;36",

    0x384D53: "40;37",
    0xC5714B: "41;37",
    0x788487: "42;37",
    0x859194: "43;37",
    0x9CA5A4: "44;37",
    0x8487C2: "45;37",
    0xA8B0AC: "46;37",
    # 0xF8F3E2: "47;37",
}

def get_message_data(message: Message) -> dict:
    try:
        user = {
            "avatar": {
                "key": message.author.avatar.key,
                "url": message.author.avatar.url
            } if message.author.avatar else {},
            "bot": message.author.bot,
            "display_name": message.author.display_name,
            "global_name": message.author.global_name,
            "name": message.author.name
        }
        if isinstance(message.author, Member):
            user |= {
                "accent_color": message.author.accent_color,
                "banner": {
                    "key": message.author.banner.key,
                    "url": message.author.banner.url
                } if message.author.banner else {},
                "color": {
                    "r": message.author.color.r,
                    "g": message.author.color.g,
                    "b": message.author.color.b,
                    "value": message.author.color.value,
                },
                "created_at": str(message.author.created_at),
                "default_avatar": {
                    "key": message.author.default_avatar.key,
                    "url": message.author.default_avatar.url
                } if message.author.default_avatar else {},
                "display_avatar": {
                    "key": message.author.display_avatar.key,
                    "url": message.author.display_avatar.url
                } if message.author.display_avatar else {},
                "display_banner": {
                    "key": message.author.display_banner.key,
                    "url": message.author.display_banner.url
                } if message.author.display_banner else {},
                "guild_avatar": {
                    "key": message.author.guild_avatar.key,
                    "url": message.author.guild_avatar.url
                } if message.author.guild_avatar else {},
                "guild_banner": {
                    "key": message.author.guild_banner.key,
                    "url": message.author.guild_banner.url
                } if message.author.guild_banner else {},
                "guild_permissions": {
                    "value": message.author.guild_permissions.value
                },
                "id": message.author.id,
                "joined_at": str(joined_at) if (joined_at := message.author.joined_at) else None,
                "nick": message.author.nick,
                "premium_since": str(premium_since) if (premium_since := message.author.premium_since) else None,
                "public_flags": {
                    "value": message.author.public_flags.value
                },
                "raw_status": message.author.raw_status,
                "roles": [{
                    "color": {
                        "r": role.color.r,
                        "g": role.color.g,
                        "b": role.color.b,
                        "value": role.color.value
                    },
                    "created_at": str(role.created_at),
                    "hoist": role.hoist,
                    "icon": role.icon if isinstance(role.icon, str) else None if role.icon is None else {
                        "key": role.icon.key,
                        "url": role.icon.url
                    },
                    "id": role.id,
                    "managed": role.managed,
                    "mentionable": role.mentionable,
                    "name": role.name,
                    "permissions": {
                        "value": role.permissions.value
                    },
                    "position": role.position,
                    "tags": {
                        "bot_id": tags.bot_id if (tags := role.tags) else None,
                        "integration_id": tags.integration_id if (tags := role.tags) else None,
                        "subscription_listing_id": tags.subscription_listing_id if (tags := role.tags) else None
                    } if isinstance(role.tags, RoleTags) else None
                } for role in message.author.roles],
                "status": str(message.author.status),
                "system": message.author.system,
                "top_role": {
                    "color": {
                        "r": message.author.top_role.color.r,
                        "g": message.author.top_role.color.g,
                        "b": message.author.top_role.color.b,
                        "value": message.author.top_role.color.value
                    },
                    "created_at": str(message.author.top_role.created_at),
                    "hoist": message.author.top_role.hoist,
                    "icon": message.author.top_role.icon if isinstance(message.author.top_role.icon, str) else None if message.author.top_role.icon is None else {
                        "key": message.author.top_role.icon.key,
                        "url": message.author.top_role.icon.url
                    },
                    "id": message.author.top_role.id,
                    "managed": message.author.top_role.managed,
                    "mentionable": message.author.top_role.mentionable,
                    "name": message.author.top_role.name,
                    "permissions": {
                        "value": message.author.top_role.permissions.value
                    },
                    "position": message.author.top_role.position,
                    "tags": {
                        "bot_id": message.author.top_role.tags.bot_id,
                        "integration_id": message.author.top_role.tags.integration_id,
                        "subscription_listing_id": message.author.top_role.tags.subscription_listing_id
                    } if message.author.top_role.tags else None
                }
            }
        return {
            "attachments": [{
                "content_type": att.content_type,
                "description": att.description,
                "filename": att.filename,
                "height": att.height,
                "id": att.id,
                "proxy_url": att.proxy_url,
                "size": att.size,
                "url": att.url,
                "width": att.width
            } for att in message.attachments],
            "author": user,
            "clean_content": message.clean_content,
            "content": message.content,
            "created_at": str(message.created_at),
            "edited_at": str(edited_at) if (edited_at := message.edited_at) else None,
            "embeds": [{
                "author": {
                    "name": embed.author.name,
                    "url": embed.author.url,
                    "icon_url": embed.author.icon_url
                },
                "color": {
                    "r": color.r,
                    "g": color.g,
                    "b": color.b,
                    "value": color.value
                } if (color := embed.color) else None,
                "description": embed.description,
                "fields": [{
                    "name": field.name,
                    "value": field.value,
                    "inline": field.inline
                } for field in embed.fields],
                "footer": {
                    "text": embed.footer.text,
                    "icon_url": embed.footer.icon_url
                },
                "image": {
                    "url": embed.image.url,
                    "proxy_url": embed.image.proxy_url,
                    "width": embed.image.width,
                    "height": embed.image.height
                },
                "provider": {
                    "name": embed.provider.name,
                    "url": embed.provider.url
                },
                "thumbnail": {
                    "url": embed.thumbnail.url,
                    "proxy_url": embed.thumbnail.proxy_url,
                    "width": embed.thumbnail.width,
                    "height": embed.thumbnail.height
                },
                "timestamp": str(embed.timestamp),
                "title": embed.title,
                "type": embed.type,
                "url": embed.url,
                "video": {
                    "url": embed.video.url,
                    "height": embed.video.height,
                    "width": embed.video.width
                }
            } for embed in message.embeds],
            "flags": {
                "value": message.flags.value
            },
            "id": message.id,
            "interaction_metadata": {
                "authorizing_integration_owners": message.interaction_metadata.authorizing_integration_owners,
                "created_at": message.interaction_metadata.created_at,
                "data": message.interaction_metadata.data,
                "id": message.interaction_metadata.id,
                "interacted_message_id": message.interaction_metadata.interacted_message_id,
                "name": message.interaction_metadata.name,
                "original_response_message_id": message.interaction_metadata.original_response_message_id,
                "triggering_interaction_metadata": message.interaction_metadata.triggering_interaction_metadata,
                "type": message.interaction_metadata.type,
                "user": {
                    "display_avatar": {
                        "key": message.interaction_metadata.user.display_avatar.key,
                        "url": message.interaction_metadata.user.display_avatar.url
                    },
                    "id": message.interaction_metadata.user.id,
                    "display_name": message.interaction_metadata.user.display_name
                }
            } if message.interaction_metadata else None,
            "reactions": [{
                "count": reaction.count,
                "emoji": reaction.emoji if isinstance(reaction.emoji, str) else {
                    "name": reaction.emoji.name,
                    "url": reaction.emoji.url,
                    "created_at": str(reaction.emoji.created_at),
                    "id": reaction.emoji.id
                }
            } for reaction in message.reactions],
            "stickers": [{
                "format": str(sticker.format),
                "id": sticker.id,
                "name": sticker.name,
                "url": sticker.url
            } for sticker in message.stickers],
            "type": {
                "valu": message.type.value
            }
        }
    except Exception as e:
        log.error(f"Error in get_message_data(): {repr(e)}")
        raise Exception(f"Error in get_message_data(): {repr(e)}")
