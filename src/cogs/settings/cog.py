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
from typing import Dict, List, cast, TYPE_CHECKING
if TYPE_CHECKING:
    from main import Bot

from fuzzywuzzy import process
from nextcord.ext import commands

from config import *
from utils.logger import Logger as log
from utils.models import BotRegions, MMBotRanks, Platform, MMBotUsers, MMBotUserSummaryStats
from utils.statistics import update_leaderboard
from views.register import RegistryButtonView
from utils.utils import log_moderation


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
    def __init__(self, bot: "Bot"):
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(RegistryButtonView(self.bot))
        await self.bot.rcon_manager.clear_dangling_servers()
        log.info("Cog started")
    
    @nextcord.slash_command(name="settings", description="Settings", guild_ids=[*GUILD_IDS])
    async def settings(self, interaction: nextcord.Interaction):
        pass

    @settings.subcommand(name="set_match_category", description="Set which category contains match channels")
    async def settings_set_match_category(self, interaction: nextcord.Interaction):
        settings = await self.bot.settings_cache(guild_id=interaction.guild.id, mm_match_category=interaction.channel.category_id)
        await interaction.response.send_message("Match category set", ephemeral=True)
        await log_moderation(interaction, settings.log_channel, f"Match category set to <#{interaction.channel.category_id}>")

    @settings.subcommand(name="set_logs", description="Set which channel receives bot logs")
    async def settings_set_logs(self, interaction: nextcord.Interaction):
        settings = await self.bot.settings_cache(guild_id=interaction.guild.id, log_channel=interaction.channel.id)
        await interaction.response.send_message("Log channel set", ephemeral=True)
        await log_moderation(interaction, settings.log_channel, f"Moderation logs set in <#{interaction.channel.id}>")

    @settings.subcommand(name="set_staff", description="Set which channel is intended for staff commands")
    async def settings_set_staff(self, interaction: nextcord.Interaction):
        settings = await self.bot.settings_cache(guild_id=interaction.guild.id, staff_channel=interaction.channel.id)
        await interaction.response.send_message("Staff channel set", ephemeral=True)
        await log_moderation(interaction, settings.log_channel, "Staff channel set", f"<#{interaction.channel.id}>")
    
    @settings.subcommand(name="set_register", description="Set which channel is intended for registry")
    async def settings_set_register_select(self, interaction: nextcord.Interaction):
        settings = await self.bot.settings_cache(interaction.guild.id)
        if settings and settings.register_channel and settings.register_message:
            channel = interaction.guild.get_channel(settings.register_channel)
            if channel:
                try: msg = await channel.fetch_message(settings.register_message)
                except nextcord.errors.NotFound: pass
                else: await msg.delete()
        
        embed = nextcord.Embed(
            title="Register for Match Making!", 
            description=f"""## Welcome to Pavlov Match Making!

-# **If you believe to have registered once in the past, simply press the `Join/Leave` button to regain mm access.**

1. Press `Register` and sign in with the account you count on playing with. 
 - This process will link your steam64 id with your discord id. 
 - Information pertaining to your account is not stored and is handleded for the least amount of time possible.
2. Select your playing region for optimal server matching.
3. Queue up for the next match in <#{settings.mm_queue_channel}>. 
 - You can also be automatically notified with the </pingme:1358358003136594054> command. 

 X. If you find yourself enjoying the services provided in this server and wish to support the continuous development and maintenance of this community-lead match making, you are invited to check out our [buymeacoffee page](https://buymeacoffee.com/oblivius) (there are special perks as well 😉).
""",

            color=VALORS_THEME1_2)
        view = RegistryButtonView(self.bot)
        msg = await interaction.channel.send(embed=embed, view=view)
        await self.bot.settings_cache(
            guild_id=interaction.guild.id, about:blank#blocked
            register_channel=interaction.channel.id, 
            register_message=msg.id)
        await interaction.response.send_message("Registry channel set", ephemeral=True)
        await log_moderation(interaction, settings.log_channel, "Register buttons set", f"<#{interaction.channel.id}>")
    
    @settings.subcommand(name="set_regions", description="Set regions with geographical coordinates")
    async def set_regions(self, interaction: nextcord.Interaction, 
        regions: nextcord.Attachment=nextcord.SlashOption(description="JSON file with region data including coordinates")
    ):
        try:
            file = await regions.read()
            regions_data: Dict[str, Dict[str, str | float]] = json.loads(file)
        except Exception:
            return await interaction.response.send_message(
                "The file you provided did not contain valid JSON. Format example:\n"
                "```json\n"
                "{\n"
                "  \"NAE\": {\n"
                "    \"emoji\": \"🇺🇸\",\n"
                "    \"lat\": 36.0466,\n"
                "    \"lon\": -86.6444,\n"
                "    \"height\": 50.0\n"
                "  },\n"
                "  \"EUW\": {\n"
                "    \"emoji\": \"🇪🇺\",\n"
                "    \"lat\": 48.8594,\n"
                "    \"lon\": 2.3507,\n"
                "  }\n"
                "}\n```", 
                ephemeral=True)
        
        if len(regions_data) > 25:
            return await interaction.response.send_message(
                "Failed. Too many regions", ephemeral=True)
        
        guild_id = interaction.guild_id
        if not guild_id: return
        
        existing_regions = await self.bot.store.get_regions(guild_id)
        new_regions: List[Dict[str, str | float | None]] = []
        
        for n, (label, data) in enumerate(regions_data.items()):
            try:
                new_regions.append({
                    "emoji": data.get("emoji", ""),
                    "index": n,
                    "base_latitude": data["lat"],
                    "base_longitude": data["lon"],
                    "base_height": data.get("height")
                })
            except KeyError:
                return await interaction.response.send_message(
                    f"Region `{label}` requires both longitude and latitude values.", ephemeral=True)
        
        removed_labels = {region.label for region in existing_regions} - set(regions_data.keys())
        for label in removed_labels:
            await self.bot.store.null_user_region(guild_id, label)
            await self.bot.store.remove(BotRegions, guild_id=guild_id, label=label)
        
        for n, region in enumerate(new_regions):
            await self.bot.store.upsert(BotRegions, guild_id=guild_id, label=label, index=n, **region)
        
        log.debug(f"{interaction.user.display_name} set regions with geographic data:")
        log.pretty(regions_data)
        
        await interaction.response.send_message(f"Regions set with geographic data", ephemeral=True)
        
        settings = await self.bot.settings_cache(guild_id)
        await log_moderation(interaction, cast(int, settings.log_channel), 
            "Regions set with geographic data", f"```\n{', '.join(regions_data.keys())}```")

    @settings.subcommand(name="get_regions", description="Get current regions with geographic data")
    async def get_regions(self, interaction: nextcord.Interaction):
        regions = await self.bot.store.get_regions(guild_id=interaction.guild_id)
        regions_dict = {}
        
        for region in regions:
            regions_dict[region.label] = {
                "emoji": region.emoji,
                "base_latitude": region.base_latitude,
                "base_longitude": region.base_longitude,
                "base_height": region.base_height
            }
        
        json_str = json.dumps(regions_dict, indent=4)
        json_bytes = json_str.encode('utf-8')
        json_file = BytesIO(json_bytes)
        json_file.seek(0)
        file = nextcord.File(json_file, filename="regions_geo.json")
        
        await interaction.response.send_message(
            f"Here are the current regions with geographic data:\n_Edit and upload with_ "
            f"{await self.bot.command_cache.get_command_mention(interaction.guild_id, 'settings set_regions_geo')}", 
            file=file, ephemeral=True)

    
    @settings.subcommand(name="add_server", description="Add a pavlov server")
    async def add_server(self, interaction: nextcord.Interaction, 
        host: str=nextcord.SlashOption(required=True, description="Server address"),
        port: int=nextcord.SlashOption(min_value=0, max_value=65535, required=True, description="Server port"),
        password: str=nextcord.SlashOption(required=True, description="Server rcon password"),
        region: str=nextcord.SlashOption(required=True)
    ):
        if await self.bot.store.get_server(host, port):
            return await interaction.response.send_message(
                f"Server `{host}`:`{port}` is already added", ephemeral=True)
        await self.bot.store.add_server(host, port, password, region)
        log.debug(f"{interaction.user.display_name} added an rcon server {host}:{port} password:{password} region:{region}")
        await interaction.response.send_message(
            f"`{region}` Server `{host}`:`{port}` added successfully.", ephemeral=True)
        settings = await self.bot.settings_cache(interaction.guild.id)
        await log_moderation(interaction, settings.log_channel, "RCON Server added", f"{host}:{port}")

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
        await self.bot.store.remove_server(host, int(port))
        log.debug(f"{interaction.user.display_name} removed an rcon server {serveraddr}")
        await interaction.response.send_message(
            f"Server `{host}`:`{port}` removed successfully.", ephemeral=True)
        settings = await self.bot.settings_cache(interaction.guild.id)
        await log_moderation(interaction, settings.log_channel, "RCON Server removed", f"{host}:{port}")

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
        
        role_id_to_name = {role.id: role.name for role in interaction.guild.roles}
        
        ranks_dict = {}
        for rank in ranks:
            role_name = role_id_to_name.get(rank.role_id, f"Unknown Role ({rank.role_id})")
            ranks_dict[role_name] = { "mmr_threshold": rank.mmr_threshold, "role_id": rank.role_id }
        
        json_str = json.dumps(ranks_dict, indent=4)
        json_bytes = json_str.encode('utf-8')
        json_file = BytesIO(json_bytes)
        json_file.seek(0)
        file = nextcord.File(json_file, filename="mmr_ranks.json")
        await interaction.response.send_message(
            f"Here are the current ranks:\n_edit and upload with_ {await self.bot.command_cache.get_command_mention(interaction.guild.id, 'ranks set_ranks')}", file=file, ephemeral=True)

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
            f"Ranks set successfully. Use {await self.bot.command_cache.get_command_mention(interaction.guild.id, 'settings get_ranks')} to view them.", ephemeral=True)
        settings = await self.bot.settings_cache(interaction.guild.id)
        await log_moderation(interaction, settings.log_channel, "Ranks set", f"```\n{ranks}```")

    @settings.subcommand(name="set_leaderboard", description="Set the channel and leaderboard message")
    async def set_leaderboard(self, interaction: nextcord.Interaction):
        await interaction.response.defer(ephemeral=True)
        settings = await self.bot.settings_cache(guild_id=interaction.guild.id, leaderboard_channel=interaction.channel.id)
        await update_leaderboard(self.bot.store, interaction.guild)
        await interaction.followup.send(
            f"Match Making Leaderboard set", ephemeral=True)
        await log_moderation(interaction, settings.log_channel, "Leaderboard channel set", f"<#{interaction.channel.id}>")

    @nextcord.slash_command(name="change_mmr", description="Change a member's Match Making Rating", guild_ids=[*GUILD_IDS])
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
        settings = await self.bot.settings_cache(interaction.guild.id)
        await log_moderation(interaction, settings.log_channel, "Member mmr adjusted", f"{user.mention}\nbefore: {old_mmr}\nafter: {new_mmr}")
    
    @nextcord.slash_command(name="manual_register", description="Manually register a guild member with a platform ID", guild_ids=[*GUILD_IDS])
    async def manual_register(self,
        interaction: nextcord.Interaction,
        user: nextcord.Member = nextcord.SlashOption(description="The user to register"),
        platform: str = nextcord.SlashOption(description="The platform to register for"),
        platform_id: str = nextcord.SlashOption(description="The platform ID to register")
    ):
        settings = await self.bot.settings_cache(interaction.guild.id)
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
        await log_moderation(interaction, settings.log_channel, "Member manually registered", f"{user.mention}")

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
    
    @settings.subcommand(name="transfer_user_data", description="Transfer all of a discord user's data to another discord account")
    async def settings_transfer_user(self, interaction: nextcord.Interaction, old_user_id, new_user_id):
        settings = await self.bot.settings_cache(interaction.guild.id)
        try:
            await self.bot.store.transfer_user(interaction.guild.id, int(old_user_id), int(new_user_id))
        except Exception as e:
            await log_moderation(interaction, settings.log_channel, "User data transfer", f"User <@{old_user_id}> FAILED to move to <@{new_user_id}>.")
            return await interaction.response.send_message(f"There was a failure in the transfer:\n{repr(e)}", ephemeral=True)

        await interaction.response.send_message(f"User <@{old_user_id}> was moved to <@{new_user_id}> with success!", ephemeral=True)
        await log_moderation(interaction, settings.log_channel, "User data transfer", f"User <@{old_user_id}> was moved to <@{new_user_id}> with success!")
    
    @settings.subcommand(name="transfer_guild_data", description="Transfer all data to another guild")
    async def settings_transfer_guild(self, interaction: nextcord.Interaction, new_guild_id):
        settings = await self.bot.settings_cache(interaction.guild.id)
        try:
            await self.bot.store.transfer_guild_data(interaction.guild.id, int(new_guild_id))
        except Exception as e:
            await log_moderation(interaction, settings.log_channel, "Guild data transfer", f"Guild FAILED to move.")
            return await interaction.response.send_message(f"There was a failure in the transfer:\n{repr(e)}", ephemeral=True)

        await interaction.response.send_message(f"Guild was moved to guild {new_guild_id} with success!", ephemeral=True)
        await log_moderation(interaction, settings.log_channel, "Guild data transfer", f"Guild was moved to {new_guild_id} with success!")


def setup(bot):
    bot.add_cog(Settings(bot))