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

import nextcord
from typing import Optional, TYPE_CHECKING
if TYPE_CHECKING:
    from main import Bot

from config import MATCH_PLAYER_COUNT
from utils.logger import Logger as log
from utils.models import *
from utils.utils import format_mm_attendance


class AcceptView(nextcord.ui.View):
    def __init__(self, bot: "Bot", done_event: Optional[asyncio.Event]=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.timeout = None
        self.done_event = done_event
        self.lock = asyncio.Lock()
        self.accepted_players = []
    
    async def edit_presence(self, interaction: nextcord.Interaction, match_id: int):
        players = await self.bot.store.get_players(match_id)
        if not ((msg := interaction.message) and msg.embeds): return
        embed = interaction.message.embeds[0]
        embed.set_field_at(0, name="Attendance", value=format_mm_attendance(players))
        await interaction.edit(embed=embed)
    
    @nextcord.ui.button(
        label="Accept", 
        emoji="✅", 
        style=nextcord.ButtonStyle.green, 
        custom_id="mm_accept_button")
    async def accept_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        match = await self.bot.store.get_match_from_channel(interaction.channel.id)

        async with self.lock:
            await interaction.response.defer()
            players = await self.bot.store.get_players(match.id)
            if interaction.user.id not in [p.user_id for p in players]:
                return await interaction.followup.send("You are not in this match :(", ephemeral=True)
            if interaction.user.id in [p.user_id for p in players if p.accepted]:
                return await interaction.followup.send("You have already accepted the match.\nBut thank you for making sure :)", ephemeral=True)
            
            await self.bot.store.update(MMBotMatchPlayers, 
                guild_id=interaction.guild.id, match_id=match.id, user_id=interaction.user.id, accepted=True)
            log.info(f"{interaction.user.display_name} accepted match {match.id}")
            
            asyncio.create_task(interaction.followup.send("You accepted the match!", ephemeral=True))
            self.accepted_players = await self.bot.store.get_accepted_players(match.id)
            if len(self.accepted_players) == MATCH_PLAYER_COUNT:
                if self.done_event:
                    self.done_event.set()
            
            await self.bot.debounce(self.edit_presence, interaction, match.id)
