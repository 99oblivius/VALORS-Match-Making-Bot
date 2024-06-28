from enum import IntEnum, auto
from typing import Dict, List
from functools import wraps

import asyncio
from pavlov import PavlovRCON

from nextcord.ext import commands

from utils.models import MMBotMatchUsers, Team

from config import SERVER_DM_MAP


class RCONManager:
    def safe_rcon(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            self = args[0]
            serveraddr = args[1]
            if serveraddr not in self.server_timeouts:
                self.server_timeouts[serveraddr] = asyncio.Lock()

            async with self.server_timeouts[serveraddr]:
                try:
                    result = func(*args, **kwargs)
                except ConnectionRefusedError:
                    if serveraddr in self.servers:
                        del self.servers[serveraddr]
                        del self.server_timeouts[serveraddr]
                    return None
                
                async def release_lock():
                    await asyncio.sleep(0.15)
                    self.server_timeouts[serveraddr].release()
                asyncio.create_task(release_lock())
                return result
        return wrapper

    def __init__(self, bot: commands.Bot):
        self.servers: Dict[str, PavlovRCON] = {}
        self.server_timeouts: Dict[str, asyncio.Lock] = {}
        self.bot = bot
    
    async def clear_dangling_servers(self):
        servers = await self.bot.store.get_servers(free=False)
        for server in servers:
            if server.being_used and f'{server.host}:{server.port}' not in self.servers:
                await self.bot.store.free_server(f'{server.host}:{server.port}')
    
    async def add_server(self, host: str, port: int, password: str) -> bool:
        rcon = PavlovRCON(host, port, password)
        try:
            reply = await rcon.send("ServerInfo")
        except ConnectionRefusedError:
            return False
        if reply and reply['Successful']:
            self.servers[f'{host}:{port}'] = rcon
            return True
        return False

    @safe_rcon
    async def remove_server(self, serveraddr: str):
        if serveraddr in self.servers:
            await self.servers[serveraddr].disconnect()
            del self.servers[serveraddr]

    @safe_rcon
    async def set_teamdeathmatch(self, serveraddr: str):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            await rcon.send(f"SwitchMap {SERVER_DM_MAP} tdm")

    @safe_rcon
    async def set_searchndestroy(self, serveraddr: str, resource_id: str):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            await rcon.send(f"SwitchMap {resource_id} snd")
    
    @safe_rcon
    async def server_info(self, serveraddr: str) -> dict:
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            reply = await rcon.send("ServerInfo")
            return reply['ServerInfo']
    
    @safe_rcon
    async def inspect_team(self, serveraddr: str, team: Team) -> List[dict]:
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            reply = await rcon.send(f"InspectTeam {team.value}")
            return reply['InspectList']
    
    @safe_rcon
    async def inspect_all(self, serveraddr: str) -> List[dict]:
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            reply = await rcon.send("InspectAll")
            return reply['InspectList']
    
    @safe_rcon
    async def set_pin(self, serveraddr: str, pin: str):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            await rcon.send(f"SetPin {pin}")
    
    @safe_rcon
    async def set_name(self, serveraddr: str, name: str):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            await rcon.send(f"UpdateServerName {name}")
    
    @safe_rcon
    async def player_list(self, serveraddr: str) -> List[dict]:
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            reply = await rcon.send("RefreshList")
            return reply['PlayerList']

    @safe_rcon
    async def kick_player(self, serveraddr: str, player_id: str):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            await rcon.send(f"Kick {player_id}")

    @safe_rcon
    async def ban_player(self, serveraddr: str, player_id: str):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            await rcon.send(f"Ban {player_id}")

    @safe_rcon
    async def unban_all_players(self, serveraddr: str):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            reply = await rcon.send("Banlist")
            for user in reply['BanList']:
                await rcon.send(f"Unban {user}")
                await asyncio.sleep(0.2)

    @safe_rcon
    async def allocate_team(self, serveraddr: str, platform_id: str, player: MMBotMatchUsers):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            if platform_id is None:
                await rcon.send(f"SwitchTeam {platform_id} {player.team.value}")

    @safe_rcon
    async def max_players(self, serveraddr: str, max_players: int):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            await rcon.send(f"SetMaxPlayers {max_players}")

    @safe_rcon
    async def comp_mode(self, serveraddr: str, state: bool=True):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            await rcon.send(f"EnableCompMode {str(state).lower()}")

    @safe_rcon
    async def start_search_and_destroy(self, serveraddr: str, map_id: str):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            await rcon.send(f"SwitchMap {map_id} snd")

    @safe_rcon
    async def list_banned_players(self, serveraddr: str):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            return await rcon.send("Banlist")
