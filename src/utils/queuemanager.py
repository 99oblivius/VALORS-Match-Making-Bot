import asyncio
from datetime import datetime, timezone
import logging as log

import nextcord

from config import GUILD_ID, VALORS_THEME2, VALORS_THEME1_1
from utils.utils import format_duration

class QueueManager:
    def __init__(self, bot):
        self.bot = bot
        self.active_users = {}
        self.tasks = {}

    async def reminder_and_kick(self, user_id: int, expiry: int):
        try:
            settings = await self.bot.store.get_settings(GUILD_ID)
            reminder_time = expiry - int(datetime.now(timezone.utc).timestamp()) - settings.mm_queue_reminder
            reminder_msg = None
            if reminder_time > 0:
                await asyncio.sleep(reminder_time)
                user = self.bot.get_user(user_id)
                if user:
                    embed = nextcord.Embed(
                        title="Queue", 
                        description=f"`{format_duration(settings.mm_queue_reminder)}` left in \n<#{settings.mm_queue_channel}>!", 
                        color=VALORS_THEME2)
                    reminder_msg = await user.send(embed=embed)
            
            await asyncio.sleep(max(0, expiry - int(datetime.now(timezone.utc).timestamp())))
            await self.bot.store.unqueue_user(settings.mm_queue_channel, user_id)

            if reminder_msg: await reminder_msg.delete()
            user = self.bot.get_user(user_id)
            if user:
                embed = nextcord.Embed(
                    title="Queue", 
                    description=f"You were removed from the queue in \n<#{settings.mm_queue_channel}>.", 
                    color=VALORS_THEME1_1)
                await user.send(embed=embed)
            self.active_users.pop(user_id, None)
            self.tasks.pop(user_id, None)
        except Exception as e:
            log.critical(f"[QueueManager] {repr(e)}")

    def add_user(self, user_id: int, expiry_timestamp: int):
        if user_id in self.tasks:
            self.remove_user(user_id)
        self.active_users[user_id] = expiry_timestamp
        task = asyncio.create_task(self.reminder_and_kick(user_id, expiry_timestamp))
        self.tasks[user_id] = task

    def remove_user(self, user_id):
        if user_id in self.tasks:
            self.tasks[user_id].cancel()
            self.tasks.pop(user_id, None)
        self.active_users.pop(user_id, None)

    async def fetch_and_initialize_users(self):
        settings = await self.bot.store.get_settings(GUILD_ID)
        queue_users = await self.bot.store.get_queue_users(settings.mm_queue_channel)
        for user in queue_users:
            if user.queue_expiry > int(datetime.now(timezone.utc).timestamp()):
                self.add_user(user.user_id, user.queue_expiry)
            else:
                await self.bot.store.unqueue_user(settings.mm_queue_channel, user.user_id)
