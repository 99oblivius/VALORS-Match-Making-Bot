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

import asyncio
import json
from datetime import datetime, timezone
from typing import Dict

import nextcord
from nextcord.ext import commands

from config import GUILD_ID, LFG_PING_DELAY, MATCH_PLAYER_COUNT, VALORS_THEME1, VALORS_THEME1_2
from matches import make_match
from utils.logger import Logger as log
from utils.utils import abandon_cooldown, format_duration, create_queue_embed
from utils.statistics import create_stats_embed


class QueueButtonsView(nextcord.ui.View):
    def __init__(self, bot: commands.Bot, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.ready_lock: Dict[asyncio.Lock] = {}

    @classmethod
    def create_dummy_persistent(cls, bot: commands.Bot):
        instance = cls(bot, timeout=None)
        for slot_id in range(15):
            button = nextcord.ui.Button(label="dummy button", custom_id=f"mm_queue_button:ready:{slot_id}")
            button.callback = instance.ready_callback
            instance.add_item(button)
        
        button = nextcord.ui.Button(label="Unready", custom_id=f"mm_queue_button:unready")
        button.callback = instance.unready_callback
        instance.add_item(button)
    
        button = nextcord.ui.Button(label="Stats", custom_id=f"mm_queue_button:stats")
        button.callback = instance.stats_callback
        instance.add_item(button)
    
        button = nextcord.ui.Button(label="lfg", custom_id=f"mm_queue_button:lfg")
        button.callback = instance.lfg_callback
        instance.add_item(button)
    
        button = nextcord.ui.Button(label="Toggle lfg", custom_id=f"mm_queue_button:toggle_lfg")
        button.callback = instance.toggle_lfg_callback
        instance.add_item(button)

        return instance
    
    @classmethod
    async def create_showable(cls, bot: commands.Bot):
        instance = cls(bot, timeout=None)
        instance.stop()
        settings = await bot.store.get_settings(GUILD_ID)
        periods = json.loads(settings.mm_queue_periods)
        
        # row may never be above 4
        # set_mm_queue_periods() in queues/cog.py must not allow more than 25 minus non-period buttons
        row = 0
        for n, label in enumerate(periods.keys()):
            button = nextcord.ui.Button(
                label=f"{label}", 
                row=row,
                style=nextcord.ButtonStyle.green, 
                custom_id=f"mm_queue_button:ready:{n}")
            if (n+1) % 5 == 0:
                row += 1
            instance.add_item(button)
        
        button = nextcord.ui.Button(
            label="Unready", 
            style=nextcord.ButtonStyle.red, 
            custom_id=f"mm_queue_button:unready")
        instance.add_item(button)

        row += 1
    
        button = nextcord.ui.Button(
            label="Stats", 
            row=row,
            style=nextcord.ButtonStyle.blurple, 
            custom_id=f"mm_queue_button:stats")
        instance.add_item(button)
    
        button = nextcord.ui.Button(
            label="lfg", 
            row=row,
            style=nextcord.ButtonStyle.blurple, 
            custom_id=f"mm_queue_button:lfg")
        instance.add_item(button)

        button = nextcord.ui.Button(
            label="Toggle lfg", 
            row=row,
            style=nextcord.ButtonStyle.grey, 
            custom_id=f"mm_queue_button:toggle_lfg")
        instance.add_item(button)

        return instance

    async def update_queue_message(self, interaction: nextcord.Interaction):
        queue_users = await self.bot.store.get_queue_users(interaction.channel.id)
        asyncio.create_task(self.bot.queue_manager.update_presence(len(queue_users)))
        embed = create_queue_embed(queue_users)
        await interaction.edit(embeds=[interaction.message.embeds[0], embed])

    async def ready_callback(self, interaction: nextcord.Interaction):
        lock_id = f'{interaction.channel.id}'
        if lock_id not in self.ready_lock:
            self.ready_lock[lock_id] = asyncio.Lock()
        
        settings = await self.bot.store.get_settings(interaction.guild.id)
        user_platforms = await self.bot.store.get_user_platforms(interaction.guild.id, interaction.user.id)
        if not user_platforms:
            return await interaction.response.send_message(
                "Verify with at least one platform.", ephemeral=True)
        
        in_queue = False
        if not settings: return await interaction.response.send_message(
            "Settings not found.", ephemeral=True)
        
        user = await self.bot.store.get_user(interaction.guild.id, interaction.user.id)
        if not user: return await interaction.response.send_message(
            "You are not registered.", ephemeral=True)
        if not user.region: return await interaction.response.send_message(
            "You must select your region.", ephemeral=True)
        
        blocked_users = await self.bot.store.get_user_blocks(interaction.guild.id)
        blocked_user = next((u for u in blocked_users if u.user_id == user.user_id), None)
        if blocked_user:
            return await interaction.response.send_message(
                f"You will be unblocked from this queue <t:{int(blocked_user.expiration.timestamp())}:R>", ephemeral=True)
        
        in_match = await self.bot.store.is_user_in_match(interaction.user.id)
        if in_match:
            msg = await interaction.response.send_message(
            "Your current match has not ended yet.", ephemeral=True)
            await asyncio.sleep(1.5)
            return await msg.delete()
        previous_abandons, last_abandon = await self.bot.store.get_abandon_count_last_period(interaction.guild.id, interaction.user.id)
        cooldown = abandon_cooldown(previous_abandons, last_abandon)
        if cooldown > 0:
            embed = nextcord.Embed(
                title="You are on cooldown due to abandoning a match",
                description=f"You can queue again in `{format_duration(cooldown)}`",
                color=VALORS_THEME1_2)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        slot_id = int(interaction.data['custom_id'].split(':')[-1])
        periods = list(json.loads(settings.mm_queue_periods).items())
        expiry = int(datetime.now(timezone.utc).timestamp()) + 60 * int(periods[slot_id][1])
        
        async with self.ready_lock[f'{interaction.channel.id}']:
            queue_users = await self.bot.store.get_queue_users(interaction.channel.id)
            total_in_queue = len(queue_users)
            if total_in_queue + 1 > MATCH_PLAYER_COUNT:
                log.info(f"{interaction.user.display_name} wanted to queue but was overtaken")
                return await interaction.response.send_message("Someone else just got in.\nBetter luck next time", ephemeral=True)
            self.bot.queue_manager.add_user(interaction.user.id, expiry)
            in_queue = await self.bot.store.upsert_queue_user(
                user_id=interaction.user.id, 
                guild_id=interaction.guild.id, 
                queue_channel=interaction.channel.id, 
                queue_expiry=expiry)
            if not in_queue:
                total_in_queue += 1
                asyncio.create_task(self.bot.queue_manager.notify_queue_count(interaction.guild.id, settings, total_in_queue))
            log.info(f"{interaction.user.display_name} has queued up")
            
            if total_in_queue == MATCH_PLAYER_COUNT:
                self.bot.queue_manager.remove_user(interaction.user.id)
                for user in queue_users: self.bot.queue_manager.remove_user(user.user_id)

                match_id = await self.bot.store.unqueue_add_match_users(settings, interaction.channel.id)
                await self.update_queue_message(interaction)
                loop = asyncio.get_event_loop()
                make_match(loop, self.bot, interaction.guild.id, match_id)
                return
        await self.update_queue_message(interaction)
    
    async def unready_callback(self, interaction: nextcord.Interaction):
        if not await self.bot.store.in_queue(interaction.guild.id, interaction.user.id):
            return await interaction.response.send_message("You are not queued up",ephemeral=True)
        self.bot.queue_manager.remove_user(interaction.user.id)
        await self.bot.store.unqueue_user(interaction.channel.id, interaction.user.id)
        log.info(f"{interaction.user.display_name} has left queue")
        await self.update_queue_message(interaction)
    
    async def stats_callback(self, interaction: nextcord.Interaction):
        user = interaction.user
        summary_stats = await self.bot.store.get_user_summary_stats(interaction.guild.id, user.id)
        if not summary_stats:
            return await interaction.response.send_message(f"No stats found for {user.mention}.", ephemeral=True)

        recent_matches = await self.bot.store.get_recent_match_stats(interaction.guild.id, user.id, 10)
        avg_stats = await self.bot.store.get_avg_stats_last_n_games(interaction.guild.id, user.id, 10)
        leaderboard = await self.bot.store.get_leaderboard(interaction.guild.id)
        ranks = await self.bot.store.get_ranks(interaction.guild.id)
        embed = create_stats_embed(interaction.guild, interaction.user, leaderboard, summary_stats, avg_stats, recent_matches, ranks)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def lfg_callback(self, interaction: nextcord.Interaction):
        if not await self.bot.store.in_queue(interaction.guild.id, interaction.user.id):
            return await interaction.response.send_message("You must be in queue to ping",ephemeral=True)
        
        settings = await self.bot.store.get_settings(interaction.guild.id)
        if not settings.mm_lfg_role:
            return await interaction.response.send_message(f"lfg_role not set. Set it with {await self.bot.command_cache.get_command_mention(interaction.guild.id, 'queue settings lfg_role')}", ephemeral=True)
        
        channel = interaction.guild.get_channel(settings.mm_text_channel)
        if not channel:
            return await interaction.response.send_message(f"Queue channel not set. Set it with {await self.bot.command_cache.get_command_mention(interaction.guild.id, 'queue settings set_queue')}", ephemeral=True)
        
        if interaction.guild.id in self.bot.last_lfg_ping:
            if (int(datetime.now(timezone.utc).timestamp()) - LFG_PING_DELAY) < self.bot.last_lfg_ping[interaction.guild.id]:
                return await interaction.response.send_message(
f"""A ping was already sent <t:{self.bot.last_lfg_ping[interaction.guild.id]}:R>.
Try again <t:{self.bot.last_lfg_ping[interaction.guild.id] + LFG_PING_DELAY}:R>""", ephemeral=True)
            log.info(f"{interaction.user.display_name} wanted to ping LFG role")
        
        self.bot.last_lfg_ping[interaction.guild.id] = int(datetime.now(timezone.utc).timestamp())
        await channel.send(f"All <@&{settings.mm_lfg_role}> members are being summoned by {interaction.user.mention}", allowed_mentions=nextcord.AllowedMentions(roles=True, users=False))
        log.info(f"{interaction.user.display_name} pinged LFG role")
        embed = nextcord.Embed(title="LookingForGame members pinged!", color=VALORS_THEME1)
        msg = await interaction.response.send_message(embed=embed, ephemeral=True)
        await asyncio.sleep(5)
        await msg.delete()

    async def toggle_lfg_callback(self, interaction: nextcord.Interaction):
        settings = await self.bot.store.get_settings(interaction.guild.id)
        if not settings.mm_lfg_role:
            return await interaction.response.send_message(f"lfg_role not set. Set it with {await self.bot.command_cache.get_command_mention(interaction.guild.id, 'queue settings lfg_role')}", ephemeral=True)
    
        lfg_role = interaction.guild.get_role(settings.mm_lfg_role)
        if not lfg_role:
            return await interaction.response.send_message("LFG Role is missing. Reach out to staff", ephemeral=True)
        
        if lfg_role in interaction.user.roles:
            await interaction.user.remove_roles(lfg_role)
            log.info(f"{interaction.user.display_name} lost LFG role")
            return await interaction.response.send_message(f"\\- You removed {lfg_role.mention} from yourself", ephemeral=True)
        await interaction.user.add_roles(lfg_role)
        log.info(f"{interaction.user.display_name} gained LFG role")
        await interaction.response.send_message(f"+ You added {lfg_role.mention} to yourself", ephemeral=True)
