import enum
import datetime
from functools import wraps
from typing import TYPE_CHECKING, Union, List, Callable, Any, TypeVar

import nextcord

if TYPE_CHECKING:
    from main import Bot

from utils.logger import Logger as log

T = TypeVar('T')

class EventType(enum.Enum):
    CREATE = 0x2ecc71  # Green
    DELETE = 0xe74c3c  # Red
    UPDATE = 0x3498db  # Blue
    MEMBER = 0x9b59b6  # Purple
    VOICE = 0xf1c40f   # Yellow
    MOD = 0xe67e22     # Orange
    OTHER = 0x95a5a6   # Gray


class LogHelper:
    def __init__(self, bot: 'Bot'):
        self.bot = bot
    
    async def get_log_channel(self, guild: nextcord.Guild) -> nextcord.TextChannel | None:
        settings = await self.bot.store.get_settings(guild.id)
        if not settings or not settings.log_channel:
            return None
        return guild.get_channel(int(settings.log_channel))
    
    async def get_staff_role(self, guild: nextcord.Guild) -> nextcord.Role | None:
        settings = await self.bot.store.get_settings(guild.id)
        if not settings or not settings.mm_staff_role:
            return None
        return guild.get_role(int(settings.mm_staff_role))
    
    async def get_match_category(self, guild: nextcord.Guild) -> nextcord.CategoryChannel | None:
        settings = await self.bot.store.get_settings(guild.id)
        if not settings or not settings.mm_match_category:
            return None
        return guild.get_channel(int(settings.mm_match_category))
    
    async def log_event(self, 
        guild: nextcord.Guild,
        event_type: EventType, 
        title: str, 
        description: str | None = None,
        fields: List[tuple[str, str, bool]] | None = None,
        author: Union[nextcord.Member, nextcord.User] | None = None,
        thumbnail: str | None = None
    ) -> nextcord.Message | None:
        channel = await self.get_log_channel(guild)
        if not channel:
            return None
        
        embed = nextcord.Embed(
            title=title,
            description=description,
            color=event_type.value,
            timestamp=datetime.datetime.now())
        
        if author:
            embed.set_author(
                name=f"{author.name}#{author.discriminator}" if hasattr(author, "discriminator") else author.name,
                icon_url=author.display_avatar.url if hasattr(author, "display_avatar") else None)
        
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        
        if fields:
            for name, value, inline in fields:
                embed.add_field(name=name, value=value, inline=inline)
        
        embed.set_footer(text=f"Event ID: {int(datetime.datetime.now().timestamp())}")
        
        try:
            return await channel.send(embed=embed)
        except nextcord.HTTPException:
            log.error(f"Failed to send log message to channel {channel.id}")
            return None
    
    @staticmethod
    def ignore_bot_actions(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            for arg in args:
                if isinstance(arg, (nextcord.Member, nextcord.User)) and arg.id == self.bot.user.id:
                    return
                if (author := getattr(arg, 'author', getattr(arg, 'owner', getattr(arg, 'user', False)))
                ) and author.id == self.bot.user.id:
                    return
            await func(self, *args, **kwargs)
        return wrapper
    
    @staticmethod
    def staff_visible_only(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            guild = None
            for arg in args:
                if isinstance(arg, nextcord.Guild):
                    guild = arg
                    break
                elif hasattr(arg, 'guild'):
                    guild = arg.guild
                    break
            
            if not guild:
                await func(self, *args, **kwargs)
                return
                
            staff_role = await self.helper.get_staff_role(guild)
            if not staff_role:
                await func(self, *args, **kwargs)
                return
                
            channel_arg = None
            for arg in args:
                if isinstance(arg, nextcord.abc.GuildChannel):
                    channel_arg = arg
                    break
                
            if not channel_arg:
                await func(self, *args, **kwargs)
                return
                
            perms = channel_arg.permissions_for(staff_role)
            if perms.view_channel:
                await func(self, *args, **kwargs)
        return wrapper
    
    @staticmethod
    def ignore_in_matches(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            guild = None
            for arg in args:
                if isinstance(arg, nextcord.Guild):
                    guild = arg
                    break
                elif hasattr(arg, 'guild'):
                    guild = arg.guild
                    break
            
            if not guild:
                await func(self, *args, **kwargs)
                return
                
            match_category = await self.helper.get_match_category(guild)
            if not match_category:
                await func(self, *args, **kwargs)
                return
                
            for arg in args:
                if isinstance(arg, (nextcord.abc.GuildChannel, nextcord.Thread)):
                    if (hasattr(arg, 'category_id') and arg.category_id == match_category.id) or \
                       (isinstance(arg, nextcord.Thread) and arg.parent.category_id == match_category.id):
                        return
                elif isinstance(arg, nextcord.StageInstance):
                    channel = guild.get_channel(arg.channel_id)
                    if channel and hasattr(channel, 'category_id') and channel.category_id == match_category.id:
                        return
                elif isinstance(arg, nextcord.VoiceState):
                    if arg.channel and hasattr(arg.channel, 'category_id') and arg.channel.category_id == match_category.id:
                        return
            
            await func(self, *args, **kwargs)
        return wrapper