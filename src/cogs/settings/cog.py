import json
from utils.logger import Logger as log
from io import BytesIO
import math
from functools import partial

from fuzzywuzzy import process

import nextcord
from nextcord.ext import commands

from config import *
from utils.models import BotSettings, MMBotRanks

from config import *
from views.register import RegistryButtonView

from utils.models import BotRegions, BotSettings
from utils.utils import ANSI_TARGET_COLORS


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

        def get_rank_color(mmr, ranks):
            def to_rgb(color):
                return ((color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF)

            def euclidean(c1, c2):
                r1, g1, b1 = to_rgb(c1)
                r2, g2, b2 = to_rgb(c2)
                return (r1-r2)**2 + (g1-g2)**2 + (b1-b2)**2

            def closest_color_code(color, target_colors=ANSI_TARGET_COLORS, dist=euclidean):
                return target_colors[min(target_colors, key=partial(dist, color))]

            sorted_ranks = sorted(ranks, key=lambda x: x.mmr_threshold, reverse=True)

            for rank in sorted_ranks:
                if mmr >= rank.mmr_threshold:
                    role = interaction.guild.get_role(rank.role_id)
                    if role and role.color:
                        color_code = closest_color_code(role.color.value)
                        return f"\u001b[1;{color_code}m"
            
            return "\u001b[1;30m"

        def create_leaderboard_embed(leaderboard_data, ranks):
            field_count = 0

            valid_scores = [player['avg_score'] for player in leaderboard_data if player['games'] > 0 and interaction.guild.get_member(player['user_id'])]
            avg_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0
            embed = nextcord.Embed(title="Match Making Leaderboard", description=f"{len(valid_scores)} ranking players\nK/D/A and Score are mean averages")

            ranking_position = 0
            for player in leaderboard_data:
                if field_count > 25: break
                if player['games'] == 0: continue

                member = interaction.guild.get_member(player['user_id'])
                if member is None: continue
                
                ranking_position += 1

                name = member.display_name[:11] + '…' if len(member.display_name) > 12 else member.display_name
                name = name.ljust(12)
                mmr = f"{math.floor(player['mmr'])}".rjust(4)
                games = f"{player['games']}".rjust(3)
                win_rate = math.floor(player['win_rate']*100)
                k = math.floor(player['avg_kills'])
                d = math.floor(player['avg_deaths'])
                a = math.floor(player['avg_assists'])
                score = math.floor(player['avg_score'])
                
                # Color coding
                rank_color = get_rank_color(float(mmr), ranks)
                win_rate_color = "\u001b[32m" if win_rate > 60 else "\u001b[31m" if win_rate < 40 else "\u001b[0m"
                score_color = "\u001b[32m" if score > avg_score else "\u001b[31m"
                
                kda = f"{k}/{d}/{a}".rjust(8)
                if k < d:
                    kda_formatted = kda.replace(str(d), f"\u001b[31m{d}\u001b[0m", 1)
                else:
                    kda_formatted = kda

                row = f"{ranking_position:3} | {name} | {rank_color}{mmr}\u001b[0m | {games} | {win_rate_color}{win_rate:3}%\u001b[0m | {kda_formatted} | {score_color}{score:2}\u001b[0m\n"
                
                if ranking_position % 5 == 1:
                    if ranking_position == 1:
                        header = "  R | Player       |  MMR |   G |  W%  |   K/D/A  | S  "
                        field_content = f"```ansi\n\u001b[1m{header}\u001b[0m\n{'─' * len(header)}\n{row}"
                    else:
                        field_content += "```"
                        embed.add_field(name="\u200b", value=field_content, inline=False)
                        field_content = f"```ansi\n{row}"
                    field_count += 1
                else:
                    field_content += row
            
            if field_content:
                field_content += "```"
                embed.add_field(name="\u200b", value=field_content, inline=False)
            
            return embed
        
        data = await self.bot.store.get_leaderboard(interaction.guild.id, limit=100)
        ranks = await self.bot.store.get_ranks(interaction.guild.id)
        embed = create_leaderboard_embed(data, ranks)
        msg = await interaction.channel.send(embed=embed)
        await self.bot.store.update(BotSettings, 
            guild_id=interaction.guild.id, 
            leaderboard_channel=interaction.channel.id, 
            leaderboard_message=msg.id)
        await interaction.response.send_message(
            f"Match Making Leaderboard set", ephemeral=True)


def setup(bot):
    bot.add_cog(Settings(bot))
