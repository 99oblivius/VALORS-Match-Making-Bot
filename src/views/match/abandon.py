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

from datetime import datetime, timedelta, timezone
import nextcord

from matches import cleanup_match, get_match
from utils.logger import Logger as log
from utils.models import *


class AbandonView(nextcord.ui.View):
    def __init__(self, bot, match=None, mmr_loss=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.timeout = None
        self.match = match
        self.mmr_loss = mmr_loss
    
    @nextcord.ui.button(
        label="Yes", 
        emoji="✔️", 
        style=nextcord.ButtonStyle.red, 
        custom_id="mm_accept_abandon_button")
    async def abandon(self, button: nextcord.ui.Button, interaction: nextcord.Integration):
        loop = asyncio.get_event_loop()
        await interaction.response.defer(ephemeral=True)

        if not await cleanup_match(loop, self.match.id):
            log.error(f"{interaction.user.display_name} had an issue abandoning match {self.match.id}")
            return await interaction.followup.send("Something went wrong. Try again...", ephemeral=True)
        
        instance = get_match(self.match.id)
        requeued_msg = ""
        if instance.match.start_timestamp + timedelta(minutes=15) > datetime.now(timezone.utc):
            requeued_msg = "\nRemaining players will be re-queued automatically."
            instance.requeue_players = [p.user_id for p in instance.players if p.user_id != interaction.user.id]
        
        log.info(f"{interaction.user.display_name} abandoned match {self.match.id}")
        await self.bot.store.add_match_abandons(interaction.guild.id, self.match.id, [interaction.user.id], [self.mmr_loss])
        await interaction.guild.get_channel(self.match.match_thread).send(f"@here Match Abandoned by {interaction.user.mention}{requeued_msg}")
        
        settings = await self.bot.store.get_settings(interaction.guild.id)
        log_channel = interaction.guild.get_channel(settings.mm_log_channel)
        try:
            log_message = await log_channel.fetch_message(self.match.log_message)
            embed = log_message.embeds[0]
            embed.description = f"Match abandoned by {interaction.user.mention}"
            await log_message.edit(embed=embed)
        except Exception: pass
        await interaction.followup.send("You abandoned the match", ephemeral=True)
    
    @nextcord.ui.button(
        label="No", 
        emoji="❌", 
        style=nextcord.ButtonStyle.grey,
        custom_id="mm_cancel_abandon_button")
    async def cancel_abandon(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        try: await self.hide_msg.delete()
        except: pass
        await interaction.response.pong()
