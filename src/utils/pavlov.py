from enum import IntEnum, auto
from typing import Dict

import asyncio
from pavlov import PavlovRCON


class PavlovState(IntEnum):
    NOT_STARTED   = auto()
    INITIALIZING  = auto()
    RUNNING       = auto()
    ENDED         = auto()


class RCONManager:
    def __init__(self):
        self.servers: Dict[str, PavlovRCON] = {}
    
    async def add_server(self, host: str, port: int, password: str):
        rcon = await PavlovRCON.create(host, port, password)
        self.servers[f'{host}:{port}'] = rcon
        await self.set_server_to_deathmatch(f'{host}:{port}')

    async def remove_server(self, serveraddr: str):
        if serveraddr in self.servers:
            await self.servers[serveraddr].disconnect()
            del self.servers[serveraddr]

    async def set_server_to_deathmatch(self, serveraddr: str):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            await rcon.send("SwitchMap sand dm")

    async def ban_player(self, serveraddr: str, player_id: str):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            await rcon.send(f"Ban {player_id}")

    async def unban_all_players(self, serveraddr: str):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            await rcon.send("UnbanAll")

    async def auto_allocate_teams(self, serveraddr: str, player_ids: List[str]):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            half = len(player_ids) // 2
            for i, player_id in enumerate(player_ids):
                team_id = 0 if i < half else 1
                await rcon.send(f"SwitchTeam {player_id} {team_id}")

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