# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # 
# VALORS Match Making Bot is a discord based match making automation and management service #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # 
# 
# Copyright (C) 2024 99oblivius, <projects@oblivius.dev>
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

import nextcord
from functools import partial
from nextcord.ext import commands

from utils.logger import Logger as log
from utils.models import MMBotMatches, MMBotUserMapPicks, Phase
from utils.utils import shifted_window


class MapPickView(nextcord.ui.View):
    def __init__(self, bot, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timeout = None
        self.bot: commands.Bot = bot

    @classmethod
    def create_dummy_persistent(cls, bot: commands.Bot):
        instance = cls(bot, timeout=None)
        for slot_id in range(10):
            button = nextcord.ui.Button(label="dummy button", custom_id=f"mm_map_picks:{slot_id}")
            button.callback = partial(instance.pick_callback, button)
            instance.add_item(button)
        return instance
    
    @classmethod
    async def create_showable(cls, bot: commands.Bot, guild_id: int, match: MMBotMatches):
        instance = cls(bot, timeout=None)
        instance.stop()

        banned_maps = await instance.bot.store.get_bans(match.id)
        maps = await instance.bot.store.get_map_vote_count(guild_id, match.id)
        picks = shifted_window(maps, match.maps_phase, match.maps_range)
        for n, (m, count) in enumerate(picks):
            if m in banned_maps:
                continue
            button = nextcord.ui.Button(
                label=f"{m}: {count}", 
                style=nextcord.ButtonStyle.green, 
                custom_id=f"mm_map_picks:{n}")
            button.callback = partial(instance.pick_callback, button)
            instance.add_item(button)
        return instance

    async def pick_callback(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        # what phase
        match = await self.bot.store.get_thread_match(interaction.channel.id)
        if match.phase != Phase.A_PICK:
            return await interaction.response.send_message("This button is no longer in use", ephemeral=True)
        # what button
        maps = await self.bot.store.get_maps(interaction.guild.id)
        settings = await self.bot.store.get_settings(interaction.guild.id)
        pick_maps = shifted_window([m.map for m in maps], settings.mm_maps_phase, settings.mm_maps_range)
        slot_id = int(button.custom_id.split(':')[-1])
        
        user_picks = await self.bot.store.get_user_map_pick(match.id, interaction.user.id)
        await self.bot.store.remove(MMBotUserMapPicks, 
            match_id=match.id, 
            user_id=interaction.user.id)
        if pick_maps[slot_id] not in user_picks:
            # vote this one
            await self.bot.store.insert(MMBotUserMapPicks, 
                guild_id=interaction.guild.id, 
                user_id=interaction.user.id, 
                match_id=match.id, 
                map=pick_maps[slot_id])
            log.debug(f"{interaction.user.display_name} voted to pick {pick_maps[slot_id]}")
        view = await self.create_showable(self.bot, interaction.guild.id, match)
        await interaction.edit(view=view)

class ChosenMapView(nextcord.ui.View):
    def __init__(self, pick: str):
        super().__init__(timeout=0)

        self.add_item(
            nextcord.ui.Button(
                label=f"{pick}", 
                style=nextcord.ButtonStyle.green,
                disabled=True))
