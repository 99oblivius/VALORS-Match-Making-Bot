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

from datetime import datetime, timezone
from collections import defaultdict
from fuzzywuzzy import process

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
        match_id: int = nextcord.SlashOption(description="Match number the warn is assigned to.", default=None, required=False),
        silent: bool = nextcord.SlashOption(choices={"Yes": True, "No": False}, default=False, required=False, description="Should the user not be messaged?")
    ):
        await self.bot.store.upsert_warning(
            guild_id=interaction.guild.id, 
            user_id=user.id, 
            message=message,
            match_id=match_id,
            moderator_id=interaction.user.id,
            warn_type=Warn.WARNING)
        
        failed_to_send = False
        if not silent:
            embed = nextcord.Embed(title="You have been warned", description=f"```\n{message}```", color=0xff6600)
            try:
                await user.send(embed=embed)
            except (nextcord.HTTPException, nextcord.Forbidden):
                failed_to_send = True

        await interaction.response.send_message(f"{user.mention} has been warned and was{' **NOT** ' if failed_to_send else ' '} notified.", ephemeral=True)
        settings = await self.bot.store.get_settings(interaction.guild.id)
        await log_moderation(interaction, settings.log_channel, f"{user.name} warned{f' Match # {match_id}' if match_id else ''}", f"```\n{message}```")

    @moderation.subcommand(name="history", description="View a user's infractions")
    async def moderation_infractions(self, interaction: nextcord.Interaction, 
        user: nextcord.User | nextcord.Member = nextcord.SlashOption(description="Which user to add a warning to"),
        warn_filter: str = nextcord.SlashOption(name="filter", description="Filter by warn type", required=False),
    ):
        warn_filters = None
        if warn_filter:
            warn_filters = [next((w for w in Warn if w.value.lower() == warn_filter.lower()))]

        all_warnings = await self.bot.store.get_user_warnings(guild_id=interaction.guild.id, user_id=user.id, warn_filters=warn_filters)
        grouped_users = defaultdict(list)
        for warn in all_warnings:
            grouped_users[warn.type].append(warn)
        
        embed = nextcord.Embed(
            title=f"User Infractions Summary{f' by {','.join((w.value.capitalize() for w in warn_filters))}' if warn_filters else ''}",
            description=f"{user.mention}",
            color=0xff6600,
            timestamp=datetime.now(timezone.utc))

        for warn_type, warnings in grouped_users.items():
            user_list = []
            for warn in warnings:
                user_info = f"{f'Match #{warn.match_id}' if warn.match_id else ''}<t:{int(warn.timestamp.timestamp())}:f>"
                if warn.moderator_id:
                    user_info += f" - by <@{warn.moderator_id}>"
                user_info += f"\n```\n{warn.message}```"
                user_list.append(user_info)
            
            value = "\n".join(user_list)[:1024]
            
            embed.add_field(
                name=f"{warn_type.value.capitalize()} ({len(warnings)})",
                value=value,
                inline=False)
        
        embed.set_footer(text=f"Total Warnings: {len(all_warnings)}")
        settings = await self.bot.store.get_settings(interaction.guild.id)
        moderation_category = interaction.guild.get_channel(settings.staff_channel).category
        await interaction.response.send_message(embed=embed, ephemeral=interaction.channel.category.id != moderation_category.id)

    @moderation_infractions.on_autocomplete("warn_filter")
    async def autocomplete_infractions(self, interaction: nextcord.Interaction, warn_filter):
        await interaction.response.send_autocomplete(choices=[w.value.capitalize() for w in Warn])


def setup(bot):
    bot.add_cog(Moderation(bot))
