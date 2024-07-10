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
from math import floor
from typing import Any, Dict, List

import io
from PIL import Image, ImageDraw, ImageFont
import aiohttp

from nextcord import Embed, Guild, Member, User

from config import VALORS_THEME1
from utils.models import MMBotMatchPlayers, MMBotRanks, MMBotMatches, MMBotUserMatchStats, Side


def format_duration(seconds):
    intervals = (
        ('days', 86400),
        ('hours', 3600),
        ('minutes', 60),
        ('seconds', 1))
    result = []
    for name, count in intervals:
        value = seconds // count
        seconds -= value * count
        if value == 1: name = name.rstrip('s')
        if value != 0: result.append(f"{value} {name}")
    return ' '.join(result) if result else "0 seconds"

def format_mm_attendance(users: List[MMBotMatchPlayers]):
    return "\n".join([f"{'🟢' if user.accepted else '🔴'} <@{user.user_id}>" for user in users])

def format_team(team: bool) -> str:
    return 'B' if team else 'A'

def shifted_window(l: list, phase: int=0, range: int=1) -> list:
    l = l + l[:range - 1]
    return l[phase:phase + range]

def generate_auth_url(cache, guild_id: int, user_id: int, platform: str) -> str:
    token = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    cache.hmset(token, {'guild_id': guild_id, 'discord_uuid': user_id, 'expires_at': expires_at.isoformat(), 'platform': platform})
    cache.expire(token, 300)
    return f"https://valorsbotapi.oblivius.dev/auth/{platform}/{token}"

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

def create_leaderboard_embed(guild: Guild, leaderboard_data: List[Dict[str, Any]], last_mmr: Dict[int, int], ranks: List[MMBotRanks]) -> Embed:
    field_count = 0

    valid_scores = [player['avg_score'] for player in leaderboard_data if player['games'] > 0 and guild.get_member(player['user_id'])]
    avg_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0
    embed = Embed(title="Match Making Leaderboard", description=f"{len(valid_scores)} ranking players\nK/D/A and Score are mean averages")

    ranked_mmr = ((n, user_id) for n, (user_id, _) in enumerate(sorted(last_mmr.items(), key=lambda x: x[1], reverse=True), 1))
    previous_positions = { user_id: n for n, user_id in ranked_mmr if guild.get_member(user_id) }

    ranking_position = 0
    for player in leaderboard_data:
        if field_count > 25: break
        if player['games'] == 0: continue

        member = guild.get_member(player['user_id'])
        if member is None: continue
        
        ranking_position += 1

        previous_position = previous_positions.get(player['user_id'], None)
        if previous_position is None:               rank_change = "\u001b[35m·"
        elif ranking_position < previous_position:  rank_change = "\u001b[32m↑"
        elif ranking_position > previous_position:  rank_change = "\u001b[31m↓"
        else:                                       rank_change = "\u001b[36m|"

        name = member.display_name[:11] + '…' if len(member.display_name) > 12 else member.display_name
        name = name.ljust(12)
        mmr = f"{floor(player['mmr'])}".rjust(4)
        games = f"{player['games']}".rjust(3)
        win_rate = floor(player['win_rate']*100)
        k = floor(player['avg_kills'])
        d = floor(player['avg_deaths'])
        a = floor(player['avg_assists'])
        score = floor(player['avg_score'])
        
        # Color coding
        rank_color = get_rank_color(guild, float(mmr), ranks)
        win_rate_color = "\u001b[32m" if win_rate > 60 else "\u001b[31m" if win_rate < 40 else "\u001b[0m"
        score_color = "\u001b[32m" if score > avg_score else "\u001b[31m"
        
        kda = f"{k}/{d}/{a}".rjust(8)
        if k < d:
            kda_formatted = kda.replace(str(d), f"\u001b[31m{d}\u001b[0m", 1)
        else:
            kda_formatted = kda

        row = f"{ranking_position:3} {rank_change}\u001b[0m {name} | {rank_color}{mmr}\u001b[0m | {games} | {win_rate_color}{win_rate:3}%\u001b[0m | {kda_formatted} | {score_color}{score:2}\u001b[0m\n"
        
        if ranking_position % 5 == 1:
            if ranking_position == 1:
                header = "  R | Player       |  MMR |   G |  W%  |   K/D/A  | S  "
                field_content = f"```ansi\n\u001b[1m{header}\u001b[0m\n{'─' * len(header)}\n{row}"
            else:
                field_content += "```"
                embed.add_field(name="\u200b", value=field_content, inline=False)
                field_content = f"```ansi\n{row}"
            field_count += 1
        else:
            field_content += row
    if field_content:
        field_content += "```"
        embed.add_field(name="\u200b", value=field_content, inline=False)
    
    return embed

async def generate_score_image(guild: Guild, match: MMBotMatches, match_stats: List[MMBotUserMatchStats]):
    width, height = 800, 600
    background_color = (20, 20, 20, 200)
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    overlay = Image.new('RGBA', (width, height), background_color)
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype("assets/fonts/Prime Regular.otf", 20)

    if match.b_side == Side.T:
        left_score, right_score = match.b_score, match.a_score
    else:
        left_score, right_score = match.a_score, match.b_score
    
    draw.text((width // 4, 10), str(left_score), fill=(100, 200, 255, 255), font=font, anchor="mt")
    draw.text((3 * width // 4, 10), str(right_score), fill=(255, 100, 100, 255), font=font, anchor="mt")

    draw.line([(width // 2, 0), (width // 2, height)], fill=(200, 200, 200, 255), width=2)

    if match.end_timestamp:
        duration = match.end_timestamp - match.start_timestamp
        minutes, seconds = divmod(duration.seconds, 60)
        timer_text = f"{minutes:02d}:{seconds:02d}"
        draw.text((width // 2, 10), timer_text, fill=(255, 255, 255, 255), font=font, anchor="mt")

    match_stats.sort(key=lambda x: x.score, reverse=True)

    async def draw_player(stats, x, y, is_red_team):
        member = guild.get_member(stats.user_id)
        if member:
            async with aiohttp.ClientSession() as session:
                async with session.get(str(member.display_avatar)) as resp:
                    if resp.status == 200:
                        avatar_data = await resp.read()
                        avatar = Image.open(io.BytesIO(avatar_data)).resize((40, 40)).convert('RGBA')
                        img.paste(avatar, (x, y), avatar)

            name = member.display_name
            color = (255, 100, 100, 255) if is_red_team else (100, 200, 255, 255)
            draw.text((x + 50, y), name, fill=color, font=font)
            stats_text = f"{stats.score} {stats.kills} {stats.deaths} {stats.assists}"
            draw.text((x + 250, y), stats_text, fill=(255, 255, 255, 255), font=font)

    y_offset = 50
    for stats in match_stats:
        if stats.ct_start:
            await draw_player(stats, width // 2 + 10, y_offset, True)
        else:
            await draw_player(stats, 10, y_offset, False)
        y_offset += 50

    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr = img_byte_arr.getvalue()

    return img_byte_arr

def create_stats_embed(guild: Guild, user: User | Member, leaderboard_data, summary_data, avg_stats, recent_matches) -> Embed:
    ranked_players = 0
    ranked_position = None
    for player in leaderboard_data:
        if player['games'] > 0 and guild.get_member(player['user_id']):
            ranked_players += 1
        if player['user_id'] == user.id:
            ranked_position = ranked_players
    embed = Embed(title=f"[{ranked_position}/{ranked_players}] Stats for {user.display_name}", color=VALORS_THEME1)
    embed.set_thumbnail(url=user.avatar.url if user.avatar else user.default_avatar.url)

    embed.add_field(name="MMR", value=f"{summary_data.mmr:.2f}", inline=True)
    embed.add_field(name="Total Games", value=summary_data.games, inline=True)
    embed.add_field(name="Win Rate", value=f"{(summary_data.wins / summary_data.games * 100):.2f}%" if summary_data.games > 0 else "N/A", inline=True)
    embed.add_field(name="Total Kills", value=summary_data.total_kills, inline=True)
    embed.add_field(name="Total Deaths", value=summary_data.total_deaths, inline=True)
    embed.add_field(name="Total Assists", value=summary_data.total_assists, inline=True)
    embed.add_field(name="K/D Ratio", value=f"{(summary_data.total_kills / summary_data.total_deaths):.2f}" if summary_data.total_deaths > 0 else "N/A", inline=True)
    embed.add_field(name="Total Score", value=f"{(summary_data.total_score / summary_data.games):.2f}" if summary_data.games > 0 else "N/A", inline=True)

    if avg_stats:
        embed.add_field(name="\u200b", value="Average Performance (Last 10 Games)", inline=False)
        embed.add_field(name="Kills", value=f"{f'{avg_stats['avg_kills']:.2f}' if avg_stats.get('avg_kills', None) else 'N/A'}", inline=True)
        embed.add_field(name="Deaths", value=f"{f'{avg_stats['avg_deaths']:.2f}' if avg_stats.get('avg_deaths', None) else 'N/A'}", inline=True)
        embed.add_field(name="Assists", value=f"{f'{avg_stats['avg_assists']:.2f}' if avg_stats.get('avg_assists', None) else 'N/A'}", inline=True)
        embed.add_field(name="Score", value=f"{f'{avg_stats['avg_score']:.2f}' if avg_stats.get('avg_score', None) else 'N/A'}", inline=True)
        embed.add_field(name="MMR Gain", value=f"{f'{avg_stats['avg_mmr_change']:.2f}' if avg_stats.get('avg_mmr_change', None) else 'N/A'}", inline=True)
    else:
        embed.add_field(name="Recent Performance", value="No recent matches found", inline=False)

    if recent_matches:
        recent_matches_str = "\n".join([f"{'W' if match.win else 'L'} | K: {match.kills} | D: {match.deaths} | A: {match.assists} | MMR: {match.mmr_change:+.2f}" for match in recent_matches])
        embed.add_field(name="Recent Matches", value=f"```{recent_matches_str}```", inline=False)
    else:
        embed.add_field(name="Recent Matches", value="No recent matches found", inline=False)
    
    return embed


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