import aiohttp
from typing import Dict
from nextcord import Guild
from nextcord.ext import commands
from config import DISCORD_TOKEN

class CommandCache:
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._cache: Dict[int, Dict[str, int]] = {}

    async def get_command_id(self, guild: Guild, command_name: str) -> int | None:
        name = command_name.split(' ')[0]
        if guild.id not in self._cache or name not in self._cache[guild.id]:
            await self.update_cache(guild)
        return self._cache[guild.id].get(name, None)

    async def update_cache(self, guild: Guild):
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
            response = await session.get(f"https://discord.com/api/v10/applications/{self.bot.user.id}/guilds/{guild}/commands", headers=headers)
            response.raise_for_status()
            all_responses.extend(await response.json())
        
        self._cache[guild.id] = {}
        for c in all_responses:
            self._cache[guild.id][c['name']] = int(c['id'])
        print(self._cache)
    
    async def get_command_mention(self, guild: Guild, full_command_name: str) -> str:
        command_id = await self.get_command_id(guild, full_command_name)
        if command_id:
            return f"</{full_command_name}:{command_id}>"
        return full_command_name