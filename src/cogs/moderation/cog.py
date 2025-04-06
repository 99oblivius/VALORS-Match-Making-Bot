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

from datetime import datetime, timezone, timedelta
from collections import defaultdict
import math
import re

from fuzzywuzzy import process
import nextcord
from nextcord.ext import commands

from config import *
from views.moderation.pagination import PaginationView
from utils.statistics import (
    create_late_rankings_embed, 
    create_rankings_embed, 
    create_user_infraction_embed, 
    create_mute_history_embed
)
from utils.logger import Logger as log
from utils.models import Warn, MMBotWarnedUsers
from utils.mutemanager import MuteManager
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
        self.mute_manager = MuteManager(bot)
    
    @commands.Cog.listener()
    async def on_ready(self):
        await self.mute_manager.load_active_mutes()
        log.info("Cog started")

    @nextcord.slash_command(description="Moderation commands", guild_ids=[*GUILD_IDS])
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

    @moderation.subcommand(name="mute", description="Mute a user")
    async def mute(self, interaction: nextcord.Interaction, 
        user: nextcord.Member = nextcord.SlashOption(description="User to mute"),
        reason: str = nextcord.SlashOption(description="Reason for mute", autocomplete=True, required=True),
        duration: str = nextcord.SlashOption(description="Mute duration (e.g., 1d12h30m or 'indefinite')", required=False),
        silent: bool = nextcord.SlashOption(description="Mute silently", required=False, default=False)
    ):
        settings = await self.bot.store.get_settings(interaction.guild_id)
        mute_role = interaction.guild.get_role(settings.mm_mute_role)

        mute_duration = None
        if duration and duration.lower() != 'indefinite':
            mute_durations = re.match(r"(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?", duration)
            if not mute_durations:
                return await interaction.response.send_message("Invalid duration format. Use '1d12h30m' or 'indefinite'.", ephemeral=True)

            days, hours, minutes = map(lambda x: int(x) if x else 0, mute_durations.groups())
            mute_duration = timedelta(days=days, hours=hours, minutes=minutes)

        await user.add_roles(mute_role)
        mute_id = await self.bot.store.add_mute(
            guild_id=interaction.guild_id, 
            user_id=user.id, 
            moderator_id=interaction.user.id, 
            duration=mute_duration.total_seconds() if mute_duration else None, 
            reason=reason)

        if mute_duration:
            expiry = datetime.now(timezone.utc) + mute_duration
            self.mute_manager.schedule_unmute(user.id, expiry)

        failed_send = False
        if not silent:
            staff_channel = interaction.guild.get_channel(settings.staff_channel)
            if staff_channel:
                embed = nextcord.Embed(
                    title="Muted", 
                    description=f"{user.mention} was muted for ```{reason}```", 
                    color=0xff0055)
                await staff_channel.send(embed=embed)

            embed = nextcord.Embed(title="You have been muted", color=0xff0055)
            embed.add_field(name="Duration", value=format_duration(mute_duration.total_seconds()) if mute_duration else "Indefinite")
            embed.add_field(name="Reason", value=reason)
            try:
                await user.send(embed=embed)
            except (nextcord.Forbidden, nextcord.HTTPException):
                failed_send = True
        
        failed_message = '\nThey were not notified due to privacy settings.'
        await interaction.response.send_message(f"id: `{mute_id}` {user.mention} has been muted. {failed_message if failed_send else ''}", ephemeral=True)
        duration_str = f'<t:{int((datetime.now(timezone.utc) + mute_duration).timestamp())}:R>' if mute_duration else 'The End of Time'
        await log_moderation(interaction, settings.log_channel, f"Muted", f"{user.mention} will be unmuted {duration_str}\nReason:\n```\n{reason}```")

    @mute.on_autocomplete("reason")
    async def mute_reason_autocomplete(self, interaction: nextcord.Interaction, reason: str):
        reasons = [
            "Obscene language",
            "Instigating arguments",
            "Spamming",
            "Inappropriate content",
            "Harassment",
            "Hate speech",
            "Sharing personal information",
            "Impersonation",
            "Excessive caps"
        ]

        if not reason:
            return reasons
        return [reason, *(r[0] for r in process.extract(reason, reasons, limit=25))]

    @moderation.subcommand(name="unmute", description="Unmute a user")
    async def unmute(self, interaction: nextcord.Interaction, 
        user: nextcord.Member = nextcord.SlashOption(description="User to unmute"),
        silent: bool = nextcord.SlashOption(description="Unmute silently", required=False, default=False)
    ):
        settings = await self.bot.store.get_settings(interaction.guild_id)
        mute_role = interaction.guild.get_role(settings.mm_mute_role)
        
        if mute_role not in user.roles:
            return await interaction.response.send_message("This user is not muted.", ephemeral=True)

        await user.remove_roles(mute_role)
        await self.bot.store.update_mute(guild_id=interaction.guild_id, user_id=user.id, active=False)
        self.mute_manager.active_mutes.pop(user.id, None)
        if user.id in self.mute_manager.tasks:
            self.mute_manager.tasks[user.id].cancel()
            self.mute_manager.tasks.pop(user.id, None)

        if not silent:
            embed = nextcord.Embed(title="You have been unmuted", color=0xff5500)
            try:
                await user.send(embed=embed)
            except (nextcord.Forbidden, nextcord.HTTPException):
                pass

        await interaction.response.send_message(f"{user.mention} has been unmuted.", ephemeral=True)
        await log_moderation(interaction, settings.log_channel, f"Unmuted", f"{user.name}")

    @moderation.subcommand(name="mute_list", description="List currently muted users")
    async def mute_list(self, interaction: nextcord.Interaction):
        mutes = await self.bot.store.get_mutes(interaction.guild_id)
        
        if not mutes:
            return await interaction.response.send_message("There are no currently muted users.", ephemeral=True)

        embed = nextcord.Embed(title="Currently Muted Users", color=0xff0055)
        for user_id, mute in mutes.items():
            user = interaction.guild.get_member(user_id)
            moderator = interaction.guild.get_member(mute['moderator_id'])
            duration = f"<t:{int(mute['timestamp'].timestamp()) + mute['duration']}:R>" if mute['duration'] else "`Never`"
            value = f"Muted by: {moderator.mention if moderator else mute['moderator_id']} <t:{int(mute['timestamp'].timestamp())}:f> expires {duration}\n"
            value += f"Reason: {mute['reason'] or 'No reason provided'}"
            embed.add_field(name=f"id:{mute['id']} - {user.name if user else user_id}", value=value, inline=False)

        await interaction.response.send_message(embed=embed)

    @moderation.subcommand(name="mute_history", description="View a user's mute history")
    async def mute_history(self, interaction: nextcord.Interaction, 
        user: nextcord.Member = nextcord.SlashOption(description="User to check"),
        page: int = nextcord.SlashOption(description="Page number", min_value=1, default=1)
    ):
        PAGE_SIZE = 10
        offset = (page - 1) * PAGE_SIZE

        mute_history = await self.bot.store.get_user_mute_history(interaction.guild_id, user.id, limit=PAGE_SIZE, offset=offset)
        total_pages = math.ceil(len(mute_history) / PAGE_SIZE)
        
        if not mute_history:
            return await interaction.response.send_message(f"{user.name} has no mute history.", ephemeral=True)
        
        embed = await create_mute_history_embed(interaction.guild, user, mute_history, page, total_pages)

        view = PaginationView(self.moderation_late_rankings, page, total_pages)
        
        await interaction.response.send_message(embed=embed, view=view)


    @moderation.subcommand(name="edit_mute", description="Edit the duration of an active mute")
    async def edit_mute(self, interaction: nextcord.Interaction, 
        mute_id: int = nextcord.SlashOption(description="ID of the mute to edit"),
        new_duration: str = nextcord.SlashOption(description="New mute duration (e.g., 1d12h30m or 'indefinite')", required=False),
        reason: str = nextcord.SlashOption(description="Edit the reason", required=False),
        delete: bool = nextcord.SlashOption(description="Remove this mute", required=False)
    ):
        mute = await self.bot.store.get_muted(mute_id)
        
        if not mute or (not mute.active and not delete):
            return await interaction.response.send_message("Invalid mute ID or mute is not active.", ephemeral=True)

        if new_duration:
            if new_duration.lower() == 'indefinite':
                new_duration_seconds = None
            else:
                mute_durations = re.match(r"(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?", new_duration)
                if not mute_durations:
                    return await interaction.response.send_message("Invalid duration format. Use '1d12h30m' or 'indefinite'.", ephemeral=True)

                days, hours, minutes = map(lambda x: int(x) if x else 0, mute_durations.groups())
                new_duration_timedelta = timedelta(days=days, hours=hours, minutes=minutes)
                new_duration_seconds = new_duration_timedelta.total_seconds()

        values = {}
        if new_duration:
            values['duration'] = new_duration
        
        if reason:
            values['reason'] = reason
        
        if delete:
            values['ignored'] = delete
            settings = await self.bot.store.get_settings(interaction.guild_id)
            mute_role = interaction.guild.get_role(settings.mm_mute_role)
            user = interaction.guild.get_member(mute.user_id) or self.bot.get_user(mute.user_id)
            if user:
                if mute_role in user.roles:
                    await user.remove_roles(mute_role)
                await self.bot.store.update_mute(guild_id=interaction.guild_id, user_id=user.id, active=False)
            self.mute_manager.active_mutes.pop(user.id, None)
            if user.id in self.mute_manager.tasks:
                self.mute_manager.tasks[user.id].cancel()
                self.mute_manager.tasks.pop(user.id, None)
        
        await self.bot.store.update_mute(mute_id=mute_id, **values)
        
        if mute.user_id in self.mute_manager.tasks:
            self.mute_manager.tasks[mute['user_id']].cancel()
        
        if new_duration and new_duration_seconds and not delete:
            expiry = datetime.now(timezone.utc) + timedelta(seconds=new_duration_seconds)
            self.mute_manager.schedule_unmute(mute.user_id, expiry)
        else:
            self.mute_manager.active_mutes.pop(mute.user_id, None)
            self.mute_manager.tasks.pop(mute.user_id, None)

        await interaction.response.send_message(f"Mute updated.\n{'\n'.join(f'{k.capitalize()}: {str(v)}' for k, v in values.items())}", ephemeral=True)
        settings = await self.bot.store.get_settings(interaction.guild_id)
        await log_moderation(interaction, settings.log_channel, f"Mute Edited #{mute.id}", f"<@{mute.user_id}>\n{'\n'.join(f'{k.capitalize()}: {str(v)}' for k, v in values.items())}")

def setup(bot):
    bot.add_cog(Moderation(bot))
