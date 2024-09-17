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

import asyncio
import json
from datetime import datetime
from io import BytesIO

import nextcord
import pytz
from nextcord.ext import commands, tasks

from config import *
from matches import cleanup_match, get_match, load_ongoing_matches
from matches.functions import calculate_mmr_change
from utils.logger import Logger as log
from utils.models import BotSettings, Team, Side
from utils.utils import abandon_cooldown, format_duration, generate_score_image, log_moderation
from views.match.abandon import AbandonView
from views.match.accept import AcceptView
from views.match.banning import BanView
from views.match.map_pick import MapPickView
from views.match.side_pick import SidePickView


class Matches(commands.Cog):
    @tasks.loop(seconds=60)
    async def rotate_map_pool(self):
        now = datetime.now(pytz.timezone('US/Eastern'))
        if now.minute == 00 and now.hour % 8 == 0:
            await self.bot.store.shuffle_map_order(GUILD_ID)

    @rotate_map_pool.before_loop
    async def wait_rotate_map_pool(self):
        await self.bot.wait_until_ready()

    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(AcceptView(self.bot))
        self.bot.add_view(AbandonView(self.bot))
        self.bot.add_view(BanView.create_dummy_persistent(self.bot))
        self.bot.add_view(MapPickView.create_dummy_persistent(self.bot))
        self.bot.add_view(SidePickView.create_dummy_persistent(self.bot))
        self.rotate_map_pool.start()
        
        log.info("Cog started")

        matches = await self.bot.store.get_ongoing_matches()
        loop = asyncio.get_event_loop()
        load_ongoing_matches(loop, self.bot, GUILD_ID, matches)
    
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: nextcord.Member, before: nextcord.VoiceState, after: nextcord.VoiceState):
        match_stages = self.bot.match_stages
        if after.channel.id in match_stages and member.id in match_stages[after.channel.id]:
            asyncio.create_task(member.edit(suppress=False))
            

    #####################
    # MM SLASH COMMANDS #
    #####################

    @nextcord.slash_command(name="cancel", description="Cancel a match", guild_ids=[GUILD_ID])
    async def mm_cancel(self, interaction: nextcord.Interaction, match_id: int=nextcord.SlashOption(default=-1, required=False)):
        settings: BotSettings = await self.bot.store.get_settings(interaction.guild.id)
        staff_role = interaction.guild.get_role(settings.mm_staff_role)
        if staff_role and not staff_role in interaction.user.roles:
            msg = await interaction.response.send_message("Missing permissions", ephemeral=True)
            await asyncio.sleep(1)
            await msg.delete()
            return
        if match_id == -1:
            match = await self.bot.store.get_match_channel(interaction.channel.id)
            if match: match_id = match.id
        else:
            match = await self.bot.store.get_match(match_id)
            if not match:
                return await interaction.response.send_message(f"There is no match #{match_id}", ephemeral=True)
        
        loop = asyncio.get_event_loop()
        if not await cleanup_match(loop, match_id):
            log.debug(f"{interaction.user.display_name} failed to cancel match {match_id}")
            return await interaction.response.send_message(
                f"Match id `{match_id}` failed to cleanup", ephemeral=True)
        log.debug(f"{interaction.user.display_name} canceled match {match_id}")
        await interaction.response.send_message(
            f"Match id {match_id} cleaning up", ephemeral=True)
        
        settings = await self.bot.store.get_settings(interaction.guild.id)
        scores_channel = interaction.guild.get_channel(settings.mm_log_channel)
        if not scores_channel: return
        scores_message = await scores_channel.fetch_message(match.log_message)
        if not scores_message: return
        embed = scores_message.embeds[0]
        embed.description = "Match canceled"
        await scores_message.edit(embed=embed)

        await log_moderation(interaction, settings.log_channel, "Match canceled")
    
    @nextcord.slash_command(name="abandon", description="Abandon a match", guild_ids=[GUILD_ID])
    async def mm_abandon(self, interaction: nextcord.Interaction):
        match = await self.bot.store.get_match_channel(interaction.channel.id)
        if not match:
            return await interaction.response.send_message(
                "You must use this command in a match channel", ephemeral=True)

        previous_abandons, _ = await self.bot.store.get_abandon_count_last_period(interaction.guild.id, interaction.user.id)       
        cooldown = abandon_cooldown(previous_abandons + 1)

        match_instance = get_match(match.id)
        player = next((player for player in match_instance.players if player.user_id == interaction.user.id), None)
        if not player:
            return await interaction.response.send_message("You cannot abandon if you are not in a match", ephemeral=True)
        ally_mmr = match.a_mmr if player.team == Team.A else match.b_mmr
        enemy_mmr = match.b_mmr if player.team == Team.A else match.a_mmr

        played_games = await self.bot.store.get_user_played_games(interaction.user.id, interaction.guild.id)
        mmr_loss = calculate_mmr_change(
            {}, 
            abandoned=True, 
            ally_team_avg_mmr=ally_mmr if ally_mmr else 0, 
            enemy_team_avg_mmr=enemy_mmr if enemy_mmr else 0, 
            placements=played_games <= PLACEMENT_MATCHES)
        embed = nextcord.Embed(
            title="Abandon", 
            description=f"""Are you certain you want to abandon this match?
_You abandoned a total of `{previous_abandons}` times in the last 2 months._
_You will have a cooldown of `{format_duration(cooldown)}` and lose `{mmr_loss}` mmr_""")
        await interaction.response.send_message(embed=embed, view=AbandonView(self.bot, match), ephemeral=True)

    @nextcord.slash_command(name="last_match", description="Display stats from the last match", guild_ids=[GUILD_ID])
    async def display_last_match(self, interaction: nextcord.Interaction):
        settings = await self.bot.store.get_settings(interaction.guild.id)
        ephemeral = interaction.channel.id != settings.mm_text_channel
        await interaction.response.defer(ephemeral=ephemeral)

        last_match = await self.bot.store.get_last_match(interaction.guild.id)
        if not last_match:
            return await interaction.followup.send("No completed matches found.", ephemeral=True)

        match_stats = await self.bot.store.get_match_stats(last_match.id)
        if not match_stats:
            return await interaction.followup.send("No stats found for the last match.", ephemeral=True)

        try:
            leaderboard_image = await generate_score_image(self.bot.cache, interaction.guild, last_match, match_stats)
            file = nextcord.File(BytesIO(leaderboard_image), filename=f"Match_{last_match.id}_leaderboard.png")
            await interaction.followup.send(ephemeral=ephemeral, file=file)

        except Exception as e:
            log.error(f"Error in displaying last match stats: {repr(e)}")
            await interaction.followup.send("An error occurred while generating the match stats.", ephemeral=True)

    @nextcord.slash_command(name="revoke_abandon", description="Revoke a user's current abandon", guild_ids=[GUILD_ID])
    async def revoke_abandon(self, interaction: nextcord.Interaction, user: nextcord.Member | nextcord.User):
        count_abandons, last_abandon = await self.bot.store.get_abandon_count_last_period(interaction.guild.id, user.id)
        cooldown = abandon_cooldown(count_abandons, last_abandon)
        if cooldown == 0:
            return await interaction.response.send_message("This user is not currently in cooldown", ephemeral=True)
        await self.bot.store.ignore_abandon(interaction.guild.id, user.id)
        log.debug(f"{interaction.user.display_name} revoked {user.display_name}'s abandon")
        await interaction.response.send_message(f"{user.mention} had their cooldown revoked successfully.", ephemeral=True)


    ###########################
    # MM SETTINGS SUBCOMMANDS #
    ###########################
    @nextcord.slash_command(name="mm", description="Match making commands", guild_ids=[GUILD_ID])
    async def match_making(self, interaction: nextcord.Interaction):
        pass

    @match_making.subcommand(name="settings", description="Match making settings")
    async def mm_settings(self, interaction: nextcord.Interaction):
        pass

    @mm_settings.subcommand(name="shuffle_maps", description="Shuffle the order of maps in the pool")
    async def shuffle_map_pool(self, interaction: nextcord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            await self.bot.store.shuffle_map_order(interaction.guild.id)
            shuffled_maps = await self.bot.store.get_maps(guild_id=interaction.guild.id)
            map_list = [m.map for m in shuffled_maps]
            
            log.debug(f"{interaction.user.display_name} shuffled the map pool:")
            
            await interaction.followup.send(
                f"Maps have been successfully shuffled. New order:\n`{', '.join(map_list)}`", ephemeral=True)
        except Exception as e:
            log.error(f"Error shuffling maps: {repr(e)}")
            await interaction.followup.send(
                "An error occurred while shuffling the maps.", ephemeral=True)
        
        settings: BotSettings = await self.bot.store.get_settings(interaction.guild.id)
        await log_moderation(interaction, settings.log_channel, "Map pool shuffled", f"New order:\n```\n{', '.join(map_list)}```")

    @mm_settings.subcommand(name="accept_period", description="Set match accept period")
    async def set_mm_accept_period(self, interaction: nextcord.Interaction, 
        seconds: int=nextcord.SlashOption(min_value=0, max_value=1800)):
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, mm_accept_period=seconds)
        log.debug(f"{interaction.user.display_name} set the accept period to:")
        log.pretty(seconds)
        await interaction.response.send_message(f"Accept period set to `{format_duration(seconds)}`", ephemeral=True)

        settings: BotSettings = await self.bot.store.get_settings(interaction.guild.id)
        await log_moderation(interaction, settings.log_channel, "Accept period changed", f"{format_duration(seconds)}")
    
    @set_mm_accept_period.on_autocomplete("seconds")
    async def autocomplete_accept_period(self, interaction: nextcord.Interaction, seconds):
        settings = await self.bot.store.get_settings(interaction.guild.id)
        if not seconds or not settings.mm_queue_periods:
            return await interaction.response.send_autocomplete(choices=[180])
        await interaction.response.send_autocomplete(choices=[seconds, settings.mm_accept_period])

    @mm_settings.subcommand(name="map_options", description="Set how many maps are revealed for pick and bans")
    async def set_maps_range(self, interaction: nextcord.Interaction, size: int=nextcord.SlashOption(min_value=3, max_value=10)):
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, mm_maps_range=size)
        await interaction.response.send_message(f"Match making set to {size} maps range", ephemeral=True)

        settings: BotSettings = await self.bot.store.get_settings(interaction.guild.id)
        await log_moderation(interaction, settings.log_channel, "Map options changed", f"{size}")
    
    @mm_settings.subcommand(name="set_maps", description="Choose what maps go into the match making pool")
    async def set_map_pool(self, interaction: nextcord.Interaction, 
        maps: nextcord.Attachment=nextcord.SlashOption(description="Json string for map name and image url (ordered)")):
        try:
            file = await maps.read()
            m = json.loads(file)
        except Exception:
            return await interaction.response.send_message(
                "The file you provided did not contain a valid json string\ne.g. `{\"Dust 2\": \"https://image.img\",}`", ephemeral=True)
        
        settings = await self.bot.store.get_settings(interaction.guild.id)
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, mm_maps_range=min(settings.mm_maps_range, len(m)), mm_maps_phase=0)
        await self.bot.store.set_maps(guild_id=interaction.guild.id, maps=[(k, v) for k, v in m.items()])
        log.debug(f"{interaction.user.display_name} set the map pool to:")
        log.pretty(m)
        await interaction.response.send_message(
            f"Maps successfully set to `{', '.join([k for k in m.keys()])}`", ephemeral=True)
        
        await log_moderation(interaction, settings.log_channel, "Map pool changed", f"New pool:\n```\n{', '.join([k for k in m.jeys()])}```")
    
    @mm_settings.subcommand(name="get_maps", description="Get the current map pool with their media")
    async def get_map_pool(self, interaction: nextcord.Interaction):
        maps = await self.bot.store.get_maps(guild_id=interaction.guild.id)
        map_dict = {
            m.map: {"media": m.media, "resource_id": m.resource_id}
            for m in maps
        }
        
        json_str = json.dumps(map_dict, indent=4)
        json_bytes = json_str.encode('utf-8')
        json_file = BytesIO(json_bytes)
        json_file.seek(0)
        file = nextcord.File(json_file, filename="map_pool.json")
        
        await interaction.response.send_message(
            f"Here is the current map pool:\n_edit and upload with_ {await self.bot.command_cache.get_command_mention(interaction.guild.id, 'queue settings set_maps')}>", file=file, ephemeral=True)
        
    @mm_settings.subcommand(name="set_mods", description="Choose what mods are added to match making")
    async def set_mods(self, interaction: nextcord.Interaction, 
        mods: nextcord.Attachment=nextcord.SlashOption(description="Json string for mod name and resource_id")):
        try:
            file = await mods.read()
            m = json.loads(file)
        except Exception:
            return await interaction.response.send_message(
                "The file you provided did not contain a valid json string\ne.g. `{\"RconPlus\": \"UGC3462586\",}`", ephemeral=True)
        
        await self.bot.store.set_mods(guild_id=interaction.guild.id, mods=[(k, v) for k, v in m.items()])
        log.debug(f"{interaction.user.display_name} set the mods to:")
        log.pretty(m)
        await interaction.response.send_message(
            f"Mods successfully set to `{', '.join([k for k in m.keys()])}`", ephemeral=True)
        
        settings = await self.bot.store.get_settings(interaction.guild.id)
        await log_moderation(interaction, settings.log_channel, "Mod list changed", f"New mods:\n```\n{', '.join([k for k in m.jeys()])}```")
    
    @mm_settings.subcommand(name="get_mods", description="Get the current mods with their ids")
    async def get_mods(self, interaction: nextcord.Interaction):
        mods = await self.bot.store.get_mods(guild_id=interaction.guild.id)
        mod_dict = {
            m.mod: {"resource_id": m.resource_id}
            for m in mods
        }
        
        json_str = json.dumps(mod_dict, indent=4)
        json_bytes = json_str.encode('utf-8')
        json_file = BytesIO(json_bytes)
        json_file.seek(0)
        file = nextcord.File(json_file, filename="mods.json")
        
        await interaction.response.send_message(
            f"Here are the current mods:\n_edit and upload with_ {await self.bot.command_cache.get_command_mention(interaction.guild.id, 'mm settings set_mods')}", file=file, ephemeral=True)


def setup(bot):
    bot.add_cog(Matches(bot))
