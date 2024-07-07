import json
import re
from utils.logger import Logger as log
from io import BytesIO
from datetime import datetime, timezone, timedelta

import nextcord
from nextcord.ext import commands, tasks

from config import *
from views.queue.buttons import QueueButtonsView
from utils.models import BotSettings
from utils.utils import format_duration, create_stats_embed
from utils.statistics import create_graph


class Queues(commands.Cog):
    @tasks.loop(seconds=5)
    async def queue_activity(self):
        try:
            if self.bot.last_activity_value != self.bot.new_activity_value:
                self.bot.last_activity_value = self.bot.new_activity_value
                await self.bot.change_presence(
                    activity=nextcord.CustomActivity(
                        name=f"Queue [{self.bot.new_activity_value}/{MATCH_PLAYER_COUNT}]"))
        except Exception as e:
            log.critical(f"Exception in queue_activity: {repr(e)}")

    @queue_activity.before_loop
    async def wait_queue_activity(self):
        await self.bot.wait_until_ready()
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.queue_activity.start()
    
    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(QueueButtonsView.create_dummy_persistent(self.bot))

        await self.bot.queue_manager.fetch_and_initialize_users()
        log.info("Cog started")

    ########################
    # QUEUE SLASH COMMANDS #
    ########################
    @nextcord.slash_command(name="queue", description="Queue settings", guild_ids=[GUILD_ID])
    async def queue(self, interaction: nextcord.Interaction):
        pass

    @nextcord.slash_command(name="lfg", description="Ping Looking for Game members", guild_ids=[GUILD_ID])
    async def ping_lfg(self, interaction: nextcord.Interaction):
        if not await self.bot.store.in_queue(interaction.guild.id, interaction.user.id):
            return await interaction.response.send_message("You must be in queue to ping",ephemeral=True)
        settings = await self.bot.store.get_settings(interaction.guild.id)
        if not settings.mm_lfg_role:
            return await interaction.response.send_message("lfg_role not set. Set it with </queue settings lfg_role:1257503334533828618>", ephemeral=True)
        
        channel = interaction.guild.get_channel(settings.mm_text_channel)
        if not channel:
            return await interaction.response.send_message("Queue channel not set. Set it with </queue settings set_queue:1257503334533828618>", ephemeral=True)
        
        if interaction.channel.id != settings.mm_text_channel:
            return await interaction.response.send_message(f"You can only use this command in <#{settings.mm_text_channel}>", ephemeral=True)

        if interaction.guild.id in self.bot.last_lfg_ping:
            if (int(datetime.now(timezone.utc).timestamp()) - LFG_PING_DELAY) < self.bot.last_lfg_ping[interaction.guild.id]:
                return await interaction.response.send_message(
    f"""A ping was already sent <t:{self.bot.last_lfg_ping[interaction.guild.id]}:R>.
    Try again <t:{self.bot.last_lfg_ping[interaction.guild.id] + LFG_PING_DELAY}:R>""", ephemeral=True)
        
        self.bot.last_lfg_ping[interaction.guild.id] = int(datetime.now(timezone.utc).timestamp())
        await interaction.response.send_message(f"All <@&{settings.mm_lfg_role}> members are being summoned!")
        log.debug(f"{interaction.user.display_name} used the ping lfg slash_command")

    @nextcord.slash_command(name="rating_change", description="Display MMR change from the last match", guild_ids=[GUILD_ID])
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
        
        settings = await self.bot.store.get_settings(interaction.guild.id)
        await interaction.response.send_message(embed=embed, ephemeral=interaction.channel.id != settings.mm_text_channel)

    @nextcord.slash_command(name="stats", description="List your recent performance", guild_ids=[GUILD_ID])
    async def stats(self, interaction: nextcord.Interaction, 
        user: nextcord.User | None = nextcord.SlashOption(required=False)
    ):
        settings = await self.bot.store.get_settings(interaction.guild.id)
        if user is None:
            user = interaction.user

        summary_stats = await self.bot.store.get_user_summary_stats(interaction.guild.id, user.id)
        if not summary_stats:
            return await interaction.response.send_message(f"No stats found for {user.mention}.", ephemeral=True)

        recent_matches = await self.bot.store.get_recent_match_stats(interaction.guild.id, user.id, 10)
        avg_stats = await self.bot.store.get_avg_stats_last_n_games(interaction.guild.id, user.id, 10)
        data = await self.bot.store.get_leaderboard(interaction.guild.id, limit=100)
        embed = create_stats_embed(interaction.guild, interaction.user, data, summary_stats, avg_stats, recent_matches)

        await interaction.response.send_message(
            embed=embed, ephemeral=interaction.channel.id != settings.mm_text_channel)

    @nextcord.slash_command(name="graph", description="Graph your recent rating performance", guild_ids=[GUILD_ID])
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
                "Overview": "performance_overview"
            },
            default="mmr_game",
            required=False
        ),
        period: str = nextcord.SlashOption(
            name="period",
            description="Time period (format: 0y0m0d0h, e.g., 1y6m for 1 year and 6 months)",
            required=False,
            default="50g"
        )
    ):
        user = interaction.user

        # Parse the period
        if period.endswith('g'):
            game_limit = int(period[:-1])
            match_stats = await self.bot.store.get_last_n_match_stats(interaction.guild.id, user.id, game_limit)
        else:
            period_match = re.match(r"(?:(\d+)y)?(?:(\d+)m)?(?:(\d+)d)?(?:(\d+)h)?", period)
            if not period_match:
                return await interaction.response.send_message("Invalid period format. Use 0y0m0d0h (e.g., 1y6m for 1 year and 6 months) or Ng (e.g., 50g for last 50 games).", ephemeral=True)

            years, months, days, hours = map(lambda x: int(x) if x else 0, period_match.groups())
            start_date = datetime.now() - timedelta(days=years*365 + months*30 + days, hours=hours)
            end_date = datetime.now()
            match_stats = await self.bot.store.get_match_stats_in_period(interaction.guild.id, user.id, start_date, end_date)

        if not match_stats:
            return await interaction.response.send_message(f"No data found for {user.mention} in the specified period.", ephemeral=True)

        ranks = await self.bot.store.get_ranks(interaction.guild.id)
        ranks = { interaction.guild.get_role(rank.role_id): rank for rank in ranks }
        fig = create_graph(graph_type, match_stats, ranks)
        
        # Save the plot to a BytesIO object
        img_bytes = BytesIO()
        fig.write_image(img_bytes, format="png", scale=2)
        img_bytes.seek(0)

        # Create a Discord file from the BytesIO object
        file = nextcord.File(img_bytes, filename="graph.png")
        settings = await self.bot.store.get_settings(interaction.guild.id)
        await interaction.response.send_message(f"Graph for {user.mention}", file=file, ephemeral=interaction.channel.id != settings.mm_text_channel)

    ##############################
    # QUEUE SETTINGS SUBCOMMANDS #
    ##############################
    @queue.subcommand(name="settings", description="Queue settings")
    async def queue_settings(self, interaction: nextcord.Interaction):
        pass
    
    @queue_settings.subcommand(name="set_logs", description="Set which channel receives queue logs")
    async def set_logs(self, interaction: nextcord.Interaction):
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, mm_log_channel=interaction.channel.id)
        await interaction.response.send_message("Queue log channel set", ephemeral=True)

    @queue_settings.subcommand(name="lfg_role", description="Set lfg role")
    async def set_mm_lfg(self, interaction: nextcord.Interaction, lfg: nextcord.Role):
        if not isinstance(lfg, nextcord.Role):
            return await interaction.response.send_message("This is not a role", ephemeral=True)
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, mm_lfg_role=lfg.id)
        await interaction.response.send_message(f"LookingForGame role set to {lfg.mention}", ephemeral=True)

    @queue_settings.subcommand(name="verified_role", description="Set verified role")
    async def set_mm_verified(self, interaction: nextcord.Interaction, verified: nextcord.Role):
        if not isinstance(verified, nextcord.Role):
            return await interaction.response.send_message("This is not a role", ephemeral=True)
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, mm_verified_role=verified.id)
        await interaction.response.send_message(f"Verified role set to {verified.mention}", ephemeral=True)

    @queue_settings.subcommand(name="staff_role", description="Set match making staff role")
    async def set_mm_staff(self, interaction: nextcord.Interaction, staff: nextcord.Role):
        if not isinstance(staff, nextcord.Role):
            return await interaction.response.send_message("This is not a role", ephemeral=True)
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, mm_staff_role=staff.id)
        await interaction.response.send_message(f"Match making staff role set to {staff.mention}", ephemeral=True)

    async def send_queue_buttons(self, interaction: nextcord.Interaction) -> nextcord.Message:
        embed = nextcord.Embed(title="Ready up!", color=VALORS_THEME2)
        view = await QueueButtonsView.create_showable(self.bot)
        return await interaction.channel.send(embed=embed, view=view)

    @queue_settings.subcommand(name="set_queue", description="Set queue buttons")
    async def set_queue_buttons(self, interaction: nextcord.Interaction):
        settings = await self.bot.store.get_settings(interaction.guild.id)
        if settings and settings.mm_queue_channel and settings.mm_queue_message:
            channel = interaction.guild.get_channel(settings.mm_queue_channel)
            try: msg = await channel.fetch_message(settings.mm_queue_message)
            except nextcord.errors.NotFound: pass
            else: await msg.delete()
        
        if not settings or not settings.mm_queue_periods:
            return await interaction.response.send_message(
                "Failed...\nSet queue periods with </queue settings set_queue_periods:1257503334533828618>", ephemeral=True)

        msg = await self.send_queue_buttons(interaction)
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, mm_queue_message=msg.id, mm_queue_channel=interaction.channel.id)
        await interaction.response.send_message(f"Queue channel set!", ephemeral=True)
    
    @queue_settings.subcommand(name="set_reminder", description="Set queue reminder time in seconds")
    async def set_queue_reminder(self, interaction: nextcord.Interaction, 
            reminder_time: int=nextcord.SlashOption(
                min_value=5, 
                max_value=3600, 
                required=True)):
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, mm_queue_reminder=reminder_time)
        await interaction.response.send_message(f"Queue reminder set to {format_duration(reminder_time)}", ephemeral=True)
    
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
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, mm_queue_periods=periods_str)
        log.debug(f"{interaction.user.display_name} set queue periods to:")
        log.pretty(periods_json)
        await interaction.response.send_message(
            f"Queue periods set to `{periods_str}`\nUse </queue settings set_queue:1257503334533828618> to update", ephemeral=True)

    @queue_settings.subcommand(name="get_queue_periods", description="Get the current queue ready periods")
    async def get_queue_periods(self, interaction: nextcord.Interaction):
        settings = await self.bot.store.get_settings(interaction.guild.id)
        if not settings.mm_queue_periods:
            return await interaction.response.send_message("No queue periods set.", ephemeral=True)
        
        periods_json = settings.mm_queue_periods
        periods_dict = json.loads(periods_json)
        
        json_str = json.dumps(periods_dict, indent=4)
        json_bytes = json_str.encode('utf-8')
        json_file = BytesIO(json_bytes)
        json_file.seek(0)
        await interaction.response.send_message(
            "Here are the current queue periods:\n_edit and upload with_ </queue settings set_queue_periods:1257503334533828618>", file=nextcord.File(json_file, filename="queue_periods.json"), ephemeral=True)
    
    @queue_settings.subcommand(name="set_text", description="Set general queueing channel")
    async def set_text_channel(self, interaction: nextcord.Interaction):
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, mm_text_channel=interaction.channel.id)
        await interaction.response.send_message("Text channel set successfully", ephemeral=True)
    
    @queue_settings.subcommand(name="set_voice", description="Set queueing voice channel")
    async def set_voice_channel(self, interaction: nextcord.Interaction, voice_channel: nextcord.VoiceChannel):
        if not isinstance(voice_channel, nextcord.VoiceChannel):
            return await interaction.response.send_message("The channel you selected is not a Voice Channel", ephemeral=True)
        
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, mm_voice_channel=voice_channel.id)
        await interaction.response.send_message("Voice channel set successfully", ephemeral=True)


def setup(bot):
    bot.add_cog(Queues(bot))
