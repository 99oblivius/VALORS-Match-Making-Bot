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
import math

import nextcord
from nextcord.ext import commands

from config import *
from views.moderation.pagination import PaginationView
from utils.statistics import create_late_rankings_embed, create_rankings_embed, create_user_infraction_embed
from utils.logger import Logger as log
from utils.models import Warn, MMBotWarnedUsers
from utils.utils import (
    format_duration, 
    log_moderation, 
    add_stats_field, 
    get_ratio_color, 
    get_ratio_interpretation
)

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
        for warning in sorted(all_warnings, key=lambda x: x.timestamp, reverse=True):
            grouped_users[warning.type].append(warning)
        
        embed = nextcord.Embed(
            title=f"User Infractions Summary{f' by {','.join((w.value.capitalize() for w in warn_filters))}' if warn_filters else ''}",
            description=f"{user.mention}",
            color=0xff6600,
            timestamp=datetime.now(timezone.utc))

        for warn_type, warnings in grouped_users.items():
            user_list = []
            for warn in warnings:
                user_info = f"id: {warn.id} |{f' Match #{warn.match_id} |' if warn.match_id else ''} <t:{int(warn.timestamp.timestamp())}:f>"
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
    
    @moderation.subcommand(name="unwarn", description="Remove a warning")
    async def moderation_remove_warn(self, interaction: nextcord.Interaction, 
        warning_id: int = nextcord.SlashOption(min_value=0, description="Unique idendentifier for the warning to remove")
    ):
        warning = await self.bot.store.get_warning(warning_id)
        if not warning:
            return await interaction.response.send_message(f"Warning `{warning_id}` does not exist.", ephemeral=True)
        
        await self.bot.store.update(MMBotWarnedUsers, id=warning_id, ignored=True)
        settings = await self.bot.store.get_settings(interaction.guild.id)
        await interaction.response.send_message(f"Warning `{warning_id}` was removed successfully.", ephemeral=interaction.channel.id != settings.staff_channel)
        await log_moderation(interaction, settings.log_channel, f"Removed warning", f"id: {warning_id}\ntype: {warning.type.value.capitalize()}\nmatch: {warning.match_id}\n```\n{warning.message}```")
    
    @moderation.subcommand(name="late_ratio", description="View user's punctuality ratio")
    async def moderation_late_ratio(self, interaction: nextcord.Interaction, 
        user: nextcord.User | nextcord.Member = nextcord.SlashOption(description="Which user to check"),
    ):
        punctuality_ratio = await self.bot.store.get_punctuality_ratio(interaction.guild.id, user.id)
        
        embed = nextcord.Embed(
            title=f"Punctuality Ratio for {user.display_name}",
            color=get_ratio_color(punctuality_ratio),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_thumbnail(url=user.avatar.url if user.avatar else user.default_avatar.url)
        
        embed.add_field(name="Punctuality Ratio", value=f"{punctuality_ratio:.2%}", inline=False)
        embed.add_field(name="Interpretation", value=get_ratio_interpretation(punctuality_ratio), inline=False)
        await interaction.response.send_message(embed=embed)

    @moderation.subcommand(name="late_details", description="View detailed late statistics for a user")
    async def moderation_late_details(self, interaction: nextcord.Interaction, 
        user: nextcord.User | nextcord.Member = nextcord.SlashOption(description="Which user to check"),
    ):
        late_stats = await self.bot.store.get_late_stats(interaction.guild.id, user.id)
        
        embed = nextcord.Embed(
            title=f"Late Statistics for {user.display_name}",
            color=0xff6600,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_thumbnail(url=user.avatar.url if user.avatar else user.default_avatar.url)
        
        embed.add_field(name="Total Games", value=late_stats['total_games'], inline=True)
        embed.add_field(name="Total Lates", value=late_stats['total_lates'], inline=True)
        embed.add_field(name="Late Rate", value=f"{late_stats['rate']:.2%}", inline=True)
        embed.add_field(name="Total Late Time", value=format_duration(late_stats['total_late_time']), inline=False)
        
        add_stats_field(embed, "Games Between Lates", late_stats['games_between'])
        add_stats_field(embed, "Late Durations", late_stats['late_durations'], is_duration=True)
        await interaction.response.send_message(embed=embed)

    @moderation.subcommand(name="late_rankings", description="View rankings of late users")
    async def moderation_late_rankings(self, interaction: nextcord.Interaction,
        page: int = nextcord.SlashOption(description="Page number", min_value=1, default=1)
    ):
        PAGE_SIZE = 10
        offset = (page - 1) * PAGE_SIZE

        rankings, total_count = await self.bot.store.get_late_rankings(interaction.guild.id, limit=PAGE_SIZE, offset=offset)
        total_pages = math.ceil(total_count / PAGE_SIZE)

        if not rankings:
            return await interaction.response.send_message("No late rankings available.", ephemeral=True)

        embed = await create_late_rankings_embed(interaction.guild, rankings, page, total_pages)
        
        view = PaginationView(self.moderation_late_rankings, page, total_pages)
        
        await interaction.response.send_message(embed=embed, view=view)

    @moderation.subcommand(name="missed_accept_rankings", description="View rankings of users who missed accepts")
    async def moderation_missed_accept_rankings(self, interaction: nextcord.Interaction,
        page: int = nextcord.SlashOption(description="Page number", min_value=1, default=1)
    ):
        PAGE_SIZE = 10
        offset = (page - 1) * PAGE_SIZE

        rankings, total_count = await self.bot.store.get_missed_accept_rankings(interaction.guild.id, limit=PAGE_SIZE, offset=offset)
        total_pages = math.ceil(total_count / PAGE_SIZE)

        if not rankings:
            return await interaction.response.send_message("No missed accept rankings available.", ephemeral=True)

        embed = await create_rankings_embed(interaction.guild, "Missed Accept Rankings", rankings, page, total_pages)
        
        view = PaginationView(self.moderation_missed_accept_rankings, page, total_pages)
        
        await interaction.response.send_message(embed=embed, view=view)

    @moderation.subcommand(name="abandon_rankings", description="View rankings of users who abandoned matches")
    async def moderation_abandon_rankings(self, interaction: nextcord.Interaction,
        page: int = nextcord.SlashOption(description="Page number", min_value=1, default=1)
    ):
        PAGE_SIZE = 10
        offset = (page - 1) * PAGE_SIZE

        rankings, total_count = await self.bot.store.get_abandon_rankings(interaction.guild.id, limit=PAGE_SIZE, offset=offset)
        total_pages = math.ceil(total_count / PAGE_SIZE)

        if not rankings:
            return await interaction.response.send_message("No abandon rankings available.", ephemeral=True)

        embed = await create_rankings_embed(interaction.guild, "Abandon Rankings", rankings, page, total_pages)
        
        view = PaginationView(self.moderation_abandon_rankings, page, total_pages)
        
        await interaction.response.send_message(embed=embed, view=view)

    @moderation.subcommand(name="user_missed_accepts", description="View missed accepts for a specific user")
    async def moderation_user_missed_accepts(self, interaction: nextcord.Interaction,
        user: nextcord.User | nextcord.Member = nextcord.SlashOption(description="Which user to check")
    ):
        missed_accepts = await self.bot.store.get_user_missed_accepts(interaction.guild.id, user.id)
        
        if not missed_accepts:
            return await interaction.response.send_message(f"{user.display_name} has no missed accepts.", ephemeral=True)

        embed = await create_user_infraction_embed("Missed Accepts", user, missed_accepts)
        
        await interaction.response.send_message(embed=embed)

    @moderation.subcommand(name="user_abandons", description="View abandons for a specific user")
    async def moderation_user_abandons(self, interaction: nextcord.Interaction,
        user: nextcord.User | nextcord.Member = nextcord.SlashOption(description="Which user to check")
    ):
        abandons = await self.bot.store.get_user_abandons(interaction.guild.id, user.id)
        
        if not abandons:
            return await interaction.response.send_message(f"{user.display_name} has no abandons.", ephemeral=True)

        embed = await create_user_infraction_embed("Abandons", user, abandons)
        
        await interaction.response.send_message(embed=embed)

def setup(bot):
    bot.add_cog(Moderation(bot))
