import asyncio
from datetime import datetime, timedelta, timezone

import nextcord

from config import GUILD_ID
from utils.logger import Logger as log

class MuteManager:
    def __init__(self, bot):
        self.bot = bot
        self.active_mutes = {}
        self.tasks = {}

    async def load_active_mutes(self):
        mutes = await self.bot.store.get_mutes(GUILD_ID)
        for user_id, mute in mutes.items():
            if mute['duration']:
                expiry = mute['timestamp'] + timedelta(seconds=mute['duration'])
                if expiry > datetime.now(timezone.utc):
                    self.schedule_unmute(user_id, expiry)

    def schedule_unmute(self, user_id: int, expiry: datetime):
        if user_id in self.tasks:
            self.tasks[user_id].cancel()
        self.active_mutes[user_id] = expiry
        task = asyncio.create_task(self.auto_unmute(user_id, expiry))
        self.tasks[user_id] = task

    async def auto_unmute(self, user_id: int, expiry: datetime):
        try:
            await asyncio.sleep((expiry - datetime.now(timezone.utc)).total_seconds())
            await self.unmute_user(user_id)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"Error in auto_unmute for user {user_id}: {repr(e)}")

    async def unmute_user(self, user_id: int):
        guild = self.bot.get_guild(GUILD_ID)
        settings = await self.bot.store.get_settings(GUILD_ID)
        member = guild.get_member(user_id)
        if member:
            if settings.mm_mute_role in (r.id for r in member.roles):
                mute_role = guild.get_role(settings.mm_mute_role)
                asyncio.create_task(member.remove_roles(mute_role))
            
            embed = nextcord.Embed(
                title="Mute Expired",
                description="You can now message in the server again.",
                color=0x0055ff)
            try:
                await member.send(embed=embed)
            except (nextcord.Forbidden, nextcord.HTTPException):
                pass

        self.active_mutes.pop(user_id, None)
        self.tasks.pop(user_id, None)
        await self.bot.store.update_mute(guild_id=GUILD_ID, user_id=user_id, active=False)

        embed = nextcord.Embed(
            title="Unmuted Automatically", 
            description=f"<@{user_id}>",
            color=0x0055ff, 
            timestamp=datetime.now(timezone.utc))
        await guild.get_channel(settings.log_channel).send(embed=embed)