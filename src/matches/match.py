import asyncio
import traceback
from functools import wraps
import logging as log
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

from config import VALORS_THEME2, VALORS_THEME1_2, VALORS_THEME1, HOME_THEME, AWAY_THEME, MATCH_PLAYER_COUNT, SERVER_DM_MAP, STARTING_MMR
from .functions import get_preferred_bans, get_preferred_map, get_preferred_side, calculate_mmr_change
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
        if serveraddr:
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
                asyncio.create_task(notify_unaccepted_players(30)),
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
            time_to_ban = 20
            players = await self.bot.store.get_players(self.match_id)
            add_mention = (f"<@{player.user_id}>" for player in players if player.team == Team.A)
            embed = nextcord.Embed(title="Pick your 2 bans", description=format_duration(time_to_ban), color=HOME_THEME)
            view = await BanView.create_showable(self.bot, self.guild_id, match)
            a_message = await a_thread.send(''.join(add_mention), embed=embed, view=view)
            await self.bot.store.update(MMBotMatches, id=self.match_id,  a_message=a_message.id, phase=Phase.A_BAN)
            await asyncio.sleep(time_to_ban)
            await self.bot.store.update(MMBotMatches, id=self.match_id, phase=Phase.NONE)

            bans = await self.bot.store.get_ban_votes(self.match_id, Phase.A_BAN)
            bans = get_preferred_bans(maps, bans, total_bans=2)
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
            time_to_ban = 20
            players = await self.bot.store.get_players(self.match_id)
            embed = nextcord.Embed(title="Pick your 2 bans", description=format_duration(time_to_ban), color=AWAY_THEME)
            view = await BanView.create_showable(self.bot, self.guild_id, match)
            add_mention = (f"<@{player.user_id}>" for player in players if player.team == Team.B)
            b_message = await b_thread.send(''.join(add_mention), embed=embed, view=view)
            await self.bot.store.update(MMBotMatches, id=self.match_id, phase=Phase.B_BAN, b_message=b_message.id)
            await asyncio.sleep(time_to_ban)
            await self.bot.store.update(MMBotMatches, id=self.match_id, phase=Phase.NONE)
            
            bans = await self.bot.store.get_ban_votes(self.match_id, Phase.B_BAN)
            bans = get_preferred_bans(maps, bans, total_bans=2)
            view = ChosenBansView(bans)
            embed = nextcord.Embed(title="You banned", color=AWAY_THEME)
            await b_message.edit(embed=embed, view=view)
            embed = nextcord.Embed(title="B banned", color=AWAY_THEME)
            await a_thread.send(embed=embed, view=view)
            await self.bot.store.update(MMBotMatches, id=self.match_id, b_bans=bans)
            await self.increment_state()
            
        if check_state(MatchState.PICKING_START):
            embed = nextcord.Embed(title="Team A pick map", description=f"<#{a_thread.id}>", color=HOME_THEME)
            embed.add_field(name="Team A", 
                value='\n'.join([f"- <@{player.user_id}>" for player in players if player.team == Team.A]))
            embed.add_field(name="Team B", 
                value='\n'.join([f"- <@{player.user_id}>" for player in players if player.team == Team.B]))
            await match_message.edit(embed=embed)
            await self.increment_state()
        
        if check_state(MatchState.A_PICK):
            time_to_pick = 20
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
        
        if check_state(MatchState.PICK_SWAP):
            embed = nextcord.Embed(title="Team B pick side", description=f"<#{b_thread.id}>", color=AWAY_THEME)
            embed.add_field(name="Team A", 
                value='\n'.join([f"- <@{player.user_id}>" for player in players if player.team == Team.A]))
            embed.add_field(name="Team B", 
                value='\n'.join([f"- <@{player.user_id}>" for player in players if player.team == Team.B]))
            await match_message.edit(embed=embed)
            await self.increment_state()
        
        if check_state(MatchState.B_PICK):
            time_to_pick = 20
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
                while server is None or len(rcon_servers) > 0:
                    region_distribution = Counter([user.region for user in users])

                    def server_score(server_region):
                        return sum(region_distribution[server_region] for server_region in region_distribution)
                    
                    best_server = max(rcon_servers, key=lambda server: server_score(server.region))
                    successful = await self.bot.rcon_manager.add_server(best_server.host, best_server.port, best_server.password)
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
                await match_message.edit(embed=embed)
                self.state = MatchState.CLEANUP - 1
            await self.increment_state()
        
        if check_state(MatchState.MATCH_WAIT_FOR_PLAYERS):
            match = await self.bot.store.get_match(self.match_id)
            await self.bot.rcon_manager.set_teamdeathmatch(serveraddr, SERVER_DM_MAP)
            await self.bot.rcon_manager.unban_all_players(serveraddr)
            await self.bot.rcon_manager.comp_mode(serveraddr, state=True)
            await self.bot.rcon_manager.max_players(serveraddr, MATCH_PLAYER_COUNT)

            pin = 5
            await self.bot.rcon_manager.set_pin(serveraddr, pin)
            server_name = f"VALORS MM - {self.match_id}"
            await self.bot.rcon_manager.set_name(serveraddr, server_name)

            embed = nextcord.Embed(title="Match", description=f"Server ready!", color=VALORS_THEME1)
            embed.set_image(match_map.media)
            embed.add_field(name=f"Team A - {match_sides[0].name}", 
                value='\n'.join([f"- <@{player.user_id}>" for player in players if player.team == Team.A]))
            embed.add_field(name=f"Team B - {match_sides[1].name}", 
                value='\n'.join([f"- <@{player.user_id}>" for player in players if player.team == Team.B]))
            embed.add_field(name="TDM Server", value=f"`{server_name}`", inline=False)
            embed.add_field(name="Pin", value=f"`{pin}`")
            embed.add_field(name=f"{match_map.map}:", value="\u200B", inline=False)
            await match_message.edit(embed=embed)

            server_players = set()
            while len(server_players) < MATCH_PLAYER_COUNT:
                log.info(f"[{self.match_id}] Waiting on players: {len(server_players)}/{MATCH_PLAYER_COUNT}")
                player_list = await self.bot.rcon_manager.player_list(serveraddr)
                current_players = {p['UniqueId'] for p in player_list.get('PlayerList', [])}
                
                new_players = current_players - server_players
                if new_players:
                    log.info(f"[{self.match_id}] New players joined: {new_players}")
                    for platform_id in new_players:
                        player = next((
                            player for player in players 
                            for p in player.user_platform_mappings
                            if p.platform_id == platform_id
                        ), None)
                        
                        if player:
                            teamid = match.b_side.value if player.team == Team.B else 1 - match.b_side.value
                            team_list = await self.bot.rcon_manager.inspect_team(serveraddr, Team(teamid))
                            if platform_id not in (p['UniqueId'] for p in team_list.get('InspectList', [])):
                                log.info(f"[{self.match_id}] Moving player {platform_id} to team {teamid}")
                                await self.bot.rcon_manager.allocate_team(serveraddr, platform_id, teamid)
                        else:
                            log.info(f"[{self.match_id}] Unauthorized player {platform_id} detected. Kicking.")
                            await self.bot.rcon_manager.kick_player(serveraddr, platform_id)
                
                server_players = current_players
                await asyncio.sleep(2)
            await self.increment_state()
        
        if check_state(MatchState.MATCH_START_SND):
            m = next((m for m in maps if m.map == match.map), maps[0])
            server_maps = await self.bot.rcon_manager.list_maps(serveraddr)
            await self.bot.rcon_manager.add_map(serveraddr, m.resource_id if m.resource_id else m.map, 'SND')
            await self.bot.rcon_manager.set_searchndestroy(serveraddr, m.resource_id if m.resource_id else m.map)
            for m in server_maps.get('MapList', []):
                await self.bot.rcon_manager.remove_map(serveraddr, m['MapId'], m['GameMode'])

            embed = nextcord.Embed(title="Match started!", description="May the best team win!", color=VALORS_THEME1)
            await match_thread.send(embed=embed)
            await self.increment_state()
        
        if check_state(MatchState.MATCH_WAIT_FOR_END):
            team_scores = [0, 0]
            users_match_stats = {}
            last_users_match_stats = {}
            disconnection_tracker = {player.user_id: 0 for player in players}
            last_round_number = 0
            abandoned_users = []
            users_summary_data = await self.bot.store.get_users_summary_stats(self.guild_id, [p.user_id for p in players])

            gamemode = 'TDM'
            while gamemode != 'SND':
                reply = (await self.bot.rcon_manager.server_info(serveraddr))['ServerInfo']
                gamemode = reply['GameMode']
                await asyncio.sleep(2)

            while max(team_scores) < 10:
                try:
                    reply = (await self.bot.rcon_manager.server_info(serveraddr))['ServerInfo']
                    team_scores[0] = int(reply['Team0Score'])
                    team_scores[1] = int(reply['Team1Score'])
                    current_round = int(reply['Round'])

                    is_new_round = current_round > last_round_number
                    if is_new_round:
                        last_round_number = current_round
                        log.info(f"[{self.match_id}] Round {current_round} completed. Scores: {team_scores[0]} - {team_scores[1]}")

                    players_data = await self.bot.rcon_manager.inspect_all(serveraddr)
                    players_dict = { player['UniqueId']: player for player in players_data['InspectList'] }
                    
                    found_player_ids = { p.user_id: False for p in players }
                    for platform_id, player_data in players_dict.items():
                        player = next(
                            (player
                                for player in players
                                if any(platform_id == p.platform_id for p in player.user_platform_mappings)),
                            None)

                        teamid = match.b_side.value if player.team == Team.B else 1 - match.b_side.value
                        if int(player_data['TeamId']) != int(teamid):
                            log.info(f"[{self.match_id}] Moving player {platform_id} to team {teamid}")
                            await self.bot.rcon_manager.allocate_team(serveraddr, platform_id, teamid)
                        
                        if player:
                            user_id = player.user_id
                            found_player_ids[user_id] = True
                            if user_id not in users_match_stats:
                                users_match_stats[user_id] = {
                                    "mmr_before": users_summary_data.get(user_id, MMBotUserSummaryStats(mmr=STARTING_MMR)).mmr,
                                    "games": users_summary_data.get(user_id, MMBotUserSummaryStats(games=0)).games + 1,
                                    "ct_start": (player.team == Team.A) == (match.b_side == Side.T),
                                    "score": 0,
                                    "kills": 0,
                                    "deaths": 0,
                                    "assists": 0,
                                    "rounds_played": 0 }
                            
                            player_data = players_dict[platform_id]
                            kills, deaths, assists = map(int, player_data['KDA'].split('/'))
                            score = int(player_data['Score'])
                            ping = int(float(player_data['Ping']))
                            
                            users_match_stats[user_id].update({
                                "score": score,
                                "kills": kills,
                                "deaths": deaths,
                                "assists": assists,
                                "ping": ping })
                            
                            if is_new_round:
                                users_match_stats[user_id]['rounds_played'] += 1
                                disconnection_tracker[user_id] = 0
                        else:
                            log.info(f"[{self.match_id}] Unauthorized player {platform_id} detected. Kicking.")
                            await self.bot.rcon_manager.kick_player(serveraddr, platform_id)
                        
                    if is_new_round:
                        for pid, found in found_player_ids.items():
                            if not found:
                                disconnection_tracker[pid] += 1
                                if disconnection_tracker[pid] >= 5:
                                    abandoned_users.append(pid)
                    
                    if last_users_match_stats != users_match_stats:
                        await self.bot.store.upsert_users_match_stats(self.guild_id, self.match_id, users_match_stats)
                        last_users_match_stats = users_match_stats

                    if abandoned_users:
                        await self.bot.store.set_match_abandons(self.match_id, abandoned_users)
                        abandonee_match_update = {}
                        abandonee_summary_update = {}
                        for abandonee_id in abandoned_users:
                            player = next((p for p in players if p.user_id == abandonee_id), None)
                            if player:
                                user_id = player.user_id
                                await self.bot.store.add_abandon(self.guild_id, user_id)
                                # await match_thread.send(f"<@{user_id}> has abandoned the match for being disconnected 5 rounds in a row.")
                                ally_mmr = match.a_mmr if player.team == Team.A else match.b_mmr
                                enemy_mmr = match.b_mmr if player.team == Team.A else match.a_mmr
                                stats = users_match_stats.get(user_id, None)
                                if stats is None:
                                    users_match_stats[user_id] = {
                                        "mmr_before": users_summary_data.get(user_id, MMBotUserSummaryStats(mmr=STARTING_MMR)).mmr,
                                        "games": users_summary_data.get(user_id, MMBotUserSummaryStats(games=0)).games + 1,
                                        "ct_start": (player.team == Team.A) == (match.b_side == Side.T),
                                        "score": 0,
                                        "kills": 0,
                                        "deaths": 0,
                                        "assists": 0,
                                        "rounds_played": 0 }
                                users_match_stats[user_id]['mmr_change'] = calculate_mmr_change(stats, 
                                    abandoned=True, ally_team_avg_mmr=ally_mmr, enemy_team_avg_mmr=enemy_mmr)
                                abandonee_match_update[user_id] = users_match_stats[user_id]
                                abandonee_summary_update[user_id] = { "mmr": users_summary_data[user_id].mmr + users_match_stats[user_id]['mmr_change'] }

                        await self.bot.store.upsert_users_match_stats(self.guild_id, self.match_id, abandonee_match_update)
                        await self.bot.store.set_users_summary_stats(self.guild_id, abandonee_summary_update)
                        self.state = MatchState.MATCH_CLEANUP - 1
                        break
                except Exception as e:
                    log.error(f"Error during match {self.match_id}: {traceback.format_exc()}")
                await asyncio.sleep(2)
            
            if not abandoned_users:
                final_updates = {}
                for player in players:
                    user_id = player.user_id
                    if user_id in users_match_stats:
                        current_stats = users_match_stats.get(user_id, None)
                        if current_stats is None:
                            users_match_stats[user_id] = {
                                "mmr_before": users_summary_data.get(user_id, MMBotUserSummaryStats(mmr=STARTING_MMR)).mmr,
                                "games": users_summary_data.get(user_id, MMBotUserSummaryStats(games=0)).games + 1,
                                "ct_start": (player.team == Team.A) == (match.b_side == Side.T),
                                "score": 0,
                                "kills": 0,
                                "deaths": 0,
                                "assists": 0,
                                "rounds_played": 0 }
                        ct_start = current_stats['ct_start']
                        win = team_scores[1] > team_scores[0] if ct_start else team_scores[0] > team_scores[1]

                        ally_score = team_scores[1] if ct_start else team_scores[0]
                        enemy_score = team_scores[0] if ct_start else team_scores[1]
                        ally_mmr = match.a_mmr if player.team == Team.A else match.b_mmr
                        enemy_mmr = match.b_mmr if player.team == Team.A else match.a_mmr
                        mmr_change = calculate_mmr_change(current_stats, 
                            ally_team_score=ally_score, enemy_team_score=enemy_score, ally_team_avg_mmr=ally_mmr, enemy_team_avg_mmr=enemy_mmr, win=win)
                        current_stats.update({ "win": win, "mmr_change": mmr_change })
                        final_updates[user_id] = current_stats

                await self.bot.store.upsert_users_match_stats(self.guild_id, self.match_id, final_updates)
                
                users_summary_stats = {}
                for player in players:
                    user_id = player.user_id
                    if user_id in users_match_stats:
                        match_stats = users_match_stats[user_id]
                        summary_data = users_summary_data[user_id]

                        users_summary_stats[user_id] = {
                            "mmr": summary_data.mmr + match_stats['mmr_change'],
                            "games": summary_data.games + 1,
                            "wins": summary_data.wins + int(match_stats['win']),
                            "losses": summary_data.losses + int(not match_stats['win']),
                            "ct_starts": summary_data.ct_starts + int(match_stats['ct_start']),
                            "top_score": max(match_stats['score'], summary_data.top_score),
                            "top_kills": max(match_stats['kills'], summary_data.top_kills),
                            "top_assists": max(match_stats['assists'], summary_data.top_assists),
                            "total_score": summary_data.total_score + match_stats['score'],
                            "total_kills": summary_data.total_kills + match_stats['kills'],
                            "total_deaths": summary_data.total_deaths + match_stats['deaths'],
                            "total_assists": summary_data.total_assists + match_stats['assists']
                        }
                await self.bot.store.set_users_summary_stats(self.guild_id, users_summary_stats)

            rank_roles = sorted(
                [(r.mmr_threshold, guild.get_role(r.role_id)) 
                for r in await self.bot.store.get_ranks(self.guild_id)], key=lambda x: x[0], reverse=True)
            
            def get_rank_role(mmr):
                return next((role for threshold, role in rank_roles if mmr >= threshold), None)
            
            role_update_tasks = []
            for player in players:
                user_id = player.user_id
                if user_id in users_match_stats and user_id in users_summary_data:
                    old_mmr = users_summary_data[user_id].mmr
                    new_mmr = old_mmr + users_match_stats[user_id]['mmr_change']
                    
                    old_rank_role = get_rank_role(old_mmr)
                    new_rank_role = get_rank_role(new_mmr)

                    if old_rank_role != new_rank_role:
                        member = guild.get_member(user_id)
                        if member:
                            if old_rank_role:
                                role_update_tasks.append(member.remove_roles(old_rank_role, reason="Updating MMR rank"))
                            if new_rank_role:
                                role_update_tasks.append(member.add_roles(new_rank_role, reason="Updating MMR rank"))
            await asyncio.gather(*role_update_tasks)

            await self.increment_state()
        
        if check_state(MatchState.MATCH_CLEANUP):
            pin = 5
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
            if serveraddr:
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