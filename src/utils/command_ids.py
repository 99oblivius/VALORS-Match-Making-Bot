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

import aiohttp
from typing import Dict
from nextcord.ext import commands
from config import DISCORD_TOKEN

class CommandCache:
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._cache: Dict[int, Dict[str, int]] = {}

    async def get_command_id(self, guild_id: int, command_name: str) -> int | None:
        name = command_name.split(' ')[0]
        if guild_id not in self._cache or name not in self._cache[guild_id]:
            await self.update_cache(guild_id)
        return self._cache[guild_id].get(name, None)

    async def update_cache(self, guild_id: int):
        all_commands = await self.get_all_commands(guild_id)
        self._cache[guild_id] = {}
        for c in all_commands:
            self._cache[guild_id][c['name']] = int(c['id'])
    
    async def get_all_commands(self, guild_id: int):
        all_responses = []
        headers = {
            'Authorization': f'Bot {DISCORD_TOKEN}', 
            'Content-Type': 'application/json'
        }
        async with aiohttp.ClientSession() as session:
            response = await session.get(f"https://discord.com/api/v10/applications/{self.bot.user.id}/commands", headers=headers)
            response.raise_for_status()
            all_responses.extend(await response.json())
        
        async with aiohttp.ClientSession() as session:
            response = await session.get(f"https://discord.com/api/v10/applications/{self.bot.user.id}/guilds/{guild_id}/commands", headers=headers)
            response.raise_for_status()
            all_responses.extend(await response.json())
        return all_responses
    
    async def get_command_mention(self, guild_id: int, full_command_name: str) -> str:
        command_id = await self.get_command_id(guild_id, full_command_name)
        if command_id:
            return f"</{full_command_name}:{command_id}>"
        return full_command_name