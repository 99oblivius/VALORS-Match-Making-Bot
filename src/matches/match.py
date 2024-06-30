import asyncio
from functools import wraps
import logging as log
import time
from enum import Enum
import random
from typing import List
from collections import Counter

import nextcord
from nextcord.ext import commands
from utils.models import *
from .match_states import MatchState
from views.match.accept import AcceptView
from views.match.banning import BanView, ChosenBansView
from views.match.map_pick import MapPickView, ChosenMapView
from views.match.side_pick import SidePickView, ChosenSideView
from utils.utils import format_mm_attendance, format_duration

from config import VALORS_THEME2, VALORS_THEME1_2, VALORS_THEME1, HOME_THEME, AWAY_THEME, MATCH_PLAYER_COUNT, SERVER_DM_MAP
from .functions import get_preferred_bans, get_preferred_map, get_preferred_side
from .ranked_teams import get_teams


class Match:
    def __init__(self, bot: commands.Bot, guild_id: int, match_id: int, state=MatchState.NOT_STARTED):
        self.bot       = bot
        self.guild_id  = guild_id
        self.match_id  = match_id
        self.state     = state

    async def increment_state(self):
        self.state = MatchState(self.state + 1)
        await self.bot.store.save_match_state(self.match_id, self.state)

    async def load_state(self) -> MatchState:
        return await self.bot.store.load_match_state(self.match_id)

    async def change_state(self, new_state: MatchState):
        self.state = new_state
        await self.bot.store.save_match_state(self.match_id, self.state)
    
    def safe_exception(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            self = args[0]
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                log.exception(f"Exception in match {self.match_id}: {e}")
                guild = self.bot.get_guild(self.guild_id)
                match = await self.bot.store.get_match(self.match_id)
                if match and match.match_thread:
                    match_thread = guild.get_thread(match.match_thread)
                    if match_thread:
                        await match_thread.send(f"```diff\n- An error occurred: {e}```\nThe match has been frozen.")
                event = asyncio.Event()
                await event.wait()
        return wrapper
    
    @safe_exception
    async def run(self):
        await self.bot.wait_until_ready()
        if self.state > 0: log.info(
            f"[Match] Loaded ongoing match {self.match_id} state:{self.state}")
        
        def check_state(state: MatchState):
            return True if self.state == state else False
        
        self.state = await self.load_state()
        settings: BotSettings             = await self.bot.store.get_settings(self.guild_id)
        match: MMBotMatches               = await self.bot.store.get_match(self.match_id)
        players: List[MMBotMatchPlayers]  = await self.bot.store.get_players(self.match_id)
        maps: List[MMBotMaps]             = await self.bot.store.get_maps(self.guild_id)
        match_map                         = await self.bot.store.get_match_map(self.match_id)
        match_sides                       = await self.bot.store.get_match_sides(self.match_id)

        serveraddr                        = await self.bot.store.get_serveraddr(self.match_id)
        if self.state > MatchState.MATCH_FIND_SERVER:
            host, port = serveraddr.split(':')
            server = await self.bot.store.get_server(host, int(port))
            await self.bot.rcon_manager.add_server(server.host, server.port, server.password)
        
        guild = self.bot.get_guild(self.guild_id)
        queue_channel = guild.get_channel(settings.mm_queue_channel)

        match_thread  = guild.get_thread(match.match_thread)
        a_thread      = guild.get_thread(match.a_thread)
        b_thread      = guild.get_thread(match.b_thread)

        a_vc          = guild.get_channel(match.a_vc)
        b_vc          = guild.get_channel(match.b_vc)

        
        try:
            if match.match_message: match_message = await match_thread.fetch_message(match.match_message)
        except Exception: pass
        try:
            if match.a_message: a_message = await match_thread.fetch_message(match.a_message)
        except Exception: pass
        try:
            if match.b_message: b_message = await match_thread.fetch_message(match.b_message)
        except Exception: pass

        if check_state(MatchState.NOT_STARTED):
            print("NOT_STARTED")
            await self.increment_state()
        
        if check_state(MatchState.CREATE_MATCH_THREAD):
            match_thread = await queue_channel.create_thread(
                name=f"Match - #{self.match_id}",
                auto_archive_duration=1440,
                invitable=False,
                reason=f"Match - #{self.match_id}")
            await self.bot.store.update(MMBotMatches, id=self.match_id, match_thread=match_thread.id)
            await self.increment_state()
        
        if check_state(MatchState.ACCEPT_PLAYERS):
            add_mention = (f"<@{player.user_id}>" for player in players)
            embed = nextcord.Embed(title=f"Match - #{self.match_id}", color=VALORS_THEME2)
            embed.add_field(name=f"Attendance - {format_duration(settings.mm_accept_period)} to accept", value=format_mm_attendance(players))
            done_event = asyncio.Event()
            await match_thread.send(''.join(add_mention), embed=embed, view=AcceptView(self.bot, done_event))

            async def notify_unaccepted_players(delay: int=30):
                await asyncio.sleep(delay)
                if not done_event.is_set():
                    unaccepted_players = await self.bot.store.get_unaccepted_players(self.match_id)
                    for player in unaccepted_players:
                        member = guild.get_member(player.user_id)
                        if member:
                            embed = nextcord.Embed(
                                title="Queue Popped!", 
                                description=f"{format_duration(settings.mm_accept_period - delay)} left to ACCEPT\n{match_thread.mention}!", 
                                color=0x18ff18)
                            await member.send(embed=embed)

            notify_tasks = [
                asyncio.create_task(notify_unaccepted_players(20)),
                asyncio.create_task(notify_unaccepted_players(settings.mm_accept_period - 30))
            ]

            try:
                await asyncio.wait_for(done_event.wait(), timeout=settings.mm_accept_period)
            except asyncio.TimeoutError:
                self.state = MatchState.CLEANUP - 1
                embed = nextcord.Embed(title="Players failed to accept the match", color=VALORS_THEME1_2)
                await match_thread.send(embed=embed)
            finally: [task.cancel() for task in notify_tasks]
            await self.increment_state()
        
        if check_state(MatchState.MAKE_TEAMS):
            users = await self.bot.store.get_users(self.guild_id, [player.user_id for player in players])
            a_players, b_players, a_mmr, b_mmr = get_teams(users)
            await self.bot.store.set_players_team(
                match_id=self.match_id, 
                user_teams={Team.A: a_players, Team.B: b_players})
            players = await self.bot.store.get_players(self.match_id)
            await self.bot.store.update(MMBotMatches, id=self.match_id, a_mmr=a_mmr, b_mmr=b_mmr)
            await self.increment_state()
        
        if check_state(MatchState.MAKE_TEAM_VC_A):
            player_overwrites = { guild.get_member(player.user_id): nextcord.PermissionOverwrite(connect=True) for player in players if player.team == Team.A }
            player_overwrites.update({
                guild.default_role: nextcord.PermissionOverwrite(view_channel=True, connect=False),
                guild.get_role(settings.mm_staff_role): nextcord.PermissionOverwrite(view_channel=True, connect=True)
            })
            
            a_vc = await queue_channel.category.create_voice_channel(
                name=f"[{self.match_id}] Team A",
                overwrites=player_overwrites,
                reason=f"[{self.match_id}] Team A")
            await self.bot.store.update(MMBotMatches, id=self.match_id, a_vc=a_vc.id)
            await self.increment_state()
        
        if check_state(MatchState.MAKE_TEAM_VC_B):
            player_overwrites = { guild.get_member(player.user_id): nextcord.PermissionOverwrite(connect=True) for player in players if player.team == Team.B }
            player_overwrites.update({
                guild.default_role: nextcord.PermissionOverwrite(view_channel=True, connect=False),
                guild.get_role(settings.mm_staff_role): nextcord.PermissionOverwrite(view_channel=True, connect=True)
            })
            b_vc = await queue_channel.category.create_voice_channel(
                name=f"[{self.match_id}] ] Team B",
                overwrites=player_overwrites,
                reason=f"[{self.match_id}] Team B")
            await self.bot.store.update(MMBotMatches, id=self.match_id, b_vc=b_vc.id)
            await self.increment_state()
        
        if check_state(MatchState.MAKE_TEAM_THREAD_A):
            a_thread = await queue_channel.create_thread(
                name=f"[{self.match_id}] Team A",
                auto_archive_duration=1440,
                invitable=False,
                reason=f"[{self.match_id}] Team A")
            await self.bot.store.update(MMBotMatches, id=self.match_id, a_thread=a_thread.id)
            await self.increment_state()
        
        if check_state(MatchState.MAKE_TEAM_THREAD_B):
            b_thread = await queue_channel.create_thread(
                name=f"[{self.match_id}] Team B",
                auto_archive_duration=1440,
                invitable=False,
                reason=f"[{self.match_id}] Team B")
            await self.bot.store.update(MMBotMatches, id=self.match_id, b_thread=b_thread.id)
            await self.increment_state()
        
        if check_state(MatchState.BANNING_START):
            await match_thread.purge(bulk=True)
            embed = nextcord.Embed(title="Team A ban first", description=f"<#{a_thread.id}>", color=HOME_THEME)
            embed.add_field(name="Team A", 
                value='\n'.join([f"- <@{player.user_id}>" for player in players if player.team == Team.A]))
            embed.add_field(name="Team B", 
                value='\n'.join([f"- <@{player.user_id}>" for player in players if player.team == Team.B]))
            match_message = await match_thread.send(embed=embed)
            await self.bot.store.update(MMBotMatches, id=self.match_id, match_message=match_message.id)
            await self.increment_state()
        
        if check_state(MatchState.A_BANS):
            time_to_ban = 30
            players = await self.bot.store.get_players(self.match_id)
            add_mention = (f"<@{player.user_id}>" for player in players if player.team == Team.A)
            embed = nextcord.Embed(title="Pick your 2 bans", description=format_duration(time_to_ban), color=HOME_THEME)
            view = await BanView.create_showable(self.bot, self.guild_id, match)
            a_message = await a_thread.send(''.join(add_mention), embed=embed, view=view)
            await self.bot.store.update(MMBotMatches, id=self.match_id,  a_message=a_message.id, phase=Phase.A_BAN)
            await asyncio.sleep(time_to_ban)
            await self.bot.store.update(MMBotMatches, id=self.match_id, phase=Phase.NONE)

            bans = await self.bot.store.get_ban_votes(self.match_id, Phase.A_BAN)
            bans = get_preferred_bans([m.map for m in maps], bans, total_bans=2)
            view = ChosenBansView(bans)
            embed = nextcord.Embed(title="You banned", color=HOME_THEME)
            await a_message.edit(embed=embed, view=view)
            embed = nextcord.Embed(title="A banned", color=HOME_THEME)
            await b_thread.send(embed=embed, view=view)
            await self.bot.store.update(MMBotMatches, id=self.match_id, a_bans=bans)
            await self.increment_state()
        
        if check_state(MatchState.BAN_SWAP):
            embed = nextcord.Embed(title="Team B ban second", description=f"<#{b_thread.id}>", color=AWAY_THEME)
            embed.add_field(name="Team A", 
                value='\n'.join([f"- <@{player.user_id}>" for player in players if player.team == Team.A]))
            embed.add_field(name="Team B", 
                value='\n'.join([f"- <@{player.user_id}>" for player in players if player.team == Team.B]))
            await match_message.edit(embed=embed)
            await self.increment_state()
        
        if check_state(MatchState.B_BANS):
            time_to_ban = 30
            players = await self.bot.store.get_players(self.match_id)
            embed = nextcord.Embed(title="Pick your 2 bans", description=format_duration(time_to_ban), color=AWAY_THEME)
            view = await BanView.create_showable(self.bot, self.guild_id, match)
            add_mention = (f"<@{player.user_id}>" for player in players if player.team == Team.B)
            b_message = await b_thread.send(''.join(add_mention), embed=embed, view=view)
            await self.bot.store.update(MMBotMatches, id=self.match_id, phase=Phase.B_BAN, b_message=b_message.id)
            await asyncio.sleep(time_to_ban)
            await self.bot.store.update(MMBotMatches, id=self.match_id, phase=Phase.NONE)
            
            bans = await self.bot.store.get_ban_votes(self.match_id, Phase.B_BAN)
            bans = get_preferred_bans([m.map for m in maps], bans, total_bans=2)
            view = ChosenBansView(bans)
            embed = nextcord.Embed(title="You banned", color=AWAY_THEME)
            await b_message.edit(embed=embed, view=view)
            embed = nextcord.Embed(title="B banned", color=AWAY_THEME)
            await a_thread.send(embed=embed, view=view)
            await self.bot.store.update(MMBotMatches, id=self.match_id, b_bans=bans)
            await self.increment_state()
        
        if check_state(MatchState.A_PICK):
            time_to_pick = 30
            players = await self.bot.store.get_players(self.match_id)
            add_mention = (f"<@{player.user_id}>" for player in players if player.team == Team.A)
            embed = nextcord.Embed(title="Pick your map", description=format_duration(time_to_pick), color=HOME_THEME)
            view = await MapPickView.create_showable(self.bot, self.guild_id, match)
            a_message = await a_thread.send(''.join(add_mention), embed=embed, view=view)
            await self.bot.store.update(MMBotMatches, id=self.match_id,  a_message=a_message.id, phase=Phase.A_PICK)
            await asyncio.sleep(time_to_pick)
            await self.bot.store.update(MMBotMatches, id=self.match_id, phase=Phase.NONE)

            map_votes = await self.bot.store.get_map_votes(self.match_id)
            map_pick = get_preferred_map(maps, map_votes)
            view = ChosenMapView(map_pick.map)
            embed = nextcord.Embed(title="You picked", color=HOME_THEME)
            embed.set_thumbnail(map_pick.media)
            await a_message.edit(embed=embed, view=view)
            embed.title = "A picked"
            await b_thread.send(embed=embed, view=view)
            await self.bot.store.update(MMBotMatches, id=self.match_id, map=map_pick.map)
            await self.increment_state()
        
        if check_state(MatchState.B_PICK):
            time_to_pick = 30
            players = await self.bot.store.get_players(self.match_id)
            add_mention = (f"<@{player.user_id}>" for player in players if player.team == Team.B)
            embed = nextcord.Embed(title="Pick your side", description=format_duration(time_to_pick), color=AWAY_THEME)
            view = await SidePickView.create_showable(self.bot, self.guild_id, match)
            b_message = await b_thread.send(''.join(add_mention), embed=embed, view=view)
            await self.bot.store.update(MMBotMatches, id=self.match_id,  b_message=b_message.id, phase=Phase.B_PICK)
            await asyncio.sleep(time_to_pick)
            await self.bot.store.update(MMBotMatches, id=self.match_id, phase=Phase.NONE)

            side_votes = await self.bot.store.get_side_votes(self.match_id)
            side_pick = get_preferred_side([Side.T, Side.CT], side_votes)
            embed = nextcord.Embed(title="You picked", color=AWAY_THEME)
            await b_message.edit(embed=embed, view=ChosenSideView(side_pick))
            
            a_side = None
            if side_pick == Side.T: a_side = Side.CT
            elif side_pick == Side.CT: a_side = Side.T
            embed = nextcord.Embed(title="You are", color=AWAY_THEME)
            await a_thread.send(embed=embed, view=ChosenSideView(a_side))
            await self.bot.store.update(MMBotMatches, id=self.match_id, b_side=side_pick)
            await self.increment_state()

        if check_state(MatchState.MATCH_STARTING):
            await match_thread.purge(bulk=True)
            match_map = await self.bot.store.get_match_map(self.match_id)
            match_sides = await self.bot.store.get_match_sides(self.match_id)
            embed = nextcord.Embed(title="Starting", description="Setting up server", color=VALORS_THEME1)
            embed.set_image(match_map.media)
            embed.add_field(name=f"Team A - {match_sides[0].name}", 
                value='\n'.join([f"- <@{player.user_id}>" for player in players if player.team == Team.A]))
            embed.add_field(name=f"Team B - {match_sides[1].name}", 
                value='\n'.join([f"- <@{player.user_id}>" for player in players if player.team == Team.B]))
            embed.add_field(name=f"{match_map.map}:", value="\u200B", inline=False)
            match_message = await match_thread.send(embed=embed)

            embed = nextcord.Embed(
                title="Match starting!",
                description=f"Return to {match_thread.mention}",
                color=VALORS_THEME1)
            await a_thread.send(embed=embed)
            await b_thread.send(embed=embed)
            await self.bot.store.update(MMBotMatches, id=self.match_id, match_message=match_message.id)
            await self.increment_state()
        
        if check_state(MatchState.MATCH_FIND_SERVER):
            users = await self.bot.store.get_users(self.guild_id, [player.user_id for player in players])
            rcon_servers: List[RconServers] = await self.bot.store.get_servers(free=True)
            server = None
            if rcon_servers:
                print("RCON_SERVERS BEING CHECKED")
                while server is None or len(rcon_servers) > 0:
                    region_distribution = Counter([user.region for user in users])

                    def server_score(server_region):
                        return sum(region_distribution[server_region] for server_region in region_distribution)
                    
                    best_server = max(rcon_servers, key=lambda server: server_score(server.region))
                    print("GOING THROUGH SERVER ", best_server)
                    successful = await self.bot.rcon_manager.add_server(best_server.host, best_server.port, best_server.password)
                    log.critical(f"AAAAAAAAAAAAAA\nAAAAAAAAAAAAAAAA\nAAAAAAAAAAAAAAA\nsuccessful server add: {successful}")
                    if successful:
                        server = best_server
                        break
                    rcon_servers.remove(best_server)
                serveraddr = f'{server.host}:{server.port}'
                await self.bot.store.set_serveraddr(self.match_id, serveraddr)
                await self.bot.store.use_server(serveraddr)
            if not rcon_servers or server is None:
                embed = nextcord.Embed(title="Match", description="No running servers found.", color=VALORS_THEME1)
                embed.set_image(match_map.media)
                embed.add_field(name=f"Team A - {match_sides[0].name}", 
                    value='\n'.join([f"- <@{player.user_id}>" for player in players if player.team == Team.A]))
                embed.add_field(name=f"Team B - {match_sides[1].name}", 
                    value='\n'.join([f"- <@{player.user_id}>" for player in players if player.team == Team.B]))
                embed.add_field(name=f"{match_map.map}:", value="\u200B", inline=False)
                await match_thread.edit(embed=embed)
                self.state = MatchState.CLEANUP - 1
            await self.increment_state()
        
        if check_state(MatchState.MATCH_WAIT_FOR_PLAYERS):
            await self.bot.rcon_manager.set_teamdeathmatch(serveraddr, SERVER_DM_MAP)
            await self.bot.rcon_manager.unban_all_players(serveraddr)
            await self.bot.rcon_manager.comp_mode(serveraddr, state=True)
            await self.bot.rcon_manager.max_players(serveraddr, MATCH_PLAYER_COUNT)

            pin = ''.join(random.choices('0123456789', k=4))
            await self.bot.rcon_manager.set_pin(serveraddr, pin)
            server_name = f"VALORS MM - {self.match_id}"
            await self.bot.rcon_manager.set_name(serveraddr, server_name)

            embed = nextcord.Embed(title="Match", description=f"Server ready!", color=VALORS_THEME1)
            embed.set_image(match_map.media)
            embed.add_field(name=f"Team A - {match_sides[0].name}", 
                value='\n'.join([f"- <@{player.user_id}>" for player in players if player.team == Team.A]))
            embed.add_field(name=f"Team B - {match_sides[1].name}", 
                value='\n'.join([f"- <@{player.user_id}>" for player in players if player.team == Team.B]))
            embed.add_field(name="Server", value=f"`{server_name}`")
            embed.add_field(name="Pin", value=f"`{pin}`")
            embed.add_field(name=f"{match_map.map}:", value="\u200B", inline=False)
            await match_message.edit(embed=embed)

            server_players = {}
            while len(server_players) < MATCH_PLAYER_COUNT:
                log.info(f"[{self.match_id}] Waiting on players: {len(server_players)}/{MATCH_PLAYER_COUNT}")
                player_list = await self.bot.rcon_manager.player_list(serveraddr)
                current_players = { p['UniqueId'] for p in player_list.get('PlayerList', []) }
                print(f"current_players:\n{current_players}\nserver_players:\n{server_players}\n\n")
                if current_players != server_players:
                    server_players = current_players
                    new_players = current_players - server_players

                    for platform_id in new_players:
                        player = next((
                            player for player in players 
                            for p in player.user_platform_mappings
                            if p.platform_id == platform_id
                        ), None)
                        teamid = match.b_side.value if player.team == Team.B else 1 - match.b_side.value
                        team_list = await self.bot.rcon_manager.inspect_team(serveraddr, teamid)
                        if player and platform_id not in (p['UniqueId'] for p in team_list.get('InspectList', [])):
                            await self.bot.rcon_manager.allocate_team(serveraddr, platform_id, teamid)
                        else:
                            await self.bot.rcon_manager.kick_player(serveraddr, platform_id)
                await asyncio.sleep(2)
            await self.increment_state()
        
        if check_state(MatchState.MATCH_START_SND):
            m = next((m for m in maps if m.map == match.map), maps[0])
            server_maps = await self.bot.rcon_manager.list_maps(serveraddr)
            await self.bot.rcon_manager.add_map(serveraddr, m.resource_id if m.resource_id else m.map, 'SND')
            await self.bot.rcon_manager.set_searchndestroy(serveraddr, m.resource_id if m.resource_id else m.map)
            for m in server_maps.get('MapList', []):
                await self.bot.rcon_manager.remove_map(serveraddr, m['MapId'], m['GameMode'])

            embed = nextcord.Embed(title="Match", description="Match started!\nMay the best team win!", color=VALORS_THEME1)
            embed.set_image(match_map.media)
            embed.add_field(name=f"Team A - {match_sides[0].name}", 
                value='\n'.join([f"- <@{player.user_id}>" for player in players if player.team == Team.A]))
            embed.add_field(name=f"Team B - {match_sides[1].name}", 
                value='\n'.join([f"- <@{player.user_id}>" for player in players if player.team == Team.B]))
            embed.add_field(name=f"{match_map.map}:", value="\u200B", inline=False)
            await match_message.edit(embed=embed)
            await self.increment_state()
        
        if check_state(MatchState.MATCH_WAIT_FOR_END):
            team0score = 0
            team1score = 0
            while max(team0score, team1score) < 10:
                reply = (await self.bot.rcon_manager.server_info(serveraddr)).get('ServerInfo', None)
                team0score = int(reply.get('Team0Score', 0))
                team1score = int(reply.get('Team1Score', 0))
                await asyncio.sleep(2)
            
            a_won = (
                team1score == 10 and match.b_side.value == Side.T.value
            ) or (
                team0score == 10 and match.b_side.value == Side.CT.value
            )

            users_summary_data = await self.bot.store.get_users_summary_stats(self.guild_id, [p.user_id for p in players])

            users_match_stats = {}
            users_summary_stats = {}

            players_data = await self.bot.rcon_manager.inspect_all(serveraddr)
            players_dict = { player['UniqueId']: player for player in players_data.get('InspectList', []) }

            for platform_id, player_data in players_dict.items():
                player = next((
                    player for player in players 
                    for p in player.user_platform_mappings
                    if p.platform_id == platform_id
                ), None)
                
                if player:
                    summary_data = users_summary_data[player.user_id]

                    total_games = summary_data.games + 1
                    win = a_won if player.team == Team.A else not a_won
                    kills, deaths, assists = map(int, player_data['KDA'].split('/'))
                    ct_start = (
                        match.b_side == Side.T and player.team == Team.A
                        ) or (
                        match.b_side == Side.CT and player.team == Team.B)

                    users_match_stats[player.user_id] = {
                        "mmr": 800,
                        "games": total_games,
                        "win": win,
                        "ct_start": ct_start,
                        "score": int(player_data['Score']),
                        "kills": kills,
                        "deaths": deaths,
                        "assists": assists,
                        "ping": int(float(player_data['Ping']))
                    }

                    top_score = max(int(player_data['Score']), summary_data.top_score)
                    users_summary_stats[player.user_id] = {
                        "mmr": 800,
                        "games": total_games,
                        "wins": summary_data.wins + int(win),
                        "losses": summary_data.losses + int(not win),
                        "ct_starts": summary_data.ct_starts + int(ct_start),
                        "top_score": top_score,
                        "top_kills": max(kills, summary_data.top_kills),
                        "top_assists": max(assists, summary_data.top_assists),
                        "total_score": summary_data.total_score + int(player_data['Score']),
                        "total_kills": summary_data.total_kills + kills,
                        "total_deaths": summary_data.total_deaths + deaths,
                        "total_assists": summary_data.total_assists + assists
                    }

            await self.bot.store.add_users_match_stats(self.guild_id, self.match_id, users_match_stats)
            await self.bot.store.set_users_summary_stats(self.guild_id, users_summary_stats)
            await self.increment_state()
        
        if check_state(MatchState.MATCH_CLEANUP):
            pin = ''.join(random.choices('0123456789', k=4))
            server_name = f"VALORS {server.region} #{server.id}"
            await self.bot.rcon_manager.kick_all(serveraddr)
            await self.bot.rcon_manager.set_name(serveraddr, server_name)
            await self.bot.rcon_manager.set_pin(serveraddr, pin)
            await self.bot.rcon_manager.add_map(serveraddr, SERVER_DM_MAP, 'TDM')
            await self.bot.rcon_manager.set_teamdeathmatch(serveraddr, SERVER_DM_MAP)
            m = next((m for m in maps if m.map == match.map), maps[0])
            await self.bot.rcon_manager.remove_map(serveraddr, m.resource_id if m.resource_id else m.map, 'SND')
            await self.bot.rcon_manager.comp_mode(serveraddr, state=False)
            await self.bot.rcon_manager.max_players(serveraddr, 10)
            await self.increment_state()
        
        if check_state(MatchState.CLEANUP):
            await self.bot.store.free_server(serveraddr)
            await self.bot.rcon_manager.unban_all_players(serveraddr, retry_attempts=1)
            await self.bot.rcon_manager.comp_mode(serveraddr, state=False, retry_attempts=1)
            embed = nextcord.Embed(title="The match will terminate in 10 seconds", color=VALORS_THEME1)
            await match_thread.send(embed=embed)
            await asyncio.sleep(10)
            # match_thread
            try:
                if match_thread: await match_thread.delete()
            except nextcord.HTTPException: pass
            # a_thread
            try:
                if a_thread: await a_thread.delete()
            except nextcord.HTTPException: pass
            # b_thread
            try:
                if b_thread: await b_thread.delete()
            except nextcord.HTTPException: pass
            # move users back
            guild = self.bot.get_guild(self.guild_id)
            voice_channel = guild.get_channel(settings.mm_voice_channel)
            for player in players:
                member = guild.get_member(player.user_id)
                if member and member.voice and member.voice.channel in [a_vc, b_vc]:
                    await asyncio.sleep(0.1)
                    try: await member.move_to(voice_channel)
                    except nextcord.HTTPException: pass
            # a_vc
            try:
                if a_vc: await a_vc.delete()
            except nextcord.HTTPException as e:
                log.warning(f"[Match] a_vc deleting: {repr(e)}")
            # b_vc
            try:
                if b_vc: await b_vc.delete()
            except nextcord.HTTPException:
                log.warning(f"[Match] b_vc deleting: {repr(e)}")
            # complete True
            await self.bot.store.update(MMBotMatches, id=self.match_id, complete=True)
            await self.increment_state()