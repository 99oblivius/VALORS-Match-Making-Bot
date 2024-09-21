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
from typing import List

import nextcord
from nextcord.ext import commands

from utils.logger import Logger as log
from utils.models import MMBotMatches, MMBotUserBans, Phase
from utils.utils import shifted_window


class BanView(nextcord.ui.View):
    def __init__(self, bot, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot: commands.Bot = bot

    @classmethod
    def create_dummy_persistent(cls, bot: commands.Bot):
        instance = cls(bot, timeout=None)
        for slot_id in range(20):
            button = nextcord.ui.Button(label="dummy button", custom_id=f"mm_match_bans:{slot_id}")
            button.callback = partial(instance.ban_callback, button)
            instance.add_item(button)
        return instance
    
    @classmethod
    async def create_showable(cls, bot: commands.Bot, guild_id: int, match: MMBotMatches):
        instance = cls(bot, timeout=None)
        instance.stop()

        banned_maps = await instance.bot.store.get_bans(match.id)
        ban_counts = await instance.bot.store.get_ban_counts(guild_id, match.id, match.phase)
        last_played_map = await instance.bot.store.get_last_played_map(match.queue_channel)

        available_maps = [x for x in ban_counts if x[0] != last_played_map]
        available_maps = shifted_window(available_maps, match.maps_phase, match.maps_range)
        bans = (x for x in available_maps if x[0] not in banned_maps)
        for n, (m, count) in enumerate(bans):
            if m in banned_maps: continue
            button = nextcord.ui.Button(
                label=f"{m}: {count}", 
                style=nextcord.ButtonStyle.red, 
                custom_id=f"mm_match_bans:{n}")
            instance.add_item(button)
        return instance

    async def ban_callback(self, button: nextcord.ui.Button, interaction: nextcord.Integration):
        # what phase
        match = await self.bot.store.get_match_channel(interaction.channel.id)
        if not match.phase in (Phase.A_BAN, Phase.B_BAN):
            return await interaction.response.send_message("This button is no longer in use", ephemeral=True)
        # what button
        settings = await self.bot.store.get_settings(interaction.guild.id)
        banned_maps = await self.bot.store.get_bans(match.id)
        maps = await self.bot.store.get_maps(interaction.guild.id)
        user_bans = await self.bot.store.get_user_map_bans(match.id, interaction.user.id)
        last_played_map = await self.bot.store.get_last_played_map(match.queue_channel)

        available_maps = [m for m in maps if m.map != last_played_map]
        available_maps = shifted_window(available_maps, settings.mm_maps_phase, settings.mm_maps_range)
        bans = [m for m in available_maps if m.map not in banned_maps]
        slot_id = int(button.custom_id.split(':')[-1])
        
        if bans[slot_id] in user_bans:
            # already voted this one
            await self.bot.store.remove(MMBotUserBans, 
                guild_id=interaction.guild.id, 
                match_id=match.id, 
                user_id=interaction.user.id, 
                map=bans[slot_id])
            log.info(f"{interaction.user.display_name} removed ban vote for {bans[slot_id].map}")
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
                map=bans[slot_id].map, 
                phase=match.phase)
            log.info(f"{interaction.user.display_name} wants to ban {bans[slot_id].map}")
        view = await self.create_showable(self.bot, interaction.guild.id, match)
        await interaction.edit(view=view)


class ChosenBansView(nextcord.ui.View):
    def __init__(self, bans: List[str]):
        super().__init__(timeout=0)

        for ban in bans:
            self.add_item(
                nextcord.ui.Button(
                    label=f"{ban}", 
                    style=nextcord.ButtonStyle.red,
                    disabled=True))