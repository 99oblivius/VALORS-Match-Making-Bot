import json
from typing import List
import logging as log

import nextcord
from nextcord.ext import commands

from config import *
from utils.models import BotSettings

from config import *
from views.regions.select import RegistryButtonView

from utils.models import BotRegions, BotSettings


class Settings(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(RegistryButtonView(self.bot))
        log.info("[Queues] Cog started")
    
    @nextcord.slash_command(name="settings", description="Settings", guild_ids=[GUILD_ID])
    async def settings(self, interaction: nextcord.Interaction):
        pass

    @settings.subcommand(name="set_logs", description="Set which channel receives bot logs")
    async def settings_set_logs(self, interaction: nextcord.Interaction):
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, log_channel=interaction.channel.id)
        await interaction.response.send_message("Log channel set", ephemeral=True)

    @settings.subcommand(name="set_staff", description="Set which channel is intended for staff commands")
    async def settings_set_staff(self, interaction: nextcord.Interaction):
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, staff_channel=interaction.channel.id)
        await interaction.response.send_message("Staff channel set", ephemeral=True)
    
    @settings.subcommand(name="set_register", description="Set which channel is intended for registry")
    async def settings_set_register_select(self, interaction: nextcord.Interaction):
        settings = await self.bot.store.get_settings(interaction.guild.id)
        if settings and settings.register_channel and settings.register_message:
            channel = interaction.guild.get_channel(settings.register_channel)
            try: msg = await channel.fetch_message(settings.register_message)
            except nextcord.errors.NotFound: pass
            else: await msg.delete()
        
        embed = nextcord.Embed(title="Register for Match Making!", color=VALORS_THEME1_2)
        view = RegistryButtonView(self.bot)
        msg = await interaction.channel.send(embed=embed, view=view)
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, register_channel=interaction.channel.id, register_message=msg.id)
        await interaction.response.send_message("Registry channel set", ephemeral=True)
    
    @settings.subcommand(name="regions", description="Set regions")
    async def set_regions(self, interaction: nextcord.Interaction, 
        regions: str = nextcord.SlashOption(
            name="json", 
            description="Comma separated List or region:emoji Json",
            required=True)
    ):
        if regions.find('{') != -1 or regions.find('}') != -1:
            try:
                regions = json.loads(regions)
            except Exception: 
                return await interaction.response.send_message("Failed.\nIncorrect formatting. Read command description.", ephemeral=True)
            if len(regions) > 25:
                return await interaction.response.send_message("Failed.\nToo many regions", ephemeral=True)
        else:
            regions = regions.replace(' ', '')
            regions = regions.split(',')
            regions = {region: None for region in regions}

        guild_id = interaction.guild_id
        existing_regions = await self.bot.store.get_regions(guild_id)

        existing_labels = {region.label for region in existing_regions}
        new_labels = set(regions.keys())
        removed_labels = existing_labels - new_labels
        for label in removed_labels:
            await self.bot.store.null_user_region(guild_id, label)
            await self.bot.store.remove(BotRegions, guild_id=guild_id, label=label)
        for n, (label, emoji) in enumerate(regions.items()):
            await self.bot.store.upsert(BotRegions, guild_id=guild_id, label=label, emoji=emoji.strip(), index=n)
            
        await interaction.response.send_message(
            f"Regions set\nUse </settings set_register:1249942181180084235> to update", ephemeral=True)

    @set_regions.on_autocomplete("regions")
    async def autocomplete_regions(self, interaction: nextcord.Interaction, regions: str):
        if not regions:
            regions = "Start typing..."
        existing_regions = await self.bot.store.get_regions(interaction.guild.id)
        dict_regions = {}
        if existing_regions:
            dict_regions = { r.label: "" for r in existing_regions }
        else: dict_regions = { "NA": "🌎", "EU": "🌍" }

        existing_regions = json.dumps(dict_regions, separators=[',', ':'])
        if len(existing_regions) > 100:
            existing_regions = "Autofill response too long sorry."
        await interaction.response.send_autocomplete(choices=[regions, existing_regions])


def setup(bot):
    bot.add_cog(Settings(bot))
