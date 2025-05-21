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

import nextcord
from functools import partial
from nextcord.ext import commands
from typing import List, TYPE_CHECKING, cast
from collections import Counter
if TYPE_CHECKING:
    from main import Bot
    from ...matches.match import Match

from utils.logger import Logger as log
from utils.models import MMBotMatches, MMBotUserMapPicks, Phase, Team, MMBotMaps
from utils.utils import shifted_window


class MapPickView(nextcord.ui.View):
    def __init__(self, bot: "Bot", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot

    @classmethod
    def create_dummy_persistent(cls, bot: "Bot"):
        instance = cls(bot, timeout=None)
        for slot_id in range(20):
            button = nextcord.ui.Button(label="dummy button", custom_id=f"mm_map_picks:{slot_id}")
            button.callback = partial(instance.pick_callback, button)
            instance.add_item(button)
        return instance
    
    @classmethod
    async def create_showable(cls, bot: "Bot", match: MMBotMatches, available_maps: List[MMBotMaps], banned_maps: List[str]):
        instance = cls(bot, banned_maps, timeout=None)
        instance.stop()
        
        picks = await instance.bot.store.get_map_votes(match.id)
        pick_counts = Counter(picks)

        for n, m in enumerate(available_maps):
            if m.map in banned_maps: continue
            button = nextcord.ui.Button(
                label=f"{m.map}: {pick_counts.get(m.map, 0)}", 
                style=nextcord.ButtonStyle.green, 
                custom_id=f"mm_map_picks:{n}")
            instance.add_item(button)
        return instance
    
    async def update_picks_message(self, interaction: nextcord.Interaction, instance: 'Match', match: MMBotMatches):
        banned_maps = await instance.bot.store.get_bans(match.id)
        view = await self.create_showable(self.bot, match, instance.available_maps, banned_maps)
        await interaction.edit(view=view)

    async def pick_callback(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        # what phase
        match = await self.bot.store.get_match_from_channel(interaction.channel.id)
        if match.phase != Phase.A_PICK:
            return await interaction.response.send_message("This button is no longer in use", ephemeral=True)
        
        from matches import get_match
        instance = get_match(match.id)
        assert(instance is not None)
        
        if not (player := next((p for p in instance.players if cast(int, p.user_id) == interaction.user.id), None)):
            return await interaction.response.send_message("You are not a player in this match", ephemeral=True)
        if cast(Team, player.team) != Team.A:
            return await interaction.response.send_message(f"Only Team A can pick the map.", ephemeral=True)
        
        user_picks = await self.bot.store.get_user_map_picks(match.id, interaction.user.id)
                
        # what button
        slot_id = int(button.custom_id.split(':')[-1])
        picked_map = instance.available_maps[slot_id].map
        
        await self.bot.store.remove(MMBotUserMapPicks, 
            match_id=match.id, 
            user_id=interaction.user.id)
        if picked_map not in user_picks:
            # vote this one
            await self.bot.store.insert(MMBotUserMapPicks, 
                guild_id=interaction.guild.id, 
                user_id=interaction.user.id, 
                match_id=match.id, 
                map=picked_map)
            log.info(f"{interaction.user.display_name} voted to pick {picked_map}")
        
        await self.bot.debounce(self.update_picks_message, interaction, instance, match)


class ChosenMapView(nextcord.ui.View):
    def __init__(self, pick: str):
        super().__init__(timeout=0)

        self.add_item(
            nextcord.ui.Button(
                label=f"{pick}", 
                style=nextcord.ButtonStyle.green,
                disabled=True))
