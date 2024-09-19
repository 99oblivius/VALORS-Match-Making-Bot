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

import json
import re
from datetime import datetime, timedelta, timezone
from io import BytesIO
import asyncio

import nextcord
from nextcord.ext import commands

from config import *
from utils.logger import Logger as log
from utils.models import Warn
from utils.utils import format_duration, log_moderation


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_ready(self):
        log.info("Cog started")

    @nextcord.slash_command(description="Moderation commands", guild_ids=[GUILD_ID])
    async def moderation(self, interaction: nextcord.Interaction):
        pass

    @moderation.subcommand(name="warn", description="Warn a user")
    async def moderation_warn(self, interaction: nextcord.Interaction, 
        user: nextcord.User | nextcord.Member = nextcord.SlashOption(description="Which user to add a warning to"),
        message: str = nextcord.SlashOption(description="The warn message. The user will see this."),
        match_id: int = nextcord.SlashOption(description="Match number the warn is assigned to.", default=None, required=False)
):
        await self.bot.store.upsert_warning(
            guild_id=interaction.guild.id, 
            user_id=user.id, 
            message=message,
            match_id=match_id,
            moderator_id=interaction.user.id,
            type=Warn.WARNING)
        
        failed_to_send = False
        embed = nextcord.Embed(title="You have been warned", description=f"```\n{message}```", color=0xff6600)
        try:
            await user.send(embed=embed)
        except (nextcord.HTTPException, nextcord.Forbidden):
            failed_to_send = True

        await interaction.response.send_message(f"{user.mention} has been warned and was{' **NOT** ' if failed_to_send else ' '} notified.", ephemeral=True)
        settings = await self.bot.store.get_settings(interaction.guild.id)
        await log_moderation(interaction, settings.log_channel, f"{user.name} warned{f' Match # {match_id}' if match_id else ''}", f"```\n{message}```")


def setup(bot):
    bot.add_cog(Moderation(bot))
