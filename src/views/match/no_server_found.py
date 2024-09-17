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

from utils.logger import Logger as log
from utils.models import *
from matches.match_states import MatchState

class NoServerFoundView(nextcord.ui.View):
    def __init__(self, bot, match_id, done_event, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.match_id = match_id
        self.done_event = done_event
        self.timeout = None

    @nextcord.ui.button(
        label="Retry",
        emoji="🔄",
        style=nextcord.ButtonStyle.primary,
        custom_id="mm_refresh_button")
    async def refresh_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        settings = await self.bot.store.get_settings(interaction.guild.id)
        staff_role = interaction.guild.get_role(settings.mm_staff_role)
        if not interaction.user.guild_permissions.administrator or not staff_role in interaction.user.roles:
            return await interaction.response.send_message("This button is intended for staff use only.", ephemeral=True)
        log.info(f"Refresh button clicked for match {self.match_id}")
        await interaction.response.defer()

        from matches import go_back_to
        await go_back_to(asyncio.get_event_loop(), self.match_id, MatchState.MATCH_FIND_SERVER)
        self.done_event.set()

    @nextcord.ui.button(
        label="Terminate",
        emoji="🛑",
        style=nextcord.ButtonStyle.danger,
        custom_id="mm_terminate_button")
    async def terminate_button(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        settings = await self.bot.store.get_settings(interaction.guild.id)
        staff_role = interaction.guild.get_role(settings.mm_staff_role)
        if not interaction.user.guild_permissions.administrator or not staff_role in interaction.user.roles:
            return await interaction.response.send_message("This button is intended for staff use only.", ephemeral=True)
        await interaction.response.defer()
        from matches import cleanup_match
        if not await cleanup_match(asyncio.get_event_loop(), self.match_id):
            log.debug(f"{interaction.user.display_name} had an issue terminating match {self.match_id}")
            return await interaction.followup.send("Something went wrong. Try again...", ephemeral=True)
        
        match = await self.bot.store.get_match(self.match_id)
        settings = await self.bot.store.get_settings(interaction.guild.id)
        log_channel = interaction.guild.get_channel(settings.mm_log_channel)
        try:
            log_message = await log_channel.fetch_message(match.log_message)
            embed = log_message.embeds[0]
            embed.description = f"Match terminated by {interaction.user.mention}"
            await log_message.edit(embed=embed)
        except Exception:
            pass
        await interaction.followup.send("Match terminated", ephemeral=True)
        log.info(f"{interaction.user.display_name} terminated match {self.match_id}")
        self.done_event.set()