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

import asyncio
from datetime import datetime, timezone
from collections import deque

import nextcord

from config import GUILD_ID, VALORS_THEME1, VALORS_THEME1_1, VALORS_THEME2, MATCH_PLAYER_COUNT
from utils.logger import Logger as log
from utils.utils import format_duration


class QueueManager:
    def __init__(self, bot):
        self.bot = bot
        self.active_users = {}
        self.tasks = {}

        self.queue = deque()
        self.last_update = 0
        self.lock = asyncio.Lock()
        self.update_task = None

    async def update_presence(self, count: int=0):
        self.queue.append(count)
        if self.update_task is None or self.update_task.done():
            self.update_task = asyncio.create_task(self._process_updates())
    
    async def _process_updates(self):
        while True:
            async with self.lock:
                if not self.queue: return
                current_time = asyncio.get_event_loop().time()
                if current_time - self.last_update < 4:
                    await asyncio.sleep(4 - (current_time - self.last_update))
                
                count = self.queue.pop()
                self.queue.clear()

                await self.bot.change_presence(
                    activity=nextcord.CustomActivity(
                        name=f"Queue [{count}/{MATCH_PLAYER_COUNT}]"))

                self.last_update = asyncio.get_event_loop().time()
            await asyncio.sleep(4)

    async def reminder_and_kick(self, user_id: int, expiry: int):
        try:
            settings = await self.bot.store.get_settings(GUILD_ID)
            guild = self.bot.get_guild(GUILD_ID)
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

            channel = guild.get_channel(settings.mm_queue_channel)
            message = await channel.fetch_message(settings.mm_queue_message)
            queue_users = await self.bot.store.get_queue_users(channel.id)
            asyncio.create_task(self.update_presence(len(queue_users)))
            embed = nextcord.Embed(title="Queue", color=VALORS_THEME1)
            message_lines = []
            for n, item in enumerate(queue_users, 1):
                message_lines.append(f"{n}. <@{item.user_id}> `expires `<t:{item.queue_expiry}:R>")
            embed.add_field(name=f"{len(queue_users)} in queue", value=f"{'\n'.join(message_lines)}\u2800")
            await message.edit(embeds=[message.embeds[0], embed])
            self.active_users.pop(user_id, None)
            self.tasks.pop(user_id, None)
        except Exception as e:
            log.error(f"{repr(e)}")

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

    async def fetch_and_initialize_users(self) -> int:
        settings = await self.bot.store.get_settings(GUILD_ID)
        try:
            queue_users = await self.bot.store.get_queue_users(settings.mm_queue_channel)
            count = len(queue_users) if queue_users else 0
            asyncio.create_task(self.update_presence(count))
        except AttributeError:
            return log.warning("No GUILDS")
        for user in queue_users:
            if user.queue_expiry > int(datetime.now(timezone.utc).timestamp()):
                self.add_user(user.user_id, user.queue_expiry)
            else:
                await self.bot.store.unqueue_user(settings.mm_queue_channel, user.user_id)
