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

import asyncio

import nextcord

from config import MATCH_PLAYER_COUNT
from utils.logger import Logger as log
from utils.models import *
from utils.utils import format_mm_attendance


class AcceptView(nextcord.ui.View):
    def __init__(self, bot, done_event=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.timeout = None
        self.done_event = done_event
    
    @nextcord.ui.button(
        label="Accept", 
        emoji="✅", 
        style=nextcord.ButtonStyle.green, 
        custom_id="mm_thread_accept_button")
    async def accept_button(self, button: nextcord.ui.Button, interaction: nextcord.Integration):
        match = await self.bot.store.get_thread_match(interaction.channel.id)
        players = await self.bot.store.get_players(match.id)
        if interaction.user.id in [p.user_id for p in players if p.accepted]:
            msg = await interaction.response.send_message(
                "You have already accepted the match.\nBut thank you for making sure :)", ephemeral=True)
            await asyncio.sleep(3)
            await msg.delete()
            return
        
        await self.bot.store.update(MMBotMatchPlayers, 
            guild_id=interaction.guild.id, match_id=match.id, user_id=interaction.user.id, accepted=True)
        log.debug(f"{interaction.user.display_name} accepted match {match.id}")
        players = await self.bot.store.get_players(match.id)
        
        embed = interaction.message.embeds[0]
        embed.set_field_at(0, name="Attendance", value=format_mm_attendance(players))
        await interaction.message.edit(embed=embed)
        msg = await interaction.response.send_message(
            "You accepted the match!", ephemeral=True)
        
        accepted_players = await self.bot.store.get_accepted_players(match.id)
        if accepted_players == MATCH_PLAYER_COUNT:
            self.done_event.set()
        
        await asyncio.sleep(3)
        await msg.delete()
