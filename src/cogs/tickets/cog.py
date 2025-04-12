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
from nextcord.ext import commands
from typing import TYPE_CHECKING, cast
if TYPE_CHECKING:
    from main import Bot

from config import GUILD_IDS

from utils.logger import Logger as log
from utils.utils import log_moderation
from views.tickets.support import TicketsView
from views.tickets.tickets import TicketCreationView
from views.tickets.ticket_panel import TicketPanelView


class Tickets(commands.Cog):
    def __init__(self, bot: "Bot"):
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(TicketsView(self.bot))
        self.bot.add_view(TicketCreationView(self.bot))
        self.bot.add_view(TicketPanelView(self.bot))
        
        log.info("Cog started")
    
    @nextcord.slash_command(name="tickets", description="Ticket management commands", guild_ids=[*GUILD_IDS])
    async def ticket_settings(self, _: nextcord.Interaction):
        pass
    
    @ticket_settings.subcommand(name="setup", description="Setup for support buttons")
    async def setup(self, interaction: nextcord.Interaction):
        settings = await self.bot.settings_cache(guild_id=interaction.guild.id, tickets_channel=interaction.channel.id)
        
        embed = nextcord.Embed(
            description="# Support\nDo you have a specific inquiry or require staff attention regarding a matter?\n\nWe ask that if you have a suggestion regarding the MM that you visit <#1358309120733745244> where you are invited to create a post as well. \n\nCreating a ticket will get staff members in touch with you as soon as possible. \n### Please simply state your reason for reaching out when creating the ticket.\n-# asking to ask a question will have your ticket closed",
            color=14242732)
        if not isinstance(interaction.channel, nextcord.TextChannel): return
        await interaction.channel.send(embed=embed, view=TicketsView(self.bot))
        
        await interaction.response.send_message(f"Tickets setup!", ephemeral=True)
        await log_moderation(interaction, cast(int, settings.log_channel), "Ticket channel", f"Ticket channel setup in <#{interaction.channel.id}>")


def setup(bot):
    bot.add_cog(Tickets(bot))