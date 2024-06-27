from enum import IntEnum, auto
from typing import Dict, List

import asyncio
from pavlov import PavlovRCON

from nextcord.ext import commands

from utils.models import MMBotMatchUsers

from config import SERVER_DM_MAP


class PavlovState(IntEnum):
    NOT_STARTED   = auto()
    INITIALIZING  = auto()
    RUNNING       = auto()
    ENDED         = auto()


class RCONManager:
    def __init__(self, bot: commands.Bot):
        self.servers: Dict[str, PavlovRCON] = {}
        self.bot = bot
    
    async def add_server(self, host: str, port: int, password: str) -> str:
        rcon = await PavlovRCON.create(host, port, password)
        self.servers[f'{host}:{port}'] = rcon
        await self.set_server_to_deathmatch(f'{host}:{port}')
        return f'{host}:{port}'

    async def remove_server(self, serveraddr: str):
        if serveraddr in self.servers:
            await self.servers[serveraddr].disconnect()
            del self.servers[serveraddr]

    async def set_server_to_deathmatch(self, serveraddr: str):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            await rcon.send(f"SwitchMap {SERVER_DM_MAP} tdm")

    async def ban_player(self, serveraddr: str, player_id: str):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            await rcon.send(f"Ban {player_id}")

    async def unban_all_players(self, serveraddr: str):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            reply = await rcon.send("Banlist")
            for user in reply['BanList']:
                await rcon.send(f"Unban {user}")
                await asyncio.sleep(0.2)

    async def allocate_team(self, serveraddr: str, match_id: int, player: MMBotMatchUsers):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            player = await self.bot.store.get_player(match_id, player.user_id)
            reply = await rcon.send(f"InspectTeam {player.team.value}")
            
            platform_id = next(
                (p.platform_id for inspect_player in reply['InspectList'] 
                    for p in player.user_platform_mappings
                    if inspect_player['Uniqueid'] == p.platform_id
                ), None)
            if platform_id is None:
                await rcon.send(f"SwitchTeam {platform_id} {player.team.value}")

    async def start_search_and_destroy(self, serveraddr: str, map_id: str):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            await rcon.send(f"SwitchMap {map_id} snd")

    async def list_banned_players(self, serveraddr: str):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            return await rcon.send("Banlist")

class Pavlov:
    def __init__(self, loop):
        self.state: PavlovState = PavlovState.NOT_STARTED
        self._conn: PavlovRCON = PavlovRCON("127.0.0.1", 9104, "password")
        loop.create_task(self.match_state())
    
    async def match_state(self):
        self.state = PavlovState.INITIALIZING
        while True:
            data = await self._conn.send("ServerInfo")
            if not data:
                break
            self.state = PavlovState.RUNNING
            await asyncio.sleep(1)
            
        self.state = PavlovState.ENDED