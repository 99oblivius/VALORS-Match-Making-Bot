import json
import logging as log

import nextcord
from nextcord.ext import commands
from sqlalchemy.ext.asyncio import AsyncSession

from config import *
from views.queue.buttons import QueueButtonsView
from utils.models import BotSettings
from utils.formatters import format_duration
from matches import load_ongoing_matches
from matches.accept import AcceptView

class Queues(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(QueueButtonsView.create_dummy_persistent(self.bot))
        self.bot.add_view(AcceptView(self.bot))

        await self.bot.queue_manager.fetch_and_initialize_users()
        log.critical("[Queues] Cog started")

        matches = await self.bot.store.get_ongoing_matches()
        await load_ongoing_matches(self.bot, matches)

    ########################
    # QUEUE SLASH COMMANDS #
    ########################
    @nextcord.slash_command(name="queue", description="Queue settings", guild_ids=[GUILD_ID])
    async def queue(self, interaction: nextcord.Interaction):
        pass

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

    @queue_settings.subcommand(name="accept_period", description="Set match accept period")
    async def set_mm_accept_period(self, interaction: nextcord.Interaction, 
        seconds: int=nextcord.SlashOption(min_value=0, max_value=1800)):
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, mm_accept_period=seconds)
        await interaction.response.send_message(f"Accept period set to `{format_duration(seconds)}`", ephemeral=True)
    
    @set_mm_accept_period.on_autocomplete("seconds")
    async def autocomplete_accept_period(self, interaction: nextcord.Interaction, seconds):
        settings = await self.bot.store.get_settings(interaction.guild.id)
        if not seconds or not settings.mm_queue_periods:
            return await interaction.response.send_autocomplete(choices=[180])
        await interaction.response.send_autocomplete(choices=[seconds, settings.mm_accept_period])

    @queue_settings.subcommand(name="lfg_role", description="Set lfg role")
    async def set_mm_lfg(self, interaction: nextcord.Interaction, lfg: nextcord.Role):
        if not isinstance(lfg, nextcord.Role):
            return await interaction.response.send_message("This is not a role", ephemeral=True)
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, mm_lfg_role=lfg.id)
        await interaction.response.send_message(f"LookingForGame role set to {lfg.mention}", ephemeral=True)

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
                "Failed...\nSet queue periods with </queue settings periods:1249109243114557461>", ephemeral=True)

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
    
    @queue_settings.subcommand(name="periods", description="Set queue ready periods")
    async def set_queue_periods(self, interaction: nextcord.Interaction, 
        periods: str = nextcord.SlashOption(
            name="json", 
            description="name:period Json",
            required=True,
            min_length=2)
    ):
        try: periods = json.loads(periods)
        except Exception:
            return await interaction.response.send_message("Failed.\nIncorrect formatting. Read command description.", ephemeral=True)
        if len(periods) > 15: # Discord limits 5 buttons on 5 rows (last 2 for other menu)
            return await interaction.response.send_message("Failed.\nToo many periods", ephemeral=True)
        periods = json.dumps(periods, separators=[',', ':'])
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, mm_queue_periods=periods)
        await interaction.response.send_message(
            f"Queue periods set to `{periods}`\nUse </queue settings set_buttons:1249109243114557461> to update", ephemeral=True)

    @set_queue_periods.on_autocomplete("periods")
    async def autocomplete_queue_periods(self, interaction: nextcord.Interaction, periods: str):
        settings = await self.bot.store.get_settings(interaction.guild.id)
        if not periods:
            periods = "Start typing..."
        if not settings.mm_queue_periods:
            return await interaction.response.send_autocomplete(choices=[periods, '{"Short":5,"Default":15}'])
        await interaction.response.send_autocomplete(choices=[periods, settings.mm_queue_periods])
    
    @queue_settings.subcommand(name="set_text", description="Set general queueing channel")
    async def set_text_channel(self, interaction: nextcord.Interaction):
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, mm_text_channel=interaction.channel.id)
        await interaction.response.send_message("Text channel set successfully", ephemeral=True)
    
    @queue_settings.subcommand(name="set_voice", description="Set queueing voice channel")
    async def set_voice_channel(self, interaction: nextcord.Interaction, voice_channel: nextcord.VoiceChannel):
        if not isinstance(voice_channel, nextcord.VoiceChannel):
            return await interaction.response.send_message("The channel you selected is not a Voice Channel", ephemeral=True)
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, mm_voice_channel=voice_channel)
        await interaction.response.send_message("Voice channel set successfully", ephemeral=True)


def setup(bot):
    bot.add_cog(Queues(bot))
