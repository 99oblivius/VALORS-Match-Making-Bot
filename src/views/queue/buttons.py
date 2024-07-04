import json
from datetime import datetime, timezone
import asyncio
from typing import Dict
from utils.logger import Logger as log

import nextcord
from nextcord.ext import commands

from matches import make_match
from config import GUILD_ID, VALORS_THEME1, MATCH_PLAYER_COUNT, VALORS_THEME1_2, LFG_PING_DELAY
from utils.utils import format_duration, abandon_cooldown


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
        embed = nextcord.Embed(title="Queue", color=VALORS_THEME1)
        message_lines = []
        for n, item in enumerate(queue_users, 1):
            message_lines.append(f"{n}. <@{item.user_id}> `expires `<t:{item.queue_expiry}:R>")
        embed.add_field(name=f"{len(queue_users)} in queue", value=f"{'\n'.join(message_lines)}\u2800")
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
                log.debug(f"{interaction.user.display_name} wanted to queue but was overtaken")
                return await interaction.response.send_message("Someone else just got in.\nBetter luck next time", ephemeral=True)
            self.bot.queue_manager.add_user(interaction.user.id, expiry)
            in_queue = await self.bot.store.upsert_queue_user(
                user_id=interaction.user.id, 
                guild_id=interaction.guild.id, 
                queue_channel=interaction.channel.id, 
                queue_expiry=expiry)
            if not in_queue: total_in_queue += 1
            log.debug(f"{interaction.user.display_name} has queued up")
            
            if total_in_queue == MATCH_PLAYER_COUNT:
                self.bot.queue_manager.remove_user(interaction.user.id)
                for user in queue_users: self.bot.queue_manager.remove_user(user.user_id)
                self.bot.new_activity_value = 0

                match_id = await self.bot.store.unqueue_add_match_users(settings, interaction.channel.id)
                self.bot.new_activity_value = total_in_queue
                await self.update_queue_message(interaction)
                loop = asyncio.get_event_loop()
                make_match(loop, self.bot, interaction.guild.id, match_id)
                return
        
        self.bot.new_activity_value = total_in_queue
        await self.update_queue_message(interaction)
    
    async def unready_callback(self, interaction: nextcord.Interaction):
        if not await self.bot.store.in_queue(interaction.guild.id, interaction.user.id):
            return await interaction.response.send_message("You are not queued up",ephemeral=True)
        self.bot.queue_manager.remove_user(interaction.user.id)
        await self.bot.store.unqueue_user(interaction.channel.id, interaction.user.id)
        log.debug(f"{interaction.user.display_name} has left queue")
        self.bot.new_activity_value -= 1
        await self.update_queue_message(interaction)
    
    async def stats_callback(self, interaction: nextcord.Interaction):
        user = interaction.user
        summary_stats = await self.bot.store.get_user_summary_stats(interaction.guild.id, user.id)
        if not summary_stats:
            return await interaction.response.send_message(f"No stats found for {user.mention}.", ephemeral=True)

        recent_matches = await self.bot.store.get_recent_match_stats(interaction.guild.id, user.id, 10)
        avg_stats = await self.bot.store.get_avg_stats_last_n_games(interaction.guild.id, user.id, 10)

        embed = nextcord.Embed(title=f"Stats for {user.display_name}", color=VALORS_THEME1)
        embed.set_thumbnail(url=user.avatar.url if user.avatar else user.default_avatar.url)

        # Summary stats
        embed.add_field(name="MMR", value=f"{summary_stats.mmr:.2f}", inline=True)
        embed.add_field(name="Total Games", value=summary_stats.games, inline=True)
        embed.add_field(name="Win Rate", value=f"{(summary_stats.wins / summary_stats.games * 100):.2f}%" if summary_stats.games > 0 else "N/A", inline=True)
        embed.add_field(name="Total Kills", value=summary_stats.total_kills, inline=True)
        embed.add_field(name="Total Deaths", value=summary_stats.total_deaths, inline=True)
        embed.add_field(name="Total Assists", value=summary_stats.total_assists, inline=True)
        embed.add_field(name="K/D Ratio", value=f"{(summary_stats.total_kills / summary_stats.total_deaths):.2f}" if summary_stats.total_deaths > 0 else "N/A", inline=True)
        embed.add_field(name="Total Score", value=f"{(summary_stats.total_score / summary_stats.games):.2f}" if summary_stats.games > 0 else "N/A", inline=True)

        # Recent performance
        if avg_stats:
            embed.add_field(name="\u200b", value="Average Performance (Last 10 Games)", inline=False)
            embed.add_field(name="Kills", value=f"{f'{avg_stats.get('avg_kills', None):.2f}' if avg_stats.get('avg_kills', None) else 'N/A'}", inline=True)
            embed.add_field(name="Deaths", value=f"{f'{avg_stats.get('avg_deaths', None):.2f}' if avg_stats.get('avg_deaths', None) else 'N/A'}", inline=True)
            embed.add_field(name="Assists", value=f"{f'{avg_stats.get('avg_assists', None):.2f}' if avg_stats.get('avg_assists', None) else 'N/A'}", inline=True)
            embed.add_field(name="Score", value=f"{f'{avg_stats.get('avg_score', None):.2f}' if avg_stats.get('avg_score', None) else 'N/A'}", inline=True)
            embed.add_field(name="MMR Gain", value=f"{f'{avg_stats.get('avg_mmr_change', None):.2f}' if avg_stats.get('avg_mmr_change', None) else 'N/A'}", inline=True)
        else:
            embed.add_field(name="Recent Performance", value="No recent matches found", inline=False)

        # Recent matches
        if recent_matches:
            recent_matches_str = "\n".join([f"{'W' if match.win else 'L'} | K: {match.kills} | D: {match.deaths} | A: {match.assists} | MMR: {match.mmr_change:+.2f}" for match in recent_matches])
            embed.add_field(name="Recent Matches", value=f"```{recent_matches_str}```", inline=False)
        else:
            embed.add_field(name="Recent Matches", value="No recent matches found", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def lfg_callback(self, interaction: nextcord.Interaction):
        if not await self.bot.store.in_queue(interaction.guild.id, interaction.user.id):
            return await interaction.response.send_message("You must be in queue to ping",ephemeral=True)
        
        settings = await self.bot.store.get_settings(interaction.guild.id)
        if not settings.mm_lfg_role:
            return await interaction.response.send_message("lfg_role not set. Set it with </queue settings lfg_role:1257503334533828618>", ephemeral=True)
        
        channel = interaction.guild.get_channel(settings.mm_text_channel)
        if not channel:
            return await interaction.response.send_message("Queue channel not set. Set it with </queue settings set_queue:1257503334533828618>", ephemeral=True)
        
        if interaction.guild.id in self.bot.last_lfg_ping:
            if (int(datetime.now(timezone.utc).timestamp()) - LFG_PING_DELAY) < self.bot.last_lfg_ping[interaction.guild.id]:
                return await interaction.response.send_message(
f"""A ping was already sent <t:{self.bot.last_lfg_ping[interaction.guild.id]}:R>.
Try again <t:{self.bot.last_lfg_ping[interaction.guild.id] + LFG_PING_DELAY}:R>""", ephemeral=True)
            log.debug(f"{interaction.user.display_name} wanted to ping LFG role")
        
        self.bot.last_lfg_ping[interaction.guild.id] = int(datetime.now(timezone.utc).timestamp())
        await channel.send(f"All <@&{settings.mm_lfg_role}> members are being summoned by {interaction.user.mention}", allowed_mentions=nextcord.AllowedMentions(roles=True, users=False))
        log.debug(f"{interaction.user.display_name} pinged LFG role")
        embed = nextcord.Embed(title="LookingForGame members pinged!", color=VALORS_THEME1)
        msg = await interaction.response.send_message(embed=embed, ephemeral=True)
        await asyncio.sleep(5)
        await msg.delete()

    async def toggle_lfg_callback(self, interaction: nextcord.Interaction):
        settings = await self.bot.store.get_settings(interaction.guild.id)
        if not settings.mm_lfg_role:
            return await interaction.response.send_message("lfg_role not set. Set it with </queue settings lfg_role:1257503334533828618>", ephemeral=True)
    
        lfg_role = interaction.guild.get_role(settings.mm_lfg_role)
        if not lfg_role:
            return await interaction.response.send_message("LFG Role is missing. Reach out to staff", ephemeral=True)
        
        if lfg_role in interaction.user.roles:
            await interaction.user.remove_roles(lfg_role)
            log.debug(f"{interaction.user.display_name} lost LFG role")
            return await interaction.response.send_message(f"\\- You removed {lfg_role.mention} from yourself", ephemeral=True)
        await interaction.user.add_roles(lfg_role)
        log.debug(f"{interaction.user.display_name} gained LFG role")
        await interaction.response.send_message(f"+ You added {lfg_role.mention} to yourself", ephemeral=True)
