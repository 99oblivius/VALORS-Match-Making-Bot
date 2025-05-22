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

from functools import partial
from typing import List, TYPE_CHECKING, cast
from collections import Counter
if TYPE_CHECKING:
    from main import Bot
    from ...matches.match import Match

import nextcord

from utils.logger import Logger as log
from utils.models import MMBotMatches, MMBotUserBans, Phase, MMBotMaps, Team


class BanView(nextcord.ui.View):
    def __init__(self, bot: 'Bot', *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot

    @classmethod
    def create_dummy_persistent(cls, bot: 'Bot'):
        instance = cls(bot, timeout=None)
        for slot_id in range(20):
            button = nextcord.ui.Button(label="dummy button", custom_id=f"mm_match_bans:{slot_id}")
            button.callback = partial(instance.ban_callback, button)
            instance.add_item(button)
        return instance
    
    @classmethod
    async def create_showable(cls, bot: 'Bot', match: MMBotMatches, available_maps: List[MMBotMaps], banned_maps: List[str]):
        instance = cls(bot, timeout=None)
        instance.stop()
        
        bans = await instance.bot.store.get_ban_votes(match.id, match.phase)
        ban_counts = Counter(bans)
        
        for n, m in enumerate(available_maps):
            if m.map in banned_maps: continue
            button = nextcord.ui.Button(
                label=f"{m.map}: {ban_counts.get(m.map, 0)}", 
                style=nextcord.ButtonStyle.red, 
                custom_id=f"mm_match_bans:{n}")
            instance.add_item(button)
        return instance
    
    async def update_bans_message(self, interaction: nextcord.Interaction, instance: 'Match', match: MMBotMatches):
        banned_maps = await self.bot.store.get_bans(match.id)
        view = await self.create_showable(self.bot, match, instance.available_maps, banned_maps)
        await interaction.edit(view=view)

    async def ban_callback(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        await interaction.response.defer()
        match = await self.bot.store.get_match_from_channel(interaction.channel.id)
        if not match.phase in (Phase.A_BAN, Phase.B_BAN):
            return await interaction.response.send_message("This button is no longer in use", ephemeral=True)

        from matches import get_match
        instance = get_match(match.id)
        assert(instance is not None)
        
        if not (player := next((p for p in instance.players if cast(int, p.user_id) == interaction.user.id), None)):
            return await interaction.response.send_message("You are not a player in this match", ephemeral=True)
        if not ((cast(Phase, match.phase) == Phase.A_BAN and cast(Team, player.team) == Team.A)
            or (cast(Phase, match.phase) == Phase.B_BAN and cast(Team, player.team) == Team.B)
        ):
            team_name = "Team A" if match.phase == Phase.A_BAN else "Team B"
            return await interaction.response.send_message(f"It is {team_name}'s turn to ban.", ephemeral=True)
        
        
        # what button
        slot_id = int(button.custom_id.split(':')[-1])
        banned_map = instance.available_maps[slot_id].map
        
        user_bans = await self.bot.store.get_user_map_bans(match.id, interaction.user.id)
        if banned_map in user_bans:
            # already voted this one
            await self.bot.store.remove(MMBotUserBans, 
                guild_id=interaction.guild.id, 
                match_id=match.id, 
                user_id=interaction.user.id, 
                map=banned_map)
            log.info(f"{interaction.user.name} removed ban vote for {banned_map}")
        else:
            # already voted max times
            if len(user_bans) > 1:
                return await interaction.response.send_message("You already banned 2 maps", ephemeral=True)
            # vote this one
            if not match.phase in (Phase.A_BAN, Phase.B_BAN): return
            await self.bot.store.insert(MMBotUserBans, 
                guild_id=interaction.guild.id, 
                user_id=interaction.user.id, 
                match_id=match.id, 
                map=banned_map, 
                phase=match.phase)
            log.info(f"{interaction.user.name} wants to ban {banned_map}")
        
        await self.bot.debounce(self.update_bans_message, interaction, instance, match)


class ChosenBansView(nextcord.ui.View):
    def __init__(self, bans: List[str]):
        super().__init__(timeout=0)

        for ban in bans:
            self.add_item(
                nextcord.ui.Button(
                    label=f"{ban}", 
                    style=nextcord.ButtonStyle.red,
                    disabled=True))