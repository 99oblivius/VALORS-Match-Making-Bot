import json
from utils.logger import ColorLogger as log
from io import BytesIO

from fuzzywuzzy import process

import nextcord
from nextcord.ext import commands

from config import *
from utils.models import BotSettings, MMBotRanks

from config import *
from views.register import RegistryButtonView

from utils.models import BotRegions, BotSettings


class Settings(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(RegistryButtonView(self.bot))
        await self.bot.rcon_manager.clear_dangling_servers()
        log.info("Cog started")
    
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
        
        embed = nextcord.Embed(
            title="Register for Match Making!", 
            color=VALORS_THEME1_2)
        embed.add_field(name="1.", value="Verify your Steam account", inline=True)
        embed.add_field(name="2.", value="Choose your region", inline=True)
        view = RegistryButtonView(self.bot)
        msg = await interaction.channel.send(embed=embed, view=view)
        await self.bot.store.upsert(BotSettings, 
            guild_id=interaction.guild.id, 
            register_channel=interaction.channel.id, 
            register_message=msg.id)
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
                return await interaction.response.send_message(
                    "Failed.\nIncorrect formatting. Read command description.", ephemeral=True)
            if len(regions) > 25:
                return await interaction.response.send_message(
                    "Failed.\nToo many regions", ephemeral=True)
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
            f"Regions set\nUse </settings set_register:1257503333674123367> to update", ephemeral=True)

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
    
    @settings.subcommand(name="add_server", description="Add a pavlov server")
    async def add_server(self, interaction: nextcord.Interaction, 
        host: str=nextcord.SlashOption(required=True, description="Server address"),
        port: int=nextcord.SlashOption(min_value=0, max_value=65535, required=True, description="Server port"),
        password: str=nextcord.SlashOption(required=True, description="Server rcon password"),
        region: str=nextcord.SlashOption(required=True)
    ):
        await self.bot.store.add_server(host, port, password, region)
        await interaction.response.send_message(
            f"`{region}` Server `{host}`:`{port}` added successfully.", ephemeral=True)

    @add_server.on_autocomplete("region")
    async def autocomplete_regions(self, interaction: nextcord.Interaction, region: str):
        regions = await self.bot.store.get_regions(interaction.guild.id)
        region_labels = [r.label for r in regions]
        if not region:
            return region_labels
        matches = process.extract(region, region_labels, limit=25)
        matched_labels = [match[0] for match in matches]
        return matched_labels
    
    @settings.subcommand(name="remove_server", description="Remove a pavlov server")
    async def remove_server(self, interaction: nextcord.Interaction, 
        serveraddr: str=nextcord.SlashOption(description="Server host:port", required=True)
    ):
        host, port = serveraddr.split(':')
        await self.bot.store.remove_server(host, port)
        await interaction.response.send_message(
            f"Server `{host}`:`{port}` removed successfully.", ephemeral=True)

    @remove_server.on_autocomplete("serveraddr")
    async def autocomplete_regions(self, interaction: nextcord.Interaction, serveraddr: str):
        servers = await self.bot.store.get_servers()
        if not servers:
            return servers
        serveraddrs = [f'{s.host}:{s.port}' for s in servers]
        matches = process.extract(serveraddr, serveraddrs, limit=25)
        matched_serveraddrs = [match[0] for match in matches]
        return matched_serveraddrs
    
    @settings.subcommand(name="get_ranks", description="Get the current MMR ranks")
    async def get_ranks(self, interaction: nextcord.Interaction):
        ranks = await self.bot.store.get_ranks(interaction.guild.id)
        if not ranks:
            return await interaction.response.send_message("No ranks set.", ephemeral=True)
        
        ranks_dict = {f"Rank {rank.id}": {"mmr": rank.mmr_threshold, "role_id": rank.role_id} for rank in ranks}
        
        json_str = json.dumps(ranks_dict, indent=4)
        json_bytes = json_str.encode('utf-8')
        json_file = BytesIO(json_bytes)
        json_file.seek(0)
        await interaction.response.send_message(
            "Here are the current ranks:\n_edit and upload with_ </ranks set_ranks:1249109243114557461>", 
            file=nextcord.File(json_file, filename="mmr_ranks.json"), 
            ephemeral=True)

    @settings.subcommand(name="set_ranks", description="Set MMR ranks")
    async def set_ranks(self, interaction: nextcord.Interaction, 
        ranks: nextcord.Attachment=nextcord.SlashOption(description="JSON file for MMR ranks")):
        try:
            file = await ranks.read()
            ranks = json.loads(file)
        except Exception as e:
            print(f"[Ranks] Error loading json file: {repr(e)}")
            return await interaction.response.send_message(
                "The file you provided did not contain a valid JSON string\ne.g. `{\"Bronze\": {\"mmr_threshold\": 1000, \"role_id\": 123456789}}`", ephemeral=True)

        if len(ranks) > 25:
            return await interaction.response.send_message("Failed.\nToo many ranks", ephemeral=True)
        
        await self.bot.store.remove(MMBotRanks, guild_id=interaction.guild.id)
        await self.bot.store.set_ranks(interaction.guild.id, ranks)

        await interaction.response.send_message(
            f"Ranks set successfully. Use </ranks get_ranks:1249109243114557461> to view them.", ephemeral=True)


def setup(bot):
    bot.add_cog(Settings(bot))
