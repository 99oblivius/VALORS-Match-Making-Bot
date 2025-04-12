import enum
import datetime
from functools import wraps
from typing import TYPE_CHECKING, Union, List, Callable, Any, TypeVar, cast

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
    
    async def log_event(self, 
        guild: nextcord.Guild,
        event_type: EventType, 
        title: str, 
        description: str | None = None,
        fields: List[tuple[str, str, bool]] | None = None,
        author: Union[nextcord.Member, nextcord.User] | None = None,
        thumbnail: str | None = None
    ) -> nextcord.Message | None:
        
        settings = await self.bot.settings_cache(guild.id)
        if not settings or not cast(int, settings.server_log_channel):
            return None
        channel = guild.get_channel(int(cast(int, settings.server_log_channel)))
        
        if not channel:
            return None
        
        embed = nextcord.Embed(
            title=title,
            description=description,
            color=event_type.value,
            timestamp=datetime.datetime.now())
        
        if author:
            embed.set_author(
                name=f"{author.name}" if hasattr(author, "discriminator") else author.name,
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
                if isinstance(arg, (nextcord.Member, nextcord.User)) and arg.id  == self.bot.user.id:
                    return
                if hasattr(arg, 'author') and arg.author.id == self.bot.user.id:
                    return
                if hasattr(arg, 'user') and arg.user.id == self.bot.user.id:
                    return
                if hasattr(arg, 'owner_id') and arg.owner_id == self.bot.user.id:
                    return
                if hasattr(arg, 'owner') and arg.owner.id == self.bot.user.id:
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
                
            settings = await self.bot.settings_cache(guild.id)
            if not settings or not cast(int, settings.mm_staff_role):
                return None
            staff_role = guild.get_role(int(cast(int, settings.mm_staff_role)))
            if not staff_role:
                await func(self, *args, **kwargs)
                return
                
            channel_arg = None
            for arg in args:
                if isinstance(arg, nextcord.abc.GuildChannel):
                    channel_arg = arg
                    break
                elif hasattr(arg, 'channel'):
                    channel_arg = arg.channel
                    break
                
            if not channel_arg:
                await func(self, *args, **kwargs)
                return
                
            perms = channel_arg.permissions_for(staff_role)
            
            if perms.view_channel: await func(self, *args, **kwargs)
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
            
            match_category = None
            settings = await self.bot.settings_cache(guild.id)
            if settings and cast(int, settings.mm_match_category):
                match_category = guild.get_channel(int(cast(int, settings.mm_match_category)))
                
            if not match_category:
                await func(self, *args, **kwargs)
                return
                
            for arg in args:
                if hasattr(arg, 'category_id') and arg.category_id == match_category.id:
                    return
                elif hasattr(arg, 'channel'):
                    if hasattr(arg.channel, 'category') and arg.channel.category.id == match_category.id:
                        return
                    elif hasattr(arg.channel, 'category_id') and arg.channel.category_id == match_category.id:
                        return
                elif hasattr(arg, 'channel_id') and (channel := guild.get_channel(arg.channel_id)) and channel.category_id == match_category.id:
                    return
                elif hasattr(arg, 'parent') and arg.parent.category.category_id == match_category.id:
                    return
            
            await func(self, *args, **kwargs)
        return wrapper