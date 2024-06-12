import json
import logging as log

import nextcord
from nextcord.ext import commands
from sqlalchemy.ext.asyncio import AsyncSession

from config import *
from views.queue.buttons import QueueButtonsView
from utils.models import BotSettings

class Queues(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(QueueButtonsView.create_dummy_persistent(self.bot))
        log.critical("[Queues] Cog started")

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

    @queue_settings.subcommand(name="mm_lfg_role", description="Set lfg role")
    async def set_lfg(self, interaction: nextcord.Interaction, lfg: nextcord.Role):
        if not isinstance(lfg, nextcord.Role):
            return await interaction.response.send_message("This is not a role", ephemeral=True)
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, mm_lfg_role=lfg.id)
        await interaction.response.send_message(f"LookingForGame role set to {lfg.mention}", ephemeral=True)

    async def send_queue_buttons(self, interaction: nextcord.Interaction) -> nextcord.Message:
        embed = nextcord.Embed(title="Ready up!", color=VALOR_YELLOW)
        view = await QueueButtonsView.create_showable(self.bot)
        return await interaction.channel.send(embed=embed, view=view)

    @queue_settings.subcommand(name="set_buttons", description="Set queue buttons")
    async def set_queue_buttons(self, interaction: nextcord.Interaction):
        settings = await self.bot.store.get_settings(interaction.guild.id)
        if settings and settings.mm_buttons_channel and settings.mm_buttons_message:
            channel = interaction.guild.get_channel(settings.mm_buttons_channel)
            try: msg = await channel.fetch_message(settings.mm_buttons_message)
            except nextcord.errors.NotFound: pass
            else: await msg.delete()
        
        if not settings or not settings.mm_buttons_periods:
            return await interaction.response.send_message(
                "Failed...\nSet queue periods with </queue settings periods:1249109243114557461>", ephemeral=True)

        msg = await self.send_queue_buttons(interaction)
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, mm_buttons_message=msg.id, mm_buttons_channel=interaction.channel.id)
        await interaction.response.send_message(f"Queue channel set!", ephemeral=True)
    
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
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, mm_buttons_periods=periods)
        await interaction.response.send_message(
            f"Queue periods set to `{periods}`\nUse </queue settings set_buttons:1249109243114557461> to update", ephemeral=True)

    @set_queue_periods.on_autocomplete("periods")
    async def autocomplete_queue_periods(self, interaction: nextcord.Interaction, periods: str):
        settings = await self.bot.store.get_settings(interaction.guild.id)
        if not periods:
            periods = "Start typing..."
        if not settings.mm_buttons_periods:
            return await interaction.response.send_autocomplete(choices=[periods, '{"Short":5,"Default":15}'])
        await interaction.response.send_autocomplete(choices=[periods, settings.mm_buttons_periods])
    
    @queue_settings.subcommand(name="set_queue", description="Set queueing channel")
    async def set_queue_channel(self, interaction: nextcord.Interaction):
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, mm_queue_channel=interaction.channel.id)
        await interaction.response.send_message("New queue channel set successfully", ephemeral=True)


def setup(bot):
    bot.add_cog(Queues(bot))
