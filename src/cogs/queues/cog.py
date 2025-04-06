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

import json
import re
from datetime import datetime, timedelta, timezone
from io import BytesIO
import asyncio
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from main import Bot

import nextcord
from nextcord.ext import commands

from config import *
from utils.logger import Logger as log
from utils.statistics import create_graph_async, create_stats_embed
from utils.utils import format_duration, create_queue_embed, log_moderation
from views.queue.buttons import QueueButtonsView


class Queues(commands.Cog):
    def __init__(self, bot: "Bot"):
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(QueueButtonsView.create_dummy_persistent(self.bot))

        await self.bot.queue_manager.fetch_and_initialize_users()
        log.info("Cog started")

    ########################
    # QUEUE SLASH COMMANDS #
    ########################
    @nextcord.slash_command(name="q", description="See who's in queue", guild_ids=[*GUILD_IDS])
    async def show_queue(self, interaction: nextcord.Interaction):
        queue_users = await self.bot.store.get_queue_users(interaction.channel.id)
        embed = create_queue_embed(queue_users)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @nextcord.slash_command(name="remove_from_queue", description="Remove a user from a queue", guild_ids=[*GUILD_IDS])
    async def remove_from_queue(self, interaction: nextcord.Interaction, 
        user: str=nextcord.SlashOption(required=False, description="Remove a user or userid from the queue")
    ):
        if not user:
            return await interaction.response.send_message(f"You must mention a user or userid to use this command.", ephemeral=True)

        queue_users = await self.bot.store.get_queue_users(interaction.channel.id)
        match = re.search(r'\d+', user)
        if not match:
            return await interaction.response.send_message(f"`{user}` was not found as a queued user.", ephemeral=True)
        user_id = int(match.group(0))
        if user_id not in (user.user_id for user in queue_users):
            return await interaction.response.send_message(f"`{user}` was not found as a queued user.", ephemeral=True)
        
        settings = await self.bot.settings_cache(interaction.guild.id)
        await self.bot.store.unqueue_user(settings.mm_queue_channel, user_id)
        self.bot.queue_manager.remove_user(user_id)
        log.info(f"{user_id} was manually removed from queue")

        queue_users = await self.bot.store.get_queue_users(interaction.channel.id)
        asyncio.create_task(self.bot.queue_manager.update_presence(len(queue_users)))
        embed = create_queue_embed(queue_users)
        channel = interaction.guild.get_channel(settings.mm_queue_channel)
        message = await channel.fetch_message(settings.mm_queue_message)
        await message.edit(embeds=[message.embeds[0], embed])

        await interaction.response.send_message(f"<@{user_id}> was manually removed from queue", ephemeral=True)

        await log_moderation(interaction, settings.log_channel, "Member removed from queue", f"{user.mention}")

    @nextcord.slash_command(name="queue", description="Queue settings", guild_ids=[*GUILD_IDS])
    async def queue(self, interaction: nextcord.Interaction):
        pass

    @nextcord.slash_command(name="ping", description="Ping Looking for Game members", guild_ids=[*GUILD_IDS])
    async def ping_lfg(self, interaction: nextcord.Interaction):
        if not await self.bot.store.in_queue(interaction.guild.id, interaction.user.id):
            return await interaction.response.send_message("You must be in queue to ping",ephemeral=True)
        settings = await self.bot.settings_cache(interaction.guild.id)
        if not settings.mm_lfg_role:
            return await interaction.response.send_message(f"lfg_role not set. Set it with {await self.bot.command_cache.get_command_mention(interaction.guild.id, 'queue settings lfg_role')}", ephemeral=True)
        
        channel = interaction.guild.get_channel(settings.mm_text_channel)
        if not channel:
            return await interaction.response.send_message(f"Queue channel not set. Set it with {await self.bot.command_cache.get_command_mention(interaction.guild.id, 'queue settings set_queue')}", ephemeral=True)
        
        if interaction.channel.id != settings.mm_text_channel:
            return await interaction.response.send_message(f"You can only use this command in <#{settings.mm_text_channel}>", ephemeral=True)

        if interaction.guild.id in self.bot.last_lfg_ping:
            if (int(datetime.now(timezone.utc).timestamp()) - LFG_PING_DELAY) < self.bot.last_lfg_ping[interaction.guild.id]:
                return await interaction.response.send_message(
    f"""A ping was already sent <t:{self.bot.last_lfg_ping[interaction.guild.id]}:R>.
    Try again <t:{self.bot.last_lfg_ping[interaction.guild.id] + LFG_PING_DELAY}:R>""", ephemeral=True)
        
        self.bot.last_lfg_ping[interaction.guild.id] = int(datetime.now(timezone.utc).timestamp())
        await interaction.response.send_message(f"All <@&{settings.mm_lfg_role}> members are being summoned!")
        log.info(f"{interaction.user.display_name} used the ping lfg slash_command")

    @nextcord.slash_command(name="rating_change", description="Display MMR change from the last match", guild_ids=[*GUILD_IDS])
    async def rating_change(self, interaction: nextcord.Interaction):
        user = interaction.user

        last_match_mmr = await self.bot.store.get_last_match_mmr_impact(interaction.guild.id, user.id)

        if not last_match_mmr:
            return await interaction.response.send_message(f"No recent match data found for {user.mention}.", ephemeral=True)

        mmr_before, mmr_change = last_match_mmr
        mmr_after = mmr_before + mmr_change

        embed = nextcord.Embed(title=f"Last Match MMR Impact for {user.display_name}", color=VALORS_THEME1)
        embed.set_thumbnail(url=user.avatar.url if user.avatar else user.default_avatar.url)

        embed.add_field(name="MMR Before", value=f"{mmr_before:.2f}", inline=True)
        embed.add_field(name="MMR After", value=f"{mmr_after:.2f}", inline=True)
        embed.add_field(name="MMR Change", value=f"{mmr_change:+.2f}", inline=True)

        last_match = await self.bot.store.get_recent_match_stats(interaction.guild.id, user.id, 1)
        if last_match:
            match = last_match[0]
            embed.add_field(name="Match Result", value="Win" if match.win else "Loss", inline=True)
            embed.add_field(name="K/D/A", value=f"{match.kills}/{match.deaths}/{match.assists}", inline=True)
            embed.add_field(name="Score", value=str(match.score), inline=True)
        
        settings = await self.bot.settings_cache(interaction.guild.id)
        await interaction.response.send_message(embed=embed, ephemeral=interaction.channel.id != settings.mm_text_channel)

    @nextcord.slash_command(name="stats", description="List your recent performance", guild_ids=[*GUILD_IDS])
    async def stats(self, interaction: nextcord.Interaction, 
        user: nextcord.User | None = nextcord.SlashOption(required=False)
    ):
        settings = await self.bot.settings_cache(interaction.guild.id)
        user = user or interaction.user

        summary_stats = await self.bot.store.get_user_summary_stats(interaction.guild.id, user.id)
        if not summary_stats:
            return await interaction.response.send_message(f"No stats found for {user.mention}.", ephemeral=True)

        recent_matches = await self.bot.store.get_recent_match_stats(interaction.guild.id, user.id, 10)
        avg_stats = await self.bot.store.get_avg_stats_last_n_games(interaction.guild.id, user.id, 10)
        leaderboard = await self.bot.store.get_leaderboard(interaction.guild.id)
        ranks = await self.bot.store.get_ranks(interaction.guild.id)
        user_data = await self.bot.store.get_user(interaction.guild.id, user.id)
        embed = create_stats_embed(interaction.guild, user, user_data, leaderboard, summary_stats, avg_stats, recent_matches, ranks)

        await interaction.response.send_message(
            embed=embed, ephemeral=interaction.channel.id != settings.mm_text_channel)

    @nextcord.slash_command(name="graph", description="Graph your recent rating performance", guild_ids=[*GUILD_IDS])
    async def graph(
        self, 
        interaction: nextcord.Interaction,
        graph_type: str = nextcord.SlashOption(
            name="type",
            description="Type of graph to display",
            choices={
                "MMR": "mmr_game",
                "Kills": "kills_game",
                "K/D": "kd_game",
                "Win rate over time": "winrate_time",
                "Score": "score_game",
                "(Supporter exclusive)": "supporter_only"
            },
            default="mmr_game",
            required=False),
        period: str=nextcord.SlashOption(
            description="(Supporter exclusive)",
            required=False)
    ):
        if graph_type == "supporter_only":
            return await interaction.response.send_message("This graph type is supporter exclusive.", ephemeral=True)
        
        user = interaction.user

        match_stats = await self.bot.store.get_last_n_match_stats(interaction.guild.id, user.id, 50)

        if not match_stats:
            return await interaction.response.send_message(f"No data found for {user.mention}.", ephemeral=True)

        ranks = await self.bot.store.get_ranks(interaction.guild.id)
        ranks = { interaction.guild.get_role(rank.role_id): rank for rank in ranks }
        fig = await create_graph_async(asyncio.get_event_loop(), graph_type, match_stats, ranks)
        
        # Save the plot to a BytesIO object
        img_bytes = BytesIO()
        fig.write_image(img_bytes, format="png", scale=2)
        img_bytes.seek(0)

        # Create a Discord file from the BytesIO object
        file = nextcord.File(img_bytes, filename="graph.png")
        settings = await self.bot.settings_cache(interaction.guild.id)
        await interaction.response.send_message(f"Graph for {user.mention}", file=file, ephemeral=interaction.channel.id != settings.mm_text_channel)
    
    @nextcord.slash_command(name="pingme", description="Get a direct message when the queue reaches a specified size", guild_ids=[*GUILD_IDS])
    async def pingme(self, 
        interaction: nextcord.Interaction,
        count: int = nextcord.SlashOption(
            description="How many members in queue for you to be pinged. 0 to not be notified.",
            min_value=0,
            max_value=MATCH_PLAYER_COUNT-1,
            required=True),
        expiration: str = nextcord.SlashOption(
            description="Time period (format: 0d0h0m)",
            required=False,
            default=None),
        one_time: bool = nextcord.SlashOption(
            description="Only be pinged once",
            choices={
                "Yes": True,
                "No": False
            },
            default=False,
            required=False)
    ):
        if expiration:
            expiry_match = re.match(r"(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?", expiration)
            if not expiry_match:
                return await interaction.followup.send("Invalid period format. Use 0d0h0m (e.g., 2h6m for 2 hours and 6 minutes).", ephemeral=True)

            days, hours, minutes = map(lambda x: int(x) if x else 0, expiry_match.groups())
            expiration = int((datetime.now(timezone.utc) + timedelta(days=days, hours=hours, minutes=minutes)).timestamp())
        
        await self.bot.store.set_user_notification(interaction.guild.id, interaction.user.id, count, expiration, one_time)
        message = f"You will be notified {'once ' if one_time else ''}if the queue reaches `{count}` members{f' <t:{expiration}:R>' if expiration else ''}."
        await interaction.response.send_message(message, ephemeral=True)


    ##############################
    # QUEUE SETTINGS SUBCOMMANDS #
    ##############################
    @queue.subcommand(name="settings", description="Queue settings")
    async def queue_settings(self, interaction: nextcord.Interaction):
        pass
    
    @queue_settings.subcommand(name="set_logs", description="Set which channel receives queue logs")
    async def set_logs(self, interaction: nextcord.Interaction):
        settings = await self.bot.settings_cache(guild_id=interaction.guild.id, mm_log_channel=interaction.channel.id)
        await interaction.response.send_message("Queue log channel set", ephemeral=True)
        await log_moderation(interaction, settings.log_channel, "Set mm logs", f"<#{interaction.channel.id}>")

    @queue_settings.subcommand(name="lfg_role", description="Set lfg role")
    async def set_mm_lfg(self, interaction: nextcord.Interaction, lfg: nextcord.Role):
        if not isinstance(lfg, nextcord.Role):
            return await interaction.response.send_message("This is not a role", ephemeral=True)
        settings = await self.bot.settings_cache(guild_id=interaction.guild.id, mm_lfg_role=lfg.id)
        await interaction.response.send_message(f"LookingForGame role set to {lfg.mention}", ephemeral=True)
        await log_moderation(interaction, settings.log_channel, "Set lfg role", f"{lfg.mention}>")

    @queue_settings.subcommand(name="verified_role", description="Set verified role")
    async def set_mm_verified(self, interaction: nextcord.Interaction, verified: nextcord.Role):
        if not isinstance(verified, nextcord.Role):
            return await interaction.response.send_message("This is not a role", ephemeral=True)
        settings = await self.bot.settings_cache(guild_id=interaction.guild.id, mm_verified_role=verified.id)
        await interaction.response.send_message(f"Verified role set to {verified.mention}", ephemeral=True)
        await log_moderation(interaction, settings.log_channel, "Set verified role", f"{verified.mention}")

    @queue_settings.subcommand(name="staff_role", description="Set match making staff role")
    async def set_mm_staff(self, interaction: nextcord.Interaction, staff: nextcord.Role):
        if not isinstance(staff, nextcord.Role):
            return await interaction.response.send_message("This is not a role", ephemeral=True)
        settings = await self.bot.settings_cache(guild_id=interaction.guild.id, mm_staff_role=staff.id)
        await interaction.response.send_message(f"Match making staff role set to {staff.mention}", ephemeral=True)
        await log_moderation(interaction, settings.log_channel, "Set staff role", f"{staff.mention}")

    @queue_settings.subcommand(name="set_mute", description="Set match making mute role")
    async def settings_set_mute(self, interaction: nextcord.Interaction, mute: nextcord.Role):
        settings = await self.bot.settings_cache(guild_id=interaction.guild.id, mm_mute_role=mute.id)
        await interaction.response.send_message(f"Mute role set to {mute.mention}", ephemeral=True)
        await log_moderation(interaction, settings.log_channel, "Mute role set", f"<@&{mute.id}>")

    async def send_queue_buttons(self, interaction: nextcord.Interaction) -> nextcord.Message:
        embed = nextcord.Embed(title="Ready up!", color=VALORS_THEME2)
        view = await QueueButtonsView.create_showable(self.bot)
        return await interaction.channel.send(embed=embed, view=view)

    @queue_settings.subcommand(name="set_queue", description="Set queue buttons")
    async def set_queue_buttons(self, interaction: nextcord.Interaction):
        settings = await self.bot.settings_cache(interaction.guild.id)
        if settings and settings.mm_queue_channel and settings.mm_queue_message:
            channel = interaction.guild.get_channel(settings.mm_queue_channel)
            if channel:
                try: msg = await channel.fetch_message(settings.mm_queue_message)
                except nextcord.errors.NotFound: pass
                else: await msg.delete()
        
        if not settings or not settings.mm_queue_periods:
            return await interaction.response.send_message(
                f"Failed...\nSet queue periods with {await self.bot.command_cache.get_command_mention(interaction.guild.id, 'queue settings set_queue_periods')}", ephemeral=True)

        msg = await self.send_queue_buttons(interaction)
        await self.bot.settings_cache(guild_id=interaction.guild.id, mm_queue_message=msg.id, mm_queue_channel=interaction.channel.id)
        await interaction.response.send_message(f"Queue channel set!", ephemeral=True)
        await log_moderation(interaction, settings.log_channel, "Queue buttons set", f"In <#{interaction.channel.id}>")
    
    @queue_settings.subcommand(name="set_reminder", description="Set queue reminder time in seconds")
    async def set_queue_reminder(self, interaction: nextcord.Interaction, 
            reminder_time: int=nextcord.SlashOption(
                min_value=5, 
                max_value=3600, 
                required=True)):
        await self.bot.settings_cache(guild_id=interaction.guild.id, mm_queue_reminder=reminder_time)
        await interaction.response.send_message(f"Queue reminder set to {format_duration(reminder_time)}", ephemeral=True)
        settings = await self.bot.settings_cache(interaction.guild.id)
        await log_moderation(interaction, settings.log_channel, "Queue reminder set", f"{format_duration(reminder_time)}")
    
    @queue_settings.subcommand(name="set_queue_periods", description="Set queue ready periods")
    async def set_queue_periods(self, interaction: nextcord.Interaction, 
        periods: nextcord.Attachment=nextcord.SlashOption(description="JSON file for queue periods")):
        try:
            file = await periods.read()
            periods_json = json.loads(file)
        except Exception as e:
            log.error(f"loading json file: {repr(e)}")
            return await interaction.response.send_message(
                "The file you provided did not contain a valid JSON string\ne.g. `{\"Short\":5,\"Default\":15}`", ephemeral=True)

        if len(periods_json) > 15:  # Discord limits to 5 buttons on 5 rows (last 2 for other menu)
            return await interaction.response.send_message("Failed.\nToo many periods", ephemeral=True)
        
        periods_str = json.dumps(periods_json, separators=[',', ':'])
        await self.bot.settings_cache(guild_id=interaction.guild.id, mm_queue_periods=periods_str)
        log.info(f"{interaction.user.display_name} set queue periods to:")
        log.pretty(periods_json)
        await interaction.response.send_message(
            f"Queue periods set to `{periods_str}`\nUse {await self.bot.command_cache.get_command_mention(interaction.guild.id, 'queue settings set_queue')} to update", ephemeral=True)
        settings = await self.bot.settings_cache(interaction.guild.id)
        await log_moderation(interaction, settings.log_channel, "Queue periods set", f"```\n{periods_json}```")

    @queue_settings.subcommand(name="get_queue_periods", description="Get the current queue ready periods")
    async def get_queue_periods(self, interaction: nextcord.Interaction):
        settings = await self.bot.settings_cache(interaction.guild.id)
        if not settings.mm_queue_periods:
            return await interaction.response.send_message("No queue periods set.", ephemeral=True)
        
        periods_json = settings.mm_queue_periods
        periods_dict = json.loads(periods_json)
        
        json_str = json.dumps(periods_dict, indent=4)
        json_bytes = json_str.encode('utf-8')
        json_file = BytesIO(json_bytes)
        json_file.seek(0)
        await interaction.response.send_message(
            f"Here are the current queue periods:\n_edit and upload with_ {await self.bot.command_cache.get_command_mention(interaction.guild.id, 'queue settings set_queue_periods')}", file=nextcord.File(json_file, filename="queue_periods.json"), ephemeral=True)
    
    @queue_settings.subcommand(name="set_text", description="Set general queueing channel")
    async def set_text_channel(self, interaction: nextcord.Interaction):
        settings = await self.bot.settings_cache(guild_id=interaction.guild.id, mm_text_channel=interaction.channel.id)
        await interaction.response.send_message("Text channel set successfully", ephemeral=True)
        await log_moderation(interaction, settings.log_channel, "Set text channel", f"<#{interaction.channel.id}>")
    
    @queue_settings.subcommand(name="set_voice", description="Set queueing voice channel")
    async def set_voice_channel(self, interaction: nextcord.Interaction, voice_channel: nextcord.VoiceChannel):
        if not isinstance(voice_channel, nextcord.VoiceChannel):
            return await interaction.response.send_message("The channel you selected is not a Voice Channel", ephemeral=True)
        
        settings = await self.bot.settings_cache(guild_id=interaction.guild.id, mm_voice_channel=voice_channel.id)
        await interaction.response.send_message("Voice channel set successfully", ephemeral=True)
        await log_moderation(interaction, settings.log_channel, "Set voice channel", f"<#{voice_channel.id}>")


def setup(bot):
    bot.add_cog(Queues(bot))
