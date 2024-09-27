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

from matches.functions import calculate_mmr_change
from config import PLACEMENT_MATCHES
from utils.utils import abandon_cooldown, format_duration
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
                    from matches import cleanup_match
                    if not await cleanup_match(asyncio.get_event_loop(), self.match.id):
                        log.error(f"{interaction.user.display_name} had an issue force abandoning match {self.match.id}")
                        return await interaction.followup.send("Something went wrong. Try again...", ephemeral=True)
                    
                    mmr_losses = []
                    for player in self.missing_players:
                        played_games = await self.bot.store.get_user_played_games(interaction.user.id, player.user_id)
                        previous_abandons, _ = await self.bot.store.get_abandon_count_last_period(interaction.guild.id, player.user_id)     
                        cooldown = abandon_cooldown(previous_abandons + 1)

                        ally_mmr = self.match.a_mmr if player.team == Team.A else self.match.b_mmr
                        enemy_mmr = self.match.b_mmr if player.team == Team.A else self.match.a_mmr
                        
                        mmr_change = calculate_mmr_change(
                            {}, 
                            abandoned_count=previous_abandons + 1, 
                            ally_team_avg_mmr=ally_mmr, 
                            enemy_team_avg_mmr=enemy_mmr, 
                            placements=played_games[player.user_id] <= PLACEMENT_MATCHES)
                        mmr_losses.append(mmr_change)
                        abandons_str =  f"`{previous_abandons + 1}` abandon{'s' if previous_abandons != 0 else ''}"
                        embed = nextcord.Embed(
                            title=f"You were abandoned for being late to Match #{self.match.id}",
                            description=f"You lost `{mmr_change}` and gained a cooldown of `{format_duration(cooldown)}` due to {abandons_str} in the past 2 months.",
                            color=0xff0000)
                        asyncio.create_task(self.bot.get_user(player.user_id).send(embed=embed))

                    await interaction.response.defer(ephemeral=True)
                    
                    missing_mentions = ', '.join((f'<@{p.user_id}>' for p in self.missing_players))
                    log.info(f"{interaction.user.display_name} abandoned forcefully match {self.match.id} due to lates: {missing_mentions}")

                    await self.bot.store.add_match_abandons(interaction.guild.id, self.match.id, [p.user_id for p in self.missing_players], mmr_losses)
                    await interaction.guild.get_channel(self.match.match_thread).send(f"@here Match Abandoned by Staff")

                    log_channel = interaction.guild.get_channel(settings.mm_log_channel)
                    try:
                        log_message = await log_channel.fetch_message(self.match.log_message)
                        embed = log_message.embeds[0]
                        embed.description = f"Match abandoned due to {missing_mentions} being late"
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
        cancel_button.callback = cancel_callback
        view.add_item(cancel_button)

        cancel_button = nextcord.ui.Button(
            label="Confirm", emoji="✔️", style=nextcord.ButtonStyle.danger)
        cancel_button.callback = confirm_callback
        view.add_item(confirm_callback)

        embed = nextcord.Embed(
            title="Force Abandon the missing players?",
            description=f"{'\n'.join((f'<@{p.user_id}>' for p in self.missing_players))}",
            color=0xff0000)

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)