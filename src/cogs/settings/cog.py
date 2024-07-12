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
from io import BytesIO

import aiohttp
import nextcord
from fuzzywuzzy import process
from nextcord.ext import commands

from config import *
from utils.logger import Logger as log
from utils.models import BotRegions, BotSettings, MMBotRanks, Platform, UserPlatformMappings, MMBotUsers, MMBotUserSummaryStats
from utils.utils import create_leaderboard_embed
from views.register import RegistryButtonView


async def validate_steam_id(platform_id: str) -> bool:
    if not platform_id.isdigit() or len(platform_id) != 17:
        return False
    
    async with aiohttp.ClientSession() as session:
        url = f"http://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/?key={STEAM_API_KEY}&steamids={platform_id}"
        async with session.get(url) as response:
            if response.status != 200:
                return False
            data = await response.json()
            return bool(data['response']['players'])


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
            description="""## Welcome to VALORS's Match Making!

1. Click `Register` to authenticate your Steam account.
   - We only access your Steam ID for performance tracking.
   - No personal information is stored or shared.

2. Select your playing region for optimal server matching.

Your privacy is our priority. Steam authentication is secure and limited to essential game data.""",
            color=VALORS_THEME1_2)
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
        log.debug(f"{interaction.user.display_name} set regions to:")
        log.pretty(regions)
            
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
        log.debug(f"{interaction.user.display_name} added an rcon server {host}:{port} password:{password} region:{region}")
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
        log.debug(f"{interaction.user.display_name} removed an rcon server {serveraddr}")
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
            log.error(f"loading json file: {repr(e)}")
            return await interaction.response.send_message(
                "The file you provided did not contain a valid JSON string\ne.g. `{\"Bronze\": {\"mmr_threshold\": 1000, \"role_id\": 123456789}}`", ephemeral=True)

        if len(ranks) > 25:
            return await interaction.response.send_message("Failed.\nToo many ranks", ephemeral=True)
        
        await self.bot.store.remove(MMBotRanks, guild_id=interaction.guild.id)
        await self.bot.store.set_ranks(interaction.guild.id, ranks)
        log.debug(f"{interaction.user.display_name} set ranks to:")
        log.pretty(ranks)

        await interaction.response.send_message(
            f"Ranks set successfully. Use </settings get_ranks:1257503333674123367> to view them.", ephemeral=True)

    @settings.subcommand(name="set_leaderboard", description="Set the channel and leaderboard message")
    async def set_leaderboard(self, interaction: nextcord.Interaction):
        settings = await self.bot.store.get_settings(interaction.guild.id)
        channel = interaction.guild.get_channel(settings.leaderboard_channel)
        if channel:
            try:
                old_message = await channel.fetch_message(settings.leaderboard_message)
                await old_message.delete()
            except nextcord.NotFound: pass
        
        data = await self.bot.store.get_leaderboard(interaction.guild.id, limit=100)
        ranks = await self.bot.store.get_ranks(interaction.guild.id)
        previous_data = await self.bot.store.get_last_mmr_for_users(interaction.guild.id)
        embed = create_leaderboard_embed(interaction.guild, data, previous_data, ranks)
        msg = await interaction.channel.send(embed=embed)
        await self.bot.store.update(BotSettings, 
            guild_id=interaction.guild.id, 
            leaderboard_channel=interaction.channel.id, 
            leaderboard_message=msg.id)
        await interaction.response.send_message(
            f"Match Making Leaderboard set", ephemeral=True)

    @nextcord.slash_command(name="change_mmr", description="Change a member's Match Making Rating", guild_ids=[GUILD_ID])
    async def change_mmr(self, interaction: nextcord.Interaction, 
        user: nextcord.User = nextcord.SlashOption(
            description="The user or member to change the MMR of."),
        add_remove: str = nextcord.SlashOption(
            name="add_remove", 
            description="Add or remove a set amount of MMR. Use negative values to remove.", 
            required=False),
        set_mmr: str = nextcord.SlashOption(
            name="set",
            description="Set the MMR to a specific value.", 
            required=False)
    ):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)

        summary_stats = await self.bot.store.get_user_summary_stats(interaction.guild.id, user.id)
        if not summary_stats:
            return await interaction.response.send_message(f"No MMR data found for {user.mention}.", ephemeral=True)

        old_mmr = summary_stats.mmr

        if add_remove is not None and set_mmr is not None:
            return await interaction.response.send_message("Please use either 'add_remove' or 'set', not both.", ephemeral=True)
        
        if add_remove is None and set_mmr is None:
            return await interaction.response.send_message("Please provide either 'add_remove' or 'set' value.", ephemeral=True)

        try:
            if add_remove is not None:
                add_remove_value = float(add_remove)
                new_mmr = old_mmr + add_remove_value
                action = "adjusted to"
            else:  # set_mmr is not None
                new_mmr = float(set_mmr)
                action = "changed to"
        except ValueError:
            return await interaction.response.send_message("Invalid input. Please provide a valid number.", ephemeral=True)
        
        new_mmr = max(0, new_mmr)

        await self.bot.store.update(MMBotUserSummaryStats, guild_id=interaction.guild.id, user_id=user.id, mmr=new_mmr)

        await interaction.response.send_message(
            f"Match Making Rating for {user.mention} {action} `{new_mmr}`. Previous MMR was `{old_mmr}`.", ephemeral=True)
        log.info(f"Match Making Rating for {user.mention} {action} `{new_mmr}`. Previous MMR was `{old_mmr}`.")
    
    @nextcord.slash_command(name="manual_register", description="Manually register a guild member with a platform ID", guild_ids=[GUILD_ID])
    async def manual_register(self,
        interaction: nextcord.Interaction,
        user: nextcord.Member = nextcord.SlashOption(description="The user to register"),
        platform: str = nextcord.SlashOption(description="The platform to register for"),
        platform_id: str = nextcord.SlashOption(description="The platform ID to register")
    ):
        settings = await self.bot.store.get_settings(interaction.guild.id)
        verified_role = interaction.guild.get_role(settings.mm_verified_role)
        try:
            platform_enum = Platform[platform.upper()]
        except KeyError:
            return await interaction.response.send_message(f"Invalid platform: {platform}", ephemeral=True)

        try:
            if platform_enum == Platform.STEAM:
                if not await validate_steam_id(platform_id):
                    return await interaction.response.send_message("The provided Steam ID is invalid.", ephemeral=True)
            else: return await interaction.resposne.send_message("This platform option does not yet exist", ephemeral=True)
            
            await self.bot.store.upsert(MMBotUsers,
                guild_id=interaction.guild.id,
                user_id=user.id)
            await self.bot.store.set_user_platform(
                guild_id=interaction.guild.id,
                user_id=user.id,
                platform=platform_enum,
                platform_id=platform_id)
            await self.bot.store.upsert(MMBotUserSummaryStats,
                guild_id=interaction.guild.id,
                user_id=user.id)
            
            if verified_role: await user.add_roles(verified_role)
            log.info(f"Registered {user.id} manually for {platform} with ID: {platform_id}")
            await interaction.response.send_message(f"Successfully registered {user.mention} for `{platform}` with ID: `{platform_id}`", ephemeral=True)
        except Exception as e:
            log.error(f"An error occurred while registering the user: {repr(e)}")
            await interaction.response.send_message(f"An error occurred while registering the user.", ephemeral=True)

    @manual_register.on_autocomplete("platform")
    async def autocomplete_platform(self, interaction: nextcord.Interaction, platform: str):
        platforms = [p.name.lower() for p in Platform]
        return [p for p in platforms if platform.lower() in p.lower()]

    @manual_register.on_autocomplete("platform_id")
    async def autocomplete_platform_id(self, interaction: nextcord.Interaction, platform_id: str, platform: str):
        if not platform:
            return ["Please select a platform first"]
        
        try:
            platform_enum = Platform(platform)
        except KeyError:
            return ["Invalid platform selected"]

        if platform_enum == Platform.STEAM:
            if platform_id.isdigit() and len(platform_id) == 17:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"http://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/?key={STEAM_API_KEY}&steamids={platform_id}") as response:
                        if response.status == 200:
                            data = await response.json()
                            if data['response']['players']:
                                return {f'{data['response']['players'][0]['personaname']}': platform_id}
                        return ["Invalid Steam ID"]
            else:
                return ["Invalid Steam ID format"]
        else:
            return ["Unsupported platform for ID validation"]


def setup(bot):
    bot.add_cog(Settings(bot))
