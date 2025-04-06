import datetime
from typing import TYPE_CHECKING, Union, List

from config import GUILD_IDS
import nextcord
from nextcord.ext import commands

if TYPE_CHECKING:
    from main import Bot

from utils.utils import log_moderation
from utils.logger import Logger as log
from .helper import EventType, LogHelper


class Logging(commands.Cog):
    def __init__(self, bot: 'Bot'):
        self.bot = bot
        self.helper = LogHelper(bot)
    
    @commands.Cog.listener()
    async def on_ready(self) -> None:
        log.info("Cog started")
    
    @nextcord.slash_command(name="logging", description="Server logs", guild_ids=[*GUILD_IDS])
    async def logging(self, interaction: nextcord.Interaction):
        pass
    
    @logging.subcommand(name="set_logs", description="Set which channel receives server logs")
    async def server_set_logs(self, interaction: nextcord.Interaction):
        await self.bot.settings_cache(guild_id=interaction.guild.id, server_log_channel=interaction.channel.id)
        await interaction.response.send_message("Server Log channel set", ephemeral=True)
        await log_moderation(interaction, interaction.channel.id, "Server logs set here")
    
    @commands.Cog.listener()
    async def on_auto_moderation_action_execution(self, execution: nextcord.AutoModerationAction) -> None:
        guild = self.bot.get_guild(execution.guild_id)
        if not guild:
            return
            
        await self.helper.log_event(
            guild,
            EventType.MOD,
            "Auto-Moderation Action",
            f"Rule: {execution.rule_id}",
            fields=[
                ("Action", str(execution.action.type), True),
                ("Channel", f"<#{execution.channel_id}>", True),
                ("Message ID", str(execution.message_id), True)
            ])
    
    @commands.Cog.listener()
    async def on_guild_scheduled_event_create(self, event: nextcord.ScheduledEvent) -> None:
        await self.helper.log_event(
            event.guild,
            EventType.CREATE,
            "Scheduled Event Created",
            f"{event.name}",
            fields=[
                ("Description", event.description[:1024] if event.description else "No description", False),
                ("Start Time", event.start_time.strftime("%Y-%m-%d %H:%M:%S"), True),
                ("End Time", event.end_time.strftime("%Y-%m-%d %H:%M:%S") if event.end_time else "No end time", True),
                ("Location", str(event.location) if event.location else "No location", True)
            ],
            thumbnail=event.image.url if event.image else None)
    
    @commands.Cog.listener()
    async def on_guild_scheduled_event_delete(self, event: nextcord.ScheduledEvent) -> None:
        await self.helper.log_event(
            event.guild,
            EventType.DELETE,
            "Scheduled Event Deleted",
            f"{event.name}",
            fields=[
                ("Description", event.description[:1024] if event.description else "No description", False),
                ("Start Time", event.start_time.strftime("%Y-%m-%d %H:%M:%S"), True),
                ("End Time", event.end_time.strftime("%Y-%m-%d %H:%M:%S") if event.end_time else "No end time", True),
                ("Location", str(event.location) if event.location else "No location", True)
            ],
            thumbnail=event.image.url if event.image else None)
    
    @commands.Cog.listener()
    async def on_invite_create(self, invite: nextcord.Invite) -> None:
        if not invite.guild:
            return
            
        inviter = invite.inviter
        await self.helper.log_event(
            invite.guild,
            EventType.CREATE,
            "Invite Created",
            f"Invite code: {invite.code}",
            fields=[
                ("Channel", f"<#{invite.channel.id}>", True),
                ("Max Uses", str(invite.max_uses) if invite.max_uses else "Unlimited", True),
                ("Temporary", "Yes" if invite.temporary else "No", True),
                ("Expires", invite.expires_at.strftime("%Y-%m-%d %H:%M:%S") if invite.expires_at else "Never", True)
            ],
            author=inviter)
    
    @commands.Cog.listener()
    async def on_member_ban(self, guild: nextcord.Guild, user: Union[nextcord.Member, nextcord.User]) -> None:
        await self.helper.log_event(
            guild,
            EventType.MOD,
            "Member Banned",
            f"{user.name}#{user.discriminator} ({user.id})" if hasattr(user, "discriminator") else f"{user.name} ({user.id})",
            author=user,
            thumbnail=user.display_avatar.url if hasattr(user, "display_avatar") else None)
    
    @commands.Cog.listener()
    async def on_member_unban(self, guild: nextcord.Guild, user: nextcord.User) -> None:
        await self.helper.log_event(
            guild,
            EventType.MOD,
            "Member Unbanned",
            f"{user.name}#{user.discriminator} ({user.id})" if hasattr(user, "discriminator") else f"{user.name} ({user.id})",
            author=user,
            thumbnail=user.display_avatar.url if hasattr(user, "display_avatar") else None)
    
    @commands.Cog.listener()
    @LogHelper.ignore_in_matches
    async def on_stage_instance_create(self, stage_instance: nextcord.StageInstance) -> None:
        guild = self.bot.get_guild(stage_instance.guild_id)
        if not guild:
            return
            
        await self.helper.log_event(
            guild,
            EventType.CREATE,
            "Stage Instance Created",
            f"{stage_instance.topic}",
            fields=[
                ("Channel", f"<#{stage_instance.channel_id}>", True),
                ("Privacy Level", str(stage_instance.privacy_level), True)
            ])
    
    @commands.Cog.listener()
    @LogHelper.ignore_in_matches
    async def on_stage_instance_delete(self, stage_instance: nextcord.StageInstance) -> None:
        guild = self.bot.get_guild(stage_instance.guild_id)
        if not guild:
            return
            
        await self.helper.log_event(
            guild,
            EventType.DELETE,
            "Stage Instance Deleted",
            f"{stage_instance.topic}",
            fields=[
                ("Channel", f"<#{stage_instance.channel_id}>", True),
                ("Privacy Level", str(stage_instance.privacy_level), True)
            ])
    
    @commands.Cog.listener()
    @LogHelper.staff_visible_only
    @LogHelper.ignore_bot_actions
    async def on_voice_state_update(self, member: nextcord.Member, before: nextcord.VoiceState, after: nextcord.VoiceState) -> None:
        if before.channel == after.channel:
            return
        
        if before.channel and not after.channel:
            action = f"Left voice channel {before.channel.name}"
        elif not before.channel and after.channel:
            action = f"Joined voice channel {after.channel.name}"
        else:
            action = f"Moved from {before.channel.name} to {after.channel.name}"
        
        await self.helper.log_event(
            member.guild,
            EventType.VOICE,
            "Voice State Updated",
            action,
            author=member)
    
    @commands.Cog.listener()
    async def on_guild_stickers_update(self, guild: nextcord.Guild, before: List[nextcord.GuildSticker], after: List[nextcord.GuildSticker]) -> None:
        before_stickers = {s.id: s for s in before}
        after_stickers = {s.id: s for s in after}
        
        new_stickers = [s for s_id, s in after_stickers.items() if s_id not in before_stickers]
        removed_stickers = [s for s_id, s in before_stickers.items() if s_id not in after_stickers]
        
        if new_stickers:
            stickers_text = "\n".join([f"- {s.name} (`{s.id}`)" for s in new_stickers])
            await self.helper.log_event(
                guild,
                EventType.CREATE,
                "Stickers Added",
                stickers_text)
        
        if removed_stickers:
            stickers_text = "\n".join([f"- {s.name} (`{s.id}`)" for s in removed_stickers])
            await self.helper.log_event(
                guild,
                EventType.DELETE,
                "Stickers Removed",
                stickers_text)
    
    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild: nextcord.Guild, before: List[nextcord.Emoji], after: List[nextcord.Emoji]) -> None:
        before_emojis = {e.id: e for e in before}
        after_emojis = {e.id: e for e in after}
        
        new_emojis = [e for e_id, e in after_emojis.items() if e_id not in before_emojis]
        removed_emojis = [e for e_id, e in before_emojis.items() if e_id not in after_emojis]
        
        if new_emojis:
            emojis_text = "\n".join([f"- {e.name} ({e})" for e in new_emojis])
            await self.helper.log_event(
                guild,
                EventType.CREATE,
                "Emojis Added",
                emojis_text)
        
        if removed_emojis:
            emojis_text = "\n".join([f"- {e.name}" for e in removed_emojis])
            await self.helper.log_event(
                guild,
                EventType.DELETE,
                "Emojis Removed",
                emojis_text)
    
    @commands.Cog.listener()
    async def on_guild_role_update(self, before: nextcord.Role, after: nextcord.Role) -> None:
        changes = []
        
        if before.name != after.name:
            changes.append(f"Name: `{before.name}` → `{after.name}`")
        if before.color != after.color:
            changes.append(f"Color: `{before.color}` → `{after.color}`")
        if before.hoist != after.hoist:
            changes.append(f"Hoisted: `{before.hoist}` → `{after.hoist}`")
        if before.mentionable != after.mentionable:
            changes.append(f"Mentionable: `{before.mentionable}` → `{after.mentionable}`")
        if before.permissions != after.permissions:
            changes.append("Permissions were updated")
        
        if changes:
            await self.helper.log_event(
                after.guild,
                EventType.UPDATE,
                "Role Updated",
                f"Role: {after.name} (`{after.id}`)",
                fields=[("Changes", "\n".join(changes), False)])
    
    @commands.Cog.listener()
    async def on_guild_role_create(self, role: nextcord.Role) -> None:
        await self.helper.log_event(
            role.guild,
            EventType.CREATE,
            "Role Created",
            f"Role: {role.name} (`{role.id}`)",
            fields=[
                ("Color", str(role.color), True),
                ("Hoisted", str(role.hoist), True),
                ("Mentionable", str(role.mentionable), True),
                ("Position", str(role.position), True)
            ])
    
    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: nextcord.Role) -> None:
        await self.helper.log_event(
            role.guild,
            EventType.DELETE,
            "Role Deleted",
            f"Role: {role.name} (`{role.id}`)",
            fields=[
                ("Color", str(role.color), True),
                ("Hoisted", str(role.hoist), True),
                ("Mentionable", str(role.mentionable), True),
                ("Position", str(role.position), True)
            ])
    
    @commands.Cog.listener()
    @LogHelper.ignore_bot_actions
    async def on_user_update(self, before: nextcord.User, after: nextcord.User) -> None:
        # User updates don't have guild context, so we skip them
        pass
    
    @commands.Cog.listener()
    @LogHelper.ignore_bot_actions
    async def on_member_update(self, before: nextcord.Member, after: nextcord.Member) -> None:
        changes = []
        
        if before.nick != after.nick:
            changes.append(f"Nickname: `{before.nick or 'None'}` → `{after.nick or 'None'}`")
        
        before_roles = set(before.roles)
        after_roles = set(after.roles)
        
        added_roles = after_roles - before_roles
        removed_roles = before_roles - after_roles
        
        if added_roles:
            roles_text = ", ".join([r.name for r in added_roles])
            changes.append(f"Added roles: {roles_text}")
        
        if removed_roles:
            roles_text = ", ".join([r.name for r in removed_roles])
            changes.append(f"Removed roles: {roles_text}")
        
        if changes:
            await self.helper.log_event(
                after.guild,
                EventType.UPDATE,
                "Member Updated",
                f"Member: {after.name} (`{after.id}`)",
                fields=[("Changes", "\n".join(changes), False)],
                author=after,
                thumbnail=after.display_avatar.url)
    
    @commands.Cog.listener()
    async def on_member_join(self, member: nextcord.Member) -> None:
        created_at = int(member.created_at.timestamp())
        joined_at = int(member.joined_at.timestamp()) if member.joined_at else None
        
        await self.helper.log_event(
            member.guild,
            EventType.MEMBER,
            "Member Joined",
            f"{member.name} (`{member.id}`)",
            fields=[
                ("Account Created", f"<t:{created_at}:R>", True),
                ("Joined Server", f"<t:{joined_at}:R>" if joined_at else "Unknown", True)
            ],
            author=member,
            thumbnail=member.display_avatar.url)
    
    @commands.Cog.listener()
    async def on_member_remove(self, member: nextcord.Member) -> None:
        joined_at = int(member.joined_at.timestamp()) if member.joined_at else None
        
        await self.helper.log_event(
            member.guild,
            EventType.MEMBER,
            "Member Left",
            f"{member.name} (`{member.id}`)",
            fields=[
                ("Joined Server", f"<t:{joined_at}:R>" if joined_at else "Unknown", True),
                ("Roles", ", ".join([r.name for r in member.roles[1:]]) or "None", False)
            ],
            author=member,
            thumbnail=member.display_avatar.url)
    
    @commands.Cog.listener()
    @LogHelper.staff_visible_only
    @LogHelper.ignore_bot_actions
    async def on_thread_create(self, thread: nextcord.Thread) -> None:
        await self.helper.log_event(
            thread.guild,
            EventType.CREATE,
            "Thread Created",
            f"{thread.name} (`{thread.id}`)",
            fields=[
                ("Parent Channel", f"<#{thread.parent_id}>", True),
                ("Archived", str(thread.archived), True),
                ("Auto Archive Duration", f"{thread.auto_archive_duration} minutes", True)
            ])
    
    @commands.Cog.listener()
    @LogHelper.staff_visible_only
    @LogHelper.ignore_bot_actions
    async def on_thread_remove(self, thread: nextcord.Thread) -> None:
        await self.helper.log_event(
            thread.guild,
            EventType.DELETE,
            "Thread Removed",
            f"{thread.name} (`{thread.id}`)",
            fields=[
                ("Parent Channel", f"<#{thread.parent_id}>", True),
                ("Archived", str(thread.archived), True),
                ("Auto Archive Duration", f"{thread.auto_archive_duration} minutes", True)
            ])
    
    @commands.Cog.listener()
    @LogHelper.staff_visible_only
    @LogHelper.ignore_bot_actions
    async def on_thread_delete(self, thread: nextcord.Thread) -> None:
        await self.helper.log_event(
            thread.guild,
            EventType.DELETE,
            "Thread Deleted",
            f"{thread.name} (`{thread.id}`)",
            fields=[
                ("Parent Channel", f"<#{thread.parent_id}>", True),
                ("Archived", str(thread.archived), True),
                ("Auto Archive Duration", f"{thread.auto_archive_duration} minutes", True)
            ])
    
    @commands.Cog.listener()
    @LogHelper.staff_visible_only
    @LogHelper.ignore_in_matches
    async def on_guild_channel_pins_update(self, channel: Union[nextcord.abc.GuildChannel, nextcord.Thread], last_pin: datetime.datetime | None) -> None:
        await self.helper.log_event(
            channel.guild,
            EventType.UPDATE,
            "Channel Pins Updated",
            f"<#{channel.id}>",
            fields=[
                ("Last Pin", last_pin.strftime("%Y-%m-%d %H:%M:%S") if last_pin else "Pin removed", True)
            ])
    
    @commands.Cog.listener()
    @LogHelper.staff_visible_only
    @LogHelper.ignore_in_matches
    async def on_guild_channel_update(self, before: nextcord.abc.GuildChannel, after: nextcord.abc.GuildChannel) -> None:
        changes = []
        
        if before.name != after.name:
            changes.append(f"Name: `{before.name}` → `{after.name}`")
        
        if isinstance(before, nextcord.TextChannel) and isinstance(after, nextcord.TextChannel):
            if before.topic != after.topic:
                changes.append(f"Topic: `{before.topic or 'None'}` → `{after.topic or 'None'}`")
            if before.slowmode_delay != after.slowmode_delay:
                changes.append(f"Slowmode: `{before.slowmode_delay}s` → `{after.slowmode_delay}s`")
        
        if isinstance(before, nextcord.VoiceChannel) and isinstance(after, nextcord.VoiceChannel):
            if before.bitrate != after.bitrate:
                changes.append(f"Bitrate: `{before.bitrate}` → `{after.bitrate}`")
            if before.user_limit != after.user_limit:
                changes.append(f"User Limit: `{before.user_limit or 'Unlimited'}` → `{after.user_limit or 'Unlimited'}`")
        
        if changes:
            await self.helper.log_event(
                after.guild,
                EventType.UPDATE,
                "Channel Updated",
                f"<#{after.id}>",
                fields=[("Changes", "\n".join(changes), False)])
    
    @commands.Cog.listener()
    @LogHelper.ignore_in_matches
    async def on_guild_channel_create(self, channel: nextcord.abc.GuildChannel) -> None:
        channel_type = "Text"
        if isinstance(channel, nextcord.VoiceChannel):
            channel_type = "Voice"
        elif isinstance(channel, nextcord.CategoryChannel):
            channel_type = "Category"
        elif isinstance(channel, nextcord.StageChannel):
            channel_type = "Stage"
        
        await self.helper.log_event(
            channel.guild,
            EventType.CREATE,
            "Channel Created",
            f"<#{channel.id}>",
            fields=[
                ("Name", channel.name, True),
                ("Type", channel_type, True),
                ("Category", channel.category.name if channel.category else "None", True)
            ])
    
    @commands.Cog.listener()
    @LogHelper.ignore_in_matches
    async def on_guild_channel_delete(self, channel: nextcord.abc.GuildChannel) -> None:
        channel_type = "Text"
        if isinstance(channel, nextcord.VoiceChannel):
            channel_type = "Voice"
        elif isinstance(channel, nextcord.CategoryChannel):
            channel_type = "Category"
        elif isinstance(channel, nextcord.StageChannel):
            channel_type = "Stage"
        
        await self.helper.log_event(
            channel.guild,
            EventType.DELETE,
            "Channel Deleted",
            f"#{channel.name}",
            fields=[
                ("ID", str(channel.id), True),
                ("Type", channel_type, True),
                ("Category", channel.category.name if channel.category else "None", True)
            ])
    
    @commands.Cog.listener()
    @LogHelper.staff_visible_only
    @LogHelper.ignore_bot_actions
    async def on_message_edit(self, before: nextcord.Message, after: nextcord.Message) -> None:
        if not before.guild or not before.content or not after.content or before.content == after.content:
            return
        
        await self.helper.log_event(
            before.guild,
            EventType.UPDATE,
            "Message Edited",
            f"Channel: <#{before.channel.id}>",
            fields=[
                ("Before", before.content[:1024], False),
                ("After", after.content[:1024], False),
                ("Message Link", f"[Jump to Message](https://discord.com/channels/{before.guild.id}/{before.channel.id}/{before.id})", True)
            ],
            author=before.author)
    
    @commands.Cog.listener()
    @LogHelper.staff_visible_only
    async def on_bulk_message_delete(self, messages: List[nextcord.Message]) -> None:
        if not messages or not messages[0].guild:
            return
            
        messages = sorted(messages, key=lambda m: m.created_at)
        
        await self.helper.log_event(
            messages[0].guild,
            EventType.DELETE,
            "Bulk Messages Deleted",
            f"{len(messages)} messages deleted in <#{messages[0].channel.id}>",
            fields=[
                ("First Message", messages[0].content[:1024] if messages[0].content else "[No content]", False),
                ("Last Message", messages[-1].content[:1024] if messages[-1].content else "[No content]", False),
                ("Time Range", f"{messages[0].created_at.strftime('%Y-%m-%d %H:%M:%S')} - {messages[-1].created_at.strftime('%Y-%m-%d %H:%M:%S')}", True)
            ])
    
    @commands.Cog.listener()
    @LogHelper.staff_visible_only
    @LogHelper.ignore_bot_actions
    async def on_message_delete(self, message: nextcord.Message) -> None:
        if not message.guild or (not message.content and not message.attachments):
            return
        
        fields = []
        if message.content:
            fields.append(("Content", message.content[:1024], False))
        
        if message.attachments:
            attachment_info = "\n".join([f"[{a.filename}]({a.url})" for a in message.attachments])
            fields.append(("Attachments", attachment_info[:1024], False))
        
        await self.helper.log_event(
            message.guild,
            EventType.DELETE,
            "Message Deleted",
            f"Channel: <#{message.channel.id}>",
            fields=fields,
            author=message.author)
    
    @commands.Cog.listener()
    @LogHelper.staff_visible_only
    @LogHelper.ignore_bot_actions
    async def on_message(self, message: nextcord.Message) -> None:
        if not message.guild or message.author.bot or not message.content:
            return
        
        if any(keyword in message.content.lower() for keyword in ["discord.gg", "discord.com/invite"]):
            await self.helper.log_event(
                message.guild,
                EventType.OTHER,
                "Invite Link Posted",
                f"Channel: <#{message.channel.id}>",
                fields=[
                    ("Content", message.content[:1024], False),
                    ("Message Link", f"[Jump to Message](https://discord.com/channels/{message.guild.id}/{message.channel.id}/{message.id})", True)
                ],
                author=message.author)


def setup(bot: 'Bot') -> None:
    bot.add_cog(Logging(bot))
