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

class ForceAbandonView(nextcord.ui.View):
    def __init__(self, bot, match=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.match = match
        self.missing_players = []
        self.abandon_lock = asyncio.Lock()
        self.abandoned = False
        self.timeout = None
    
    async def wait_abandon(self):
        async with self.abandon_lock:
            await asyncio.sleep(0)

    @nextcord.ui.button(
        label="Staff Only",
        style=nextcord.ButtonStyle.danger,
        custom_id="mm_force_abandon_staff_only",
        disabled=True)
    async def force_abandon_staff_only(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        pass

    @nextcord.ui.button(
        label="Abandon",
        emoji="🏳️",
        style=nextcord.ButtonStyle.secondary,
        custom_id="mm_force_abandon")
    async def force_abandon(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        settings = await self.bot.store.get_settings(interaction.guild.id)

        if settings.mm_staff_role not in [r.id for r in interaction.user.roles]:
            return await interaction.response.send_message("This button is meant for Staff only", ephemeral=True)
        
        message = None
        async def confirm_callback(interaction: nextcord.Integration):
            async with self.abandon_lock:
                if not self.abandoned:
                    loop = asyncio.get_event_loop()
                    await interaction.response.defer(ephemeral=True)

                    from matches import cleanup_match
                    if not await cleanup_match(loop, self.match.id):
                        log.error(f"{interaction.user.display_name} had an issue force abandoning match {self.match.id}")
                        return await interaction.followup.send("Something went wrong. Try again...", ephemeral=True)
                    
                    missing_str = ', '.join((p.user_id for p in self.missing_players))
                    log.info(f"{interaction.user.display_name} abandoned forcefully match {self.match.id} due to lates: {missing_str}")

                    await self.bot.store.add_match_abandons(interaction.guild.id, self.match.id, [p.user_id for p in self.missing_players])
                    await interaction.guild.get_channel(self.match.match_thread).send(f"@here Match Abandoned by Staff")

                    log_channel = interaction.guild.get_channel(settings.mm_log_channel)
                    try:
                        log_message = await log_channel.fetch_message(self.match.log_message)
                        embed = log_message.embeds[0]
                        embed.description = f"Match abandoned by Staff ({interaction.user.mention})"
                        await log_message.edit(embed=embed)
                    except Exception: pass
                    await interaction.followup.send("You successfully force abandoned the match", ephemeral=True)
                    self.abandoned = True
        
        async def cancel_callback(interaction: nextcord.Integration):
            try:
                await message.delete()
            except Exception:
                pass
            
        view = nextcord.ui.View(timeout=None)

        cancel_button = nextcord.ui.Button(
            label="Cancel", emoji="❌", style=nextcord.ButtonStyle.secondary)
        cancel_button.callback = cancel_callback()
        view.add_item(cancel_button)

        cancel_button = nextcord.ui.Button(
            label="Confirm", emoji="✔️", style=nextcord.ButtonStyle.danger)
        cancel_button.callback = confirm_callback()
        view.add_item(confirm_callback)

        embed = nextcord.Embed(
            title="Force Abandon the missing players?",
            description=f"{'\n'.join((f'<@{p.user_id}>' for p in self.missing_players))}",
            color=0xff0000)

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)