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

from utils.logger import Logger as log
from utils.models import MMBotMatches, MMBotUserSidePicks, Phase, Side


class SidePickView(nextcord.ui.View):
    def __init__(self, bot, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timeout = None
        self.bot: commands.Bot = bot

    @classmethod
    def create_dummy_persistent(cls, bot: commands.Bot):
        instance = cls(bot, timeout=None)

        button = nextcord.ui.Button(label="dummy button", custom_id=f"mm_side_picks:CT")
        button.callback = partial(instance.side_callback, button)
        instance.add_item(button)

        button = nextcord.ui.Button(label="dummy button", custom_id=f"mm_side_picks:T")
        button.callback = partial(instance.side_callback, button)
        instance.add_item(button)
        return instance
    
    @classmethod
    async def create_showable(cls, bot: commands.Bot, guild_id: int, match: MMBotMatches):
        instance = cls(bot, timeout=None)
        instance.stop()

        sides = await instance.bot.store.get_side_vote_count(guild_id, match.id)
        for side, count in sides:
            button = nextcord.ui.Button(
                label=f"{side.name}: {count}", 
                style=nextcord.ButtonStyle.blurple, 
                custom_id=f"mm_side_picks:{side.name}")
            button.callback = partial(instance.side_callback, button)
            instance.add_item(button)
        return instance
    
    async def side_callback(self, button: nextcord.ui.Button, interaction: nextcord.Integration):
        # what phase
        match = await self.bot.store.get_match_from_channel(interaction.channel.id)
        if match.phase != Phase.B_PICK:
            return await interaction.response.send_message("This button is no longer in use", ephemeral=True)
        
        user_pick = await self.bot.store.get_user_side_pick(match.id, interaction.user.id)
        await self.bot.store.remove(MMBotUserSidePicks, 
            match_id=match.id, 
            user_id=interaction.user.id)

        pick_slot = button.custom_id.split(':')[-1]
        if pick_slot == "T": pick = Side.T
        if pick_slot == "CT": pick = Side.CT
        if pick not in user_pick:
            # vote this one
            await self.bot.store.insert(MMBotUserSidePicks, 
                guild_id=interaction.guild.id, 
                user_id=interaction.user.id, 
                match_id=match.id, 
                side=pick)
            log.info(f"{interaction.user.display_name} voted for {pick.name}")
        view = await self.create_showable(self.bot, interaction.guild.id, match)
        await interaction.edit(view=view)

class ChosenSideView(nextcord.ui.View):
    def __init__(self, pick: Side):
        super().__init__(timeout=0)

        self.add_item(
            nextcord.ui.Button(
                label=f"{pick.name}", 
                style=nextcord.ButtonStyle.blurple,
                disabled=True))
