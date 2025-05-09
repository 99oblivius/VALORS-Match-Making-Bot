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
from functools import wraps
from typing import Dict

from nextcord.ext import commands
from pavlov import PavlovRCON

from utils.models import Team


class RCONManager:
    def safe_rcon(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            self = args[0]
            serveraddr = args[1]
            if serveraddr not in self.server_timeouts:
                self.server_timeouts[serveraddr] = asyncio.Lock()
            async with self.server_timeouts[serveraddr]:
                attempts = 0
                while attempts < kwargs.get('retry_attempts', 10):
                    try:
                        result = await func(*args, **kwargs)
                        # log.debug(f"[{func.__name__} n={attempts} addr={serveraddr}] {str(result)[:89 if len(str(result)) > 92 else 92]}{'...' if len(str(result)) > 92 else ''}")
                        if isinstance(result, str): result = None
                        if result and result.get('Successful', True):
                            async def delay_release():
                                await asyncio.sleep(0.15)
                            asyncio.create_task(delay_release())
                            return dict() if result is None else result
                    except (TimeoutError, ConnectionRefusedError):
                        if serveraddr in self.servers:
                            del self.servers[serveraddr]
                            del self.server_timeouts[serveraddr]
                        return dict()
                    attempts += 1
                    await asyncio.sleep(1)
                return dict()
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
        reply = None
        rcon = PavlovRCON(host, port, password)
        count = 0
        while count < 3:
            try:
                reply = await rcon.send("ServerInfo")
                break
            except ConnectionRefusedError:
                return False
            except Exception:
                await asyncio.sleep(1)
                count += 1
        if reply and isinstance(reply, dict) and reply.get('Successful', False):
            self.servers[f'{host}:{port}'] = rcon
            return True
        return False

    @safe_rcon
    async def remove_server(self, serveraddr: str, *args, **kwargs):
        if serveraddr in self.servers:
            await self.servers[serveraddr].disconnect()
            del self.servers[serveraddr]

    @safe_rcon
    async def set_teamdeathmatch(self, serveraddr: str, resource_id: str, *args, **kwargs):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            return await rcon.send(f"SwitchMap {resource_id} TDM")

    @safe_rcon
    async def set_searchndestroy(self, serveraddr: str, resource_id: str, *args, **kwargs):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            return await rcon.send(f"SwitchMap {resource_id} SND")
    
    @safe_rcon
    async def add_map(self, serveraddr: str, resource_id: str, mode: str, *args, **kwargs):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            return await rcon.send(f"AddMapRotation {resource_id} {mode}")
    
    @safe_rcon
    async def remove_map(self, serveraddr: str, resource_id: str, mode: str, *args, **kwargs):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            return await rcon.send(f"RemoveMapRotation {resource_id} {mode}")

    @safe_rcon
    async def server_info(self, serveraddr: str, *args, **kwargs) -> dict:
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            reply = await rcon.send("ServerInfo")
            return reply
    
    @safe_rcon
    async def inspect_team(self, serveraddr: str, team: Team, *args, **kwargs):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            reply = await rcon.send(f"InspectTeam {team.value}")
            return reply
    
    @safe_rcon
    async def inspect_all(self, serveraddr: str, *args, **kwargs):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            reply = await rcon.send("InspectAll")
            return reply
    
    @safe_rcon
    async def set_pin(self, serveraddr: str, pin: str, *args, **kwargs):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            return await rcon.send(f"SetPin {pin}")
    
    @safe_rcon
    async def set_name(self, serveraddr: str, name: str, *args, **kwargs):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            return await rcon.send(f"UpdateServerName {name}")
    
    @safe_rcon
    async def player_list(self, serveraddr: str, *args, **kwargs):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            reply = await rcon.send("RefreshList")
            return reply

    @safe_rcon
    async def kick_player(self, serveraddr: str, player_id: str, *args, **kwargs):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            return await rcon.send(f"Kick {player_id}")

    @safe_rcon
    async def ban_player(self, serveraddr: str, player_id: str, *args, **kwargs):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            return await rcon.send(f"Ban {player_id}")

    @safe_rcon
    async def kick_all(self, serveraddr: str, *args, **kwargs):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            reply = await rcon.send("InspectAll")
            for user in reply['InspectList']:
                await rcon.send(f"Kick {user['UniqueId']}")
                await asyncio.sleep(0.2)
            return {'Successful': True}

    @safe_rcon
    async def unban_all_players(self, serveraddr: str, *args, **kwargs):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            reply = await rcon.send("Banlist")
            for user in reply['BanList']:
                await rcon.send(f"Unban {user}")
                await asyncio.sleep(0.2)
            return {'Successful': True}

    @safe_rcon
    async def allocate_team(self, serveraddr: str, platform_id: str, teamid: int, *args, **kwargs):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            return await rcon.send(f"SwitchTeam {platform_id} {teamid}")

    @safe_rcon
    async def max_players(self, serveraddr: str, max_players: int, *args, **kwargs):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            return await rcon.send(f"SetMaxPlayers {max_players}")

    @safe_rcon
    async def comp_mode(self, serveraddr: str, state: bool=True, *args, **kwargs):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            return await rcon.send(f"EnableCompMode {str(state).lower()}")

    @safe_rcon
    async def start_search_and_destroy(self, serveraddr: str, map_id: str, *args, **kwargs):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            return await rcon.send(f"SwitchMap {map_id} SND")

    @safe_rcon
    async def list_banned_players(self, serveraddr: str, *args, **kwargs):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            return await rcon.send("Banlist")
    
    @safe_rcon
    async def list_maps(self, serveraddr: str, *args, **kwargs) -> dict:
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            return await rcon.send("MapList")
    
    @safe_rcon
    async def mod_list(self, serveraddr: str, *args, **kwargs) -> dict:
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            return await rcon.send("UGCModList")
    
    @safe_rcon
    async def add_mod(self, serveraddr: str, mod_id: str, *args, **kwargs):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            return await rcon.send(f"UGCAddMod {mod_id}")
    
    @safe_rcon
    async def clear_mods(self, serveraddr: str, *args, **kwargs):
        if serveraddr in self.servers:
            rcon = self.servers[serveraddr]
            return await rcon.send(f"UGCClearModList")
