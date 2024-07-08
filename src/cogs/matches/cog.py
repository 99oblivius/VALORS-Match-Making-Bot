# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # 
# VALORS Match Making Bot is a discord based match making automation and management service #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # 
# 
# Copyright (C) 2024  Julian von Virag, <projects@oblivius.dev>
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import json
from utils.logger import Logger as log
from io import BytesIO
import asyncio
from datetime import datetime
import pytz

import nextcord
from nextcord.ext import commands, tasks

from config import *
from utils.models import BotSettings, Team
from utils.utils import format_duration, abandon_cooldown
from matches import load_ongoing_matches, cleanup_match, get_match

from views.match.accept import AcceptView
from views.match.banning import BanView
from views.match.map_pick import MapPickView
from views.match.side_pick import SidePickView
from views.match.abandon import AbandonView
from matches.functions import calculate_mmr_change


class Matches(commands.Cog):
    @tasks.loop(seconds=60)
    async def rotate_map_pool(self):
        now = datetime.now(pytz.timezone('US/Eastern'))
        if now.minute == 00 and now.hour == 00:
            settings = await self.bot.store.get_settings(GUILD_ID)
            maps = await self.bot.store.get_maps(GUILD_ID)
            new_phase = (settings.mm_maps_phase - 1) % len(maps)
            await self.bot.store.upsert(BotSettings, guild_id=GUILD_ID, mm_maps_phase=new_phase)

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

    #####################
    # MM SLASH COMMANDS #
    #####################

    @nextcord.slash_command(name="cancel", description="Cancel a match")
    async def mm_cancel(self, interaction: nextcord.Interaction, match_id: int=nextcord.SlashOption(default=-1, required=False)):
        settings = await self.bot.store.get_settings(interaction.guild.id)
        staff_role = interaction.guild.get_role(settings.mm_staff_role)
        if staff_role and not staff_role in interaction.user.roles:
            msg = await interaction.response.send_message("Missing permissions", ephemeral=True)
            await asyncio.sleep(1)
            await msg.delete()
            return
        if match_id == -1:
            match = await self.bot.store.get_thread_match(interaction.channel.id)
            if match: match_id = match.id
        
        loop = asyncio.get_event_loop()
        if not await cleanup_match(loop, match_id):
            log.debug(f"{interaction.user.display_name} failed to cancel match {match_id}")
            return await interaction.response.send_message(
                f"Match id `{match_id}` failed to cleanup", ephemeral=True)
        log.debug(f"{interaction.user.display_name} canceled match {match_id}")
        await interaction.response.send_message(
            f"Match id {match_id} cleaning up", ephemeral=True)
        
        settings = await self.bot.store.get_settings(interaction.guild.id)
        log_channel = interaction.guild.get_channel(settings.mm_log_channel)
        log_message = await log_channel.fetch_message(self.match.log_message)
        embed = log_message.embeds[0]
        embed.description = "Match canceled"
        await log_message.edit(embed=embed)
    
    @nextcord.slash_command(name="abandon", description="Abandon a match")
    async def mm_abandon(self, interaction: nextcord.Interaction):
        match = await self.bot.store.get_thread_match(interaction.channel.id)
        if not match:
            return await interaction.response.send_message(
                "You must use this command in a match thread", ephemeral=True)

        previous_abandons, _ = await self.bot.store.get_abandon_count_last_period(interaction.guild.id, interaction.user.id)       
        cooldown = abandon_cooldown(previous_abandons + 1)

        match_instance = get_match(match.id)
        player = next((player for player in match_instance.players if player.user_id == interaction.user.id), None)
        if not player:
            return await interaction.response.send_message("You cannot abandon if you are not in a match", ephemeral=True)
        ally_mmr = match.a_mmr if player.team == Team.A else match.b_mmr
        enemy_mmr = match.b_mmr if player.team == Team.A else match.a_mmr
        mmr_loss = calculate_mmr_change({}, abandoned=True, ally_team_avg_mmr=ally_mmr, enemy_team_avg_mmr=enemy_mmr)
        embed = nextcord.Embed(
            title="Abandon", 
            description=f"""Are you certain you want to abandon this match?
_You abandoned a total of `{previous_abandons}` times in the last 2 months._
_You will have a cooldown of `{format_duration(cooldown)}` and lose `{mmr_loss}` mmr_""")
        await interaction.response.send_message(embed=embed, view=AbandonView(self.bot, match), ephemeral=True)


    ###########################
    # MM SETTINGS SUBCOMMANDS #
    ###########################
    @nextcord.slash_command(name="mm", description="Match making commands", guild_ids=[GUILD_ID])
    async def match_making(self, interaction: nextcord.Interaction):
        pass

    @match_making.subcommand(name="revoke_abandon", description="Revoke a user's current abandon")
    async def revoke_abandon(self, interaction: nextcord.Interaction, user: nextcord.Member | nextcord.User):
        count_abandons, last_abandon = await self.bot.store.get_abandon_count_last_period(interaction.guild.id, user.id)
        cooldown = abandon_cooldown(count_abandons, last_abandon)
        if cooldown == 0:
            return await interaction.response.send_message("This user is not currently in cooldown", ephemeral=True)
        await self.bot.store.ignore_abandon(interaction.guild.id, user.id)
        log.debug(f"{interaction.user.display_name} revoked {user.display_name}'s abandon")
        await interaction.response.send_message(f"{user.mention} had their cooldown revoked successfully.", ephemeral=True)

    @match_making.subcommand(name="settings", description="Match making settings")
    async def mm_settings(self, interaction: nextcord.Interaction):
        pass

    @mm_settings.subcommand(name="accept_period", description="Set match accept period")
    async def set_mm_accept_period(self, interaction: nextcord.Interaction, 
        seconds: int=nextcord.SlashOption(min_value=0, max_value=1800)):
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, mm_accept_period=seconds)
        log.debug(f"{interaction.user.display_name} set the accept period to:")
        log.pretty(seconds)
        await interaction.response.send_message(f"Accept period set to `{format_duration(seconds)}`", ephemeral=True)
    
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
    
    @mm_settings.subcommand(name="get_maps", description="Get the current map pool with their media")
    async def get_map_pool(self, interaction: nextcord.Interaction):
        maps = await self.bot.store.get_maps(guild_id=interaction.guild.id)
        map_dict = {m.map: m.media for m in maps}
        
        json_str = json.dumps(map_dict, indent=4)
        json_bytes = json_str.encode('utf-8')
        json_file = BytesIO(json_bytes)
        json_file.seek(0)
        file = nextcord.File(json_file, filename="map_pool.json")
        
        await interaction.response.send_message(
            "Here is the current map pool:\n_edit and upload with_ </queue settings set_maps:1257503332952707173>", file=file, ephemeral=True)


def setup(bot):
    bot.add_cog(Matches(bot))
