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
import functools
import copy
import traceback
from time import perf_counter_ns, time
from datetime import datetime, timezone
from typing import List, Dict, Tuple, cast, TYPE_CHECKING
from io import BytesIO

if TYPE_CHECKING:
    from main import Bot

import nextcord

from config import (
   B_THEME,
   A_THEME,
   MATCH_PLAYER_COUNT,
   SERVER_DM_MAP,
   STARTING_MMR,
   VALORS_THEME1,
   VALORS_THEME1_2,
   VALORS_THEME2,
   PLACEMENT_MATCHES
)
from utils.logger import Logger as log
from utils.models import *
from utils.utils import format_duration, format_mm_attendance, generate_score_image, generate_score_text, create_queue_embed, get_rank_role
from utils.statistics import update_leaderboard
from views.match.accept import AcceptView
from views.match.banning import BanView, ChosenBansView
from views.match.map_pick import ChosenMapView, MapPickView
from views.match.side_pick import ChosenSideView, SidePickView
from views.match.no_server_found import NoServerFoundView
from views.match.force_abandon import ForceAbandonView
from .functions import calculate_mmr_change, get_preferred_bans, get_preferred_map, get_preferred_side, calculate_placements_mmr, update_momentum
from .match_states import MatchState
from .ranked_teams import get_teams


class Match:
    def __init__(self, bot: 'Bot', guild_id: int, match_id: int, state=MatchState.NOT_STARTED):
        self.subtasks = set()
        self.bot: 'Bot'  = bot
        self.guild_id  = guild_id
        self.match_id  = match_id
        self.state     = state

        self.players       = []
        self.persistent_player_stats = {}
        self.user_platform_map = {}
        self.current_round = None

    def compute_user_platform_map(self):
        self.user_platform_map = {
            player.user_id: [m.platform_id for m in player.user_platform_mappings]
            for player in self.players
        }

    async def wait_for_snd_mode(self):
        while True:
            await asyncio.sleep(3)
            try:
                reply = (await self.bot.rcon_manager.server_info(str(self.match.serveraddr)))['ServerInfo']
                log.debug(f"WAITING FOR SND {reply}")
                if reply['GameMode'] == 'SND' and reply['PlayerCount'][0] != '0':
                    break
            except Exception as e:
                log.error(f"Error while waiting for SND mode: {str(e)}")
    
    async def show_no_server_found_message(self):
        embed = nextcord.Embed(
            title="Match", 
            description=f"No suitable servers found.", 
            color=VALORS_THEME1)
        done_event = asyncio.Event()
        view = NoServerFoundView(self.bot, self.match_id, done_event)
        
        if hasattr(self, 'no_server_message') and self.no_server_message:
            self.no_server_message = await self.no_server_message.edit(embed=embed, view=view)
        else:
            self.no_server_message = await self.match_channel.send(embed=embed, view=view)
        await done_event.wait()
    
    async def send_placements_reward_message(self, member: nextcord.Member, new_mmr: int):
        guild = member.guild
        ranks = await self.bot.store.get_ranks(guild.id)
        rank_role: nextcord.Role = get_rank_role(guild, ranks, new_mmr)
        embed = nextcord.Embed(
            title="You completed your placement matches!",
            description=f"Congratulations you were placed in `{rank_role.name}`!",
            color=rank_role.color)
        try:
            await member.send(embed=embed)
        except (nextcord.Forbidden, nextcord.HTTPException):
            pass
        settings = await self.bot.settings_cache(guild.id)

        embed = nextcord.Embed(
            title=f"Placements completed!",
            description=f"{member.mention} finished their {PLACEMENT_MATCHES} placement games.\nThey will start their adventure in {rank_role.mention}!",
            color=rank_role.color,
            timestamp=datetime.now(timezone.utc))
        await guild.get_channel(settings.mm_text_channel).send(embed=embed)
    
    async def estimate_user_server_ping(self, user_id: int, serveraddr: str, ping_data: Dict[Tuple[int, str], Dict[str, float]]) -> int:
        user_server = (user_id, serveraddr)
        if user_server in ping_data and ping_data[user_server] is not None:
            weighted_avg_ping = ping_data[user_server].get('weighted_avg_ping')
            if weighted_avg_ping is not None:
                return round(weighted_avg_ping)
        
        user = await self.bot.store.get_user(self.guild_id, user_id)
        host, port = serveraddr.split(':')
        server = await self.bot.store.get_server(host, int(port))
        
        if user.region == server.region:
            region_pings = [
                float(data.get('weighted_avg_ping', 50)) 
                for (_, addr), data in ping_data.items() 
                if addr.split(':')[0] == serveraddr.split(':')[0] 
                and data is not None 
                and data.get('weighted_avg_ping') is not None
            ]
            if region_pings:
                return round(sum(region_pings) / len(region_pings))
        
        region_difference = abs(ord(user.region[0]) - ord(server.region[0]))
        return 50 + region_difference * 20

    async def estimate_pings(self, rcon_servers: List[RconServers]):
        user_ids = [player.user_id for player in self.players]
        ping_data = await self.bot.store.get_weighted_player_server_pings(self.guild_id)
        
        estimated_pings = {}
        for server in rcon_servers:
            serveraddr = f"{server.host}:{server.port}"
            server_pings = {}
            for user_id in user_ids:
                ping = await self.estimate_user_server_ping(user_id, serveraddr, ping_data)
                server_pings[user_id] = ping
            estimated_pings[serveraddr] = server_pings
        return estimated_pings

    async def process_players(self, players_dict, disconnection_tracker, is_new_round):
        for platform_id, player_data in players_dict.items():
            user_id = next((uid for uid, pids in self.user_platform_map.items() if platform_id in pids), None)
            if user_id:
                player = next(p for p in self.players if p.user_id == user_id)
                
                await self.ensure_correct_team(player, platform_id, player_data)
                
                self.update_user_match_stats(self.persistent_player_stats[user_id], player_data)
                
                if is_new_round:
                    self.persistent_player_stats[user_id]['rounds_played'] += 1
                    disconnection_tracker[user_id] = 0
            else:
                log.info(f"[{self.match_id}] Unauthorized player {platform_id} detected. Kicking.")
                await self.bot.rcon_manager.kick_player(self.match.serveraddr, platform_id)
    
    async def upsert_user_stats(self, changed_users, last_users_match_stats, players_dict):
        changed_users.clear()
        for user_id, current_stats in self.persistent_player_stats.items():
            if user_id not in last_users_match_stats or current_stats != last_users_match_stats[user_id]:
                changed_users[user_id] = current_stats.copy()

                platform_ids = self.user_platform_map.get(user_id, [])
                for platform_id in platform_ids:
                    if platform_id in players_dict:
                        changed_users[user_id]["ping"] = int(float(players_dict[platform_id]['Ping']))
                        break
                else: changed_users[user_id]["ping"] = -1

        if changed_users:
            await self.bot.store.upsert_users_match_stats(self.guild_id, self.match_id, changed_users)
            for user_id in changed_users: del changed_users[user_id]["ping"]
            last_users_match_stats.update(copy.deepcopy(changed_users))

    async def ensure_correct_team(self, player, platform_id, player_data):
        teamid = self.match.b_side.value if player.team == Team.B else 1 - self.match.b_side.value
        if int(player_data['TeamId']) != int(teamid):
            log.info(f"[{self.match_id}] Moving player {platform_id} to team {teamid}")
            await self.bot.rcon_manager.allocate_team(self.match.serveraddr, platform_id, teamid)

    def initialize_user_match_stats(self, match_stats, users_summary_data):
        id_stats = { stats.user_id: stats for stats in match_stats }
        for p in self.players:
            if p.user_id in id_stats:
                stats = id_stats[p.user_id]
                self.persistent_player_stats[p.user_id] = {
                    "mmr_before": stats.mmr_before,
                    "games": stats.games,
                    "ct_start": stats.ct_start,
                    "score": stats.score,
                    "kills": stats.kills,
                    "deaths": stats.deaths,
                    "assists": stats.assists,
                    "rounds_played": stats.rounds_played,
                    "mmr_change": stats.mmr_change
                }
            else:
                self.persistent_player_stats[p.user_id] = {
                    "mmr_before": users_summary_data.get(p.user_id, MMBotUserSummaryStats(mmr=STARTING_MMR)).mmr,
                    "games": users_summary_data.get(p.user_id, MMBotUserSummaryStats(games=0)).games + 1,
                    "ct_start": (p.team == Team.A) == (self.match.b_side == Side.T),
                    "score": 0,
                    "kills": 0,
                    "deaths": 0,
                    "assists": 0,
                    "rounds_played": 0,
                    "mmr_change": None
                }

    def update_user_match_stats(self, user_stats, player_data):
        kills, deaths, assists = map(int, player_data['KDA'].split('/'))
        user_stats.update({
            "score": int(player_data['Score']),
            "kills": kills,
            "deaths": deaths,
            "assists": assists
        })

    def update_summary_stats(self, summary_data, match_stats):
        return {
            "mmr": summary_data.mmr + match_stats['mmr_change'],
            "momentum": update_momentum(summary_data.momentum, match_stats['win']),
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
    
    async def finalize_match(self, users_summary_data, team_scores):
        final_updates = {}
        users_summary_stats = {}
        placement_completions = []

        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            log.error(f"Could not find guild with id {self.guild_id}")
            return
        
        ranks = await self.bot.store.get_ranks(self.guild_id)
        rank_ids = { r.role_id for r in ranks }

        played_games = await self.bot.store.get_users_played_games([user.user_id for user in self.players], self.guild_id)
        for player in self.players:
            user_id = player.user_id
            if user_id not in self.persistent_player_stats:
                continue

            member = guild.get_member(user_id)
            games_played = played_games[player.user_id]
            current_stats = self.persistent_player_stats[user_id]
            summary_data = users_summary_data[user_id]

            if current_stats["mmr_change"] is not None:
                if games_played == PLACEMENT_MATCHES:
                    placement_completions.append((member, summary_data.mmr))
                continue

            ct_start = current_stats['ct_start']
            win = team_scores[0] > team_scores[1] if ct_start else team_scores[1] > team_scores[0]

            ally_score = team_scores[0] if ct_start else team_scores[1]
            enemy_score = team_scores[1] if ct_start else team_scores[0]
            ally_mmr = self.match.a_mmr if player.team == Team.A else self.match.b_mmr
            enemy_mmr = self.match.b_mmr if player.team == Team.A else self.match.a_mmr


            mmr_change = calculate_mmr_change(current_stats, 
                ally_team_score=ally_score, 
                enemy_team_score=enemy_score, 
                ally_team_avg_mmr=ally_mmr, 
                enemy_team_avg_mmr=enemy_mmr, win=win,
                placements=games_played <= PLACEMENT_MATCHES,
                momentum=summary_data.momentum)
            
            current_stats.update({"win": win, "mmr_change": mmr_change})

            new_mmr = summary_data.mmr + current_stats['mmr_change']
            if games_played == PLACEMENT_MATCHES:
                placement_completions.append((member, new_mmr))
            elif games_played >= PLACEMENT_MATCHES:
                new_rank_id = next((r.role_id for r in sorted(ranks, key=lambda x: x.mmr_threshold, reverse=True) if new_mmr >= r.mmr_threshold), None)

                if member:
                    current_rank_role_ids = set(role.id for role in member.roles if role.id in rank_ids)
                
                    if new_rank_id not in current_rank_role_ids:
                        
                        rank_roles = [guild.get_role(role_id) for role_id in current_rank_role_ids]
                        roles_to_remove = [role for role in rank_roles if role is not None]
                        if roles_to_remove:
                            asyncio.create_task(member.remove_roles(*roles_to_remove, reason="Updating MMR rank"))
                            log.info(f"Roles {', '.join(role.name for role in roles_to_remove)} removed from {member.display_name}")
                        
                        new_role = guild.get_role(new_rank_id)
                        if new_role:
                            asyncio.create_task(member.add_roles(new_role, reason="Updating MMR rank"))
                            log.info(f"Role {new_role.name} added to {member.display_name}")
            else:
                if member:
                    current_rank_role_ids = set(role.id for role in member.roles if role.id in rank_ids)
                    rank_roles = [guild.get_role(role_id) for role_id in current_rank_role_ids]
                    asyncio.create_task(member.remove_roles(*rank_roles))

            users_summary_stats[user_id] = self.update_summary_stats(summary_data, current_stats)
            final_updates[user_id] = current_stats
        
        team_a_score, team_b_score = (team_scores[1], team_scores[0]) if self.match.b_side == Side.CT else (team_scores[0], team_scores[1])
        self.match.a_score = team_a_score
        self.match.b_score = team_b_score
        await self.bot.store.update(MMBotMatches, id=self.match_id, a_score=team_a_score, b_score=team_b_score)

        await self.bot.store.upsert_users_match_stats(self.guild_id, self.match_id, final_updates)
        await self.bot.store.set_users_summary_stats(self.guild_id, users_summary_stats)

        users_placement_summary = {}
        guild_avg_scores = sorted([stats['avg_score'] for stats in await self.bot.store.get_leaderboard(self.guild_id)])
        for member, mmr in placement_completions:
            user_avg_score = (await self.bot.store.get_avg_stats_last_n_games(self.guild_id, member.id, PLACEMENT_MATCHES))['avg_score']
            new_mmr = calculate_placements_mmr(user_avg_score, guild_avg_scores, mmr)
            users_placement_summary[member.id] = { 'mmr': new_mmr }
            asyncio.create_task(self.send_placements_reward_message(member, new_mmr))
            log.info(f"User {member.id} has completed their placements and received {new_mmr - mmr} mmr from being at {mmr} mmr")
        if users_placement_summary:
            await self.bot.store.set_users_summary_stats(self.guild_id, users_placement_summary)

    async def start_requeue_players(self, settings: BotSettings):
        guild = self.bot.get_guild(cast(int, settings.guild_id))
        assert(isinstance(guild, nextcord.Guild))

        queue_users = await self.bot.store.get_queue_users(settings.mm_queue_channel)
        queue_players = sorted(queue_users, key=lambda user: user.timestamp, reverse=True)
        
        total_users_and_players = len(queue_players) + len(self.requeue_players)
        players_to_requeue = max(0, total_users_and_players - MATCH_PLAYER_COUNT)
        requeue_after = queue_players[:players_to_requeue]

        for user in requeue_after:
            self.bot.queue_manager.remove_user(user.user_id)
            await self.bot.store.unqueue_user(settings.mm_queue_channel, user.user_id)
        
        durations_left = await self.bot.store.get_user_last_queue_time_remaining(
            guild.id, self.match_id, self.requeue_players)
        for player_id in self.requeue_players:
            self.bot.queue_manager.add_user(player_id, int(datetime.now(timezone.utc).timestamp()) + durations_left[player_id] + 300)
            await self.bot.store.upsert_queue_user(
                    user_id=player_id, 
                    guild_id=settings.guild_id, 
                    queue_channel=settings.mm_queue_channel, 
                    queue_expiry=int(datetime.now(timezone.utc).timestamp()) + durations_left[player_id] + 300)
            log.debug(f"{member.display_name if (member := guild.get_member(player_id)) else player_id} has auto queued up")
            
        if total_users_and_players >= MATCH_PLAYER_COUNT:
            for user in queue_users: self.bot.queue_manager.remove_user(user.user_id)

            match_id = await self.bot.store.unqueue_add_match_users(settings, settings.mm_queue_channel)
            loop = asyncio.get_event_loop()
            from matches import make_match
            make_match(loop, self.bot, settings.guild_id, match_id)
        
        for user in requeue_after:
            self.bot.queue_manager.add_user(user.user_id, user.queue_expiry)
            await self.bot.store.upsert_queue_user(
                    user_id=user.user_id, 
                    guild_id=settings.guild_id, 
                    queue_channel=settings.mm_queue_channel, 
                    queue_expiry=user.queue_expiry)
            log.debug(f"{member.display_name if (member := guild.get_member(player_id)) else player_id} has auto requeued")
        
        queue_users = await self.bot.store.get_queue_users(settings.mm_queue_channel)
        asyncio.create_task(self.bot.queue_manager.update_presence(len(queue_users)))
        embed = create_queue_embed(queue_users)

        channel = guild.get_channel(cast(int, settings.mm_queue_channel))
        assert(isinstance(channel, nextcord.TextChannel))
        message = await channel.fetch_message(cast(int, settings.mm_queue_message))
        await message.edit(embeds=[message.embeds[0], embed])

    async def increment_state(self):
        self.state = MatchState(self.state + 1)
        log.debug(f"Match state -> {self.state}")
        await self.bot.store.save_match_state(self.match_id, self.state)

    async def load_state(self) -> MatchState:
        return await self.bot.store.load_match_state(self.match_id)

    async def change_state(self, new_state: MatchState):
        self.state = new_state
        await self.bot.store.save_match_state(self.match_id, self.state)
    
    def safe_exit(func):
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            self.subtasks = set()
            try:
                return await func(self, *args, **kwargs)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.critical(f"Exception in match {self.match_id}: {traceback.format_exc()}")
                guild = self.bot.get_guild(self.guild_id)
                match = await self.bot.store.get_match(self.match_id)
                if match and match.match_thread:
                    match_channel = guild.get_channel(match.match_thread)
                    if match_channel:
                        await match_channel.send(f"```diff\n- An error occurred: {e}```\nThe match has been frozen.")
            finally:
                for task in self.subtasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*self.subtasks, return_exceptions=True)
        return wrapper
    
    @safe_exit
    async def run(self):
        await self.bot.wait_until_ready()
        if self.state > 0: log.info(
            f"Loaded ongoing match {self.match_id} state:{self.state}")
        
        def check_state(state: MatchState):
            return True if self.state == state else False
        
        self.requeue_players = []
        
        self.state      = await self.load_state()
        settings        = await self.bot.settings_cache(self.guild_id)
        assert(isinstance(settings, BotSettings))
        guild           = self.bot.get_guild(self.guild_id)
        assert(isinstance(guild, nextcord.Guild))
        match_category  = guild.get_channel(cast(int, settings.mm_match_category))
        assert(isinstance(match_category, nextcord.CategoryChannel))
        text_channel    = guild.get_channel(cast(int, settings.mm_text_channel))
        assert(isinstance(text_channel, nextcord.TextChannel))

        self.match: MMBotMatches               = await self.bot.store.get_match(self.match_id)
        self.players: List[MMBotMatchPlayers]  = await self.bot.store.get_players(self.match_id)
        self.compute_user_platform_map()
        for p in self.players:
            if not guild.get_member(cast(int, p.user_id)):
                self.state = MatchState.CLEANUP
                await text_channel.send(
                    "```diff\n- A player has left the discord server during match initialization. -\nMatch canceled```")

        maps: List[MMBotMaps]             = await self.bot.store.get_maps(self.guild_id)
        match_map: MMBotMaps              = await self.bot.store.get_match_map(self.guild_id, self.match_id)
        self.last_map: str                = await self.bot.store.get_last_played_map(self.match.queue_channel)
        match_sides                       = await self.bot.store.get_match_sides(self.match_id)

        serveraddr                        = await self.bot.store.get_serveraddr(self.match_id)
        if serveraddr:
            host, port = serveraddr.split(':')
            server = await self.bot.store.get_server(host, port)
            await self.bot.rcon_manager.add_server(server.host, server.port, server.password)
        
        

        self.match_channel = guild.get_channel(cast(int, self.match.match_thread))
        log_channel   = guild.get_channel(cast(int, settings.mm_log_channel))
        
        a_channel     = guild.get_channel(cast(int, self.match.a_thread))
        b_channel     = guild.get_channel(cast(int, self.match.b_thread))

        a_vc          = guild.get_channel(cast(int, self.match.a_vc))
        b_vc          = guild.get_channel(cast(int, self.match.b_vc))
        
        if a_vc:
            self.bot.match_stages[a_vc.id] = [u.user_id for u in self.players if u.team == Team.A]
        if b_vc:
            self.bot.match_stages[b_vc.id] = [u.user_id for u in self.players if u.team == Team.B]

        try:
            if self.match.log_message:
                log_message    = await log_channel.fetch_message(self.match.log_message)
        except Exception: pass
        try:
            if self.match.match_message: 
                match_message  = await self.match_channel.fetch_message(self.match.match_message)
        except Exception: pass
        try:
            if self.match.a_message: 
                a_message      = await self.match_channel.fetch_message(self.match.a_message)
        except Exception: pass
        try:
            if self.match.b_message: 
                b_message      = await self.match_channel.fetch_message(self.match.b_message)
        except Exception: pass

        if check_state(MatchState.NOT_STARTED):
            await self.increment_state()
        
        if check_state(MatchState.CREATE_MATCH_CHANNEL):
            overwrites = {
                guild.get_member(cast(int, player.user_id)):
                    nextcord.PermissionOverwrite(
                        view_channel=True, send_messages=True, speak=True, stream=True, connect=True
                    ) for player in self.players
            }
            overwrites.update({ guild.default_role: nextcord.PermissionOverwrite(view_channel=False) })
            self.match_channel = await match_category.create_text_channel(
                name=f"Match - #{self.match_id}",
                overwrites=overwrites,
                reason=f"Match - #{self.match_id}")
            assert(isinstance(self.match_channel, nextcord.TextChannel))
            await self.bot.store.update(MMBotMatches, id=self.match_id, match_thread=self.match_channel.id)
            await self.increment_state()
        
        if check_state(MatchState.ACCEPT_PLAYERS):
            add_mention = []
            for player in self.players:
                add_mention.append(f"<@{player.user_id}>")
            embed = nextcord.Embed(title=f"Match - #{self.match_id}", color=VALORS_THEME2)
            embed.add_field(name=f"Attendance - {format_duration(settings.mm_accept_period)} to accept", value=format_mm_attendance(self.players))
            done_event = asyncio.Event()
            view = AcceptView(self.bot, done_event)
            await self.match_channel.send(''.join(add_mention), embed=embed, view=view)

            async def notify_unaccepted_players(delay: int=30):
                await asyncio.sleep(delay)
                if not done_event.is_set():
                    unaccepted_players = await self.bot.store.get_unaccepted_players(self.match_id)
                    for player in unaccepted_players:
                        member = guild.get_member(cast(int, player.user_id))
                        if member:
                            embed = nextcord.Embed(
                                title="Queue Popped!", 
                                description=f"{format_duration(settings.mm_accept_period - delay)} left to ACCEPT\n{self.match_channel.mention}!", 
                                color=0x18ff18)
                            try:
                                await member.send(embed=embed)
                            except (nextcord.Forbidden, nextcord.HTTPException):
                                pass

            notify_tasks = [
                asyncio.create_task(notify_unaccepted_players(30)),
                asyncio.create_task(notify_unaccepted_players(cast(int, settings.mm_accept_period) - 30))
            ]

            try:
                await asyncio.wait_for(done_event.wait(), timeout=float(cast(int, settings.mm_accept_period)))
            except asyncio.TimeoutError:
                self.requeue_players = view.accepted_players
                self.state = MatchState.CLEANUP - 1
                embed = nextcord.Embed(title="Players failed to accept the match", color=VALORS_THEME1_2)
                await self.match_channel.send(embed=embed)
                player_ids = [p.user_id for p in self.players]
                dodged_mentions = ' '.join((f'<@{userid}>' for userid in player_ids if userid not in view.accepted_players))
                await text_channel.send(f"{dodged_mentions}\nDid not accept the last match in time.\nRemaining players will be re-queued automatically.")
            finally: [task.cancel() for task in notify_tasks]
            await self.increment_state()

        if check_state(MatchState.MAKE_TEAMS):
            users = await self.bot.store.get_users(self.guild_id, [player.user_id for player in self.players])
            start = perf_counter_ns()
            a_players, b_players, a_mmr, b_mmr = get_teams(users)
            stop = perf_counter_ns()
            delay = (stop - start) / 1000000
            log.debug(f"Teams generated in {delay:.6f}ms")
            await self.bot.store.set_players_team(
                match_id=self.match_id, 
                user_teams={Team.A: a_players, Team.B: b_players})
            self.players = await self.bot.store.get_players(self.match_id)
            self.compute_user_platform_map()
            self.match.a_mmr = a_mmr
            self.match.b_mmr = b_mmr
            await self.bot.store.update(MMBotMatches, id=self.match_id, a_mmr=a_mmr, b_mmr=b_mmr)
            await self.increment_state()
        
        if check_state(MatchState.LOG_MATCH):
            embed = nextcord.Embed(
                title=f"Match #{self.match_id}",
                description="Teams created\nInitiating team votes",
                color=VALORS_THEME1)
            embed.add_field(name=f"[{self.match.a_mmr:.0f}]Team A", 
                value='\n'.join([f"- <@{player.user_id}>" for player in self.players if player.team == Team.A]))
            embed.add_field(name=f"[{self.match.b_mmr:.0f}]Team B", 
                value='\n'.join([f"- <@{player.user_id}>" for player in self.players if player.team == Team.B]))
            embed.set_footer(text=f"Match started ")
            embed.timestamp = datetime.now(timezone.utc)
            log_message = await log_channel.send(embed=embed)
            await self.bot.store.update(MMBotMatches, id=self.match_id, log_message=log_message.id)
            await self.increment_state()
        
        if check_state(MatchState.MAKE_TEAM_VC_A):
            overwrites = {
                guild.get_member(cast(int, player.user_id)):
                    nextcord.PermissionOverwrite(
                        view_channel=True, send_messages=True, speak=True, stream=True, connect=True, manage_channels=False
                    ) for player in self.players if player.team == Team.A
            }
            overwrites.update({ guild.default_role: nextcord.PermissionOverwrite(view_channel=True, connect=True, speak=False, stream=False) })
            a_vc = await match_category.create_voice_channel(
                name=f"[{self.match_id}] Team A",
                overwrites=overwrites,
                reason=f"[{self.match_id}] Team A",
                rtc_region=nextcord.VoiceRegion.us_east)
            self.bot.match_stages[a_vc.id] = [u.user_id for u in self.players if u.team == Team.A]
            await self.bot.store.update(MMBotMatches, id=self.match_id, a_vc=a_vc.id)
            await self.increment_state()
        
        if check_state(MatchState.MAKE_TEAM_VC_B):
            overwrites = {
                guild.get_member(cast(int, player.user_id)):
                    nextcord.PermissionOverwrite(
                        view_channel=True, send_messages=True, speak=True, stream=True, connect=True, manage_channels=False
                    ) for player in self.players if player.team == Team.B
            }
            overwrites.update({ guild.default_role: nextcord.PermissionOverwrite(view_channel=True, connect=True, speak=False, stream=False) })
            b_vc = await match_category.create_voice_channel(
                name=f"[{self.match_id}] Team B",
                overwrites=overwrites,
                reason=f"[{self.match_id}] Team B",
                rtc_region=nextcord.VoiceRegion.us_east)
            self.bot.match_stages[a_vc.id] = [u.user_id for u in self.players if u.team == Team.B]
            await self.bot.store.update(MMBotMatches, id=self.match_id, b_vc=b_vc.id)
            await self.increment_state()
        
        if check_state(MatchState.MAKE_TEAM_CHANNEL_A):
            overwrites = {
                guild.get_member(cast(int, player.user_id)):
                    nextcord.PermissionOverwrite(
                        view_channel=True, send_messages=True, speak=True, stream=True, connect=True
                    ) for player in self.players if player.team == Team.A
            }
            overwrites.update({ guild.default_role: nextcord.PermissionOverwrite(view_channel=False) })
            a_channel = await match_category.create_text_channel(
                name=f"[{self.match_id}] Team A",
                overwrites=overwrites,
                reason=f"[{self.match_id}] Team A")
            await self.bot.store.update(MMBotMatches, id=self.match_id, a_thread=a_channel.id)
            await self.increment_state()
        
        if check_state(MatchState.MAKE_TEAM_CHANNEL_B):
            overwrites = {
                guild.get_member(cast(int, player.user_id)):
                    nextcord.PermissionOverwrite(
                        view_channel=True, send_messages=True, speak=True, stream=True, connect=True
                    ) for player in self.players if player.team == Team.B
            }
            overwrites.update({ guild.default_role: nextcord.PermissionOverwrite(view_channel=False) })
            b_channel = await match_category.create_text_channel(
                name=f"[{self.match_id}] Team B",
                overwrites=overwrites,
                reason=f"[{self.match_id}] Team B")
            await self.bot.store.update(MMBotMatches, id=self.match_id, b_thread=b_channel.id)
            await self.increment_state()
        
        if check_state(MatchState.BANNING_START):
            await self.match_channel.purge(bulk=True)
            embed = nextcord.Embed(title="Team A ban first", description=f"<#{a_channel.id}>", color=A_THEME)
            embed.add_field(name="Team A", 
                value='\n'.join([f"- <@{player.user_id}>" for player in self.players if player.team == Team.A]))
            embed.add_field(name="Team B", 
                value='\n'.join([f"- <@{player.user_id}>" for player in self.players if player.team == Team.B]))
            match_message = await self.match_channel.send(embed=embed)
            await self.bot.store.update(MMBotMatches, id=self.match_id, match_message=match_message.id)
            await self.increment_state()
        
        if check_state(MatchState.A_BANS):
            time_to_ban = 20
            self.players = await self.bot.store.get_players(self.match_id)
            add_mention = [f"<@{player.user_id}>" for player in self.players if player.team == Team.A]
            embed = nextcord.Embed(title="Pick your 2 bans", description=format_duration(time_to_ban), color=A_THEME)
            view = await BanView.create_showable(self.bot, self.guild_id, self.match, self.last_map)
            a_message = await a_channel.send(''.join(add_mention), embed=embed, view=view)
            await self.bot.store.update(MMBotMatches, id=self.match_id,  a_message=a_message.id, phase=Phase.A_BAN)
            await asyncio.sleep(time_to_ban)
            await self.bot.store.update(MMBotMatches, id=self.match_id, phase=Phase.NONE)

            bans = await self.bot.store.get_ban_votes(self.match_id, Phase.A_BAN)
            bans = get_preferred_bans(maps, bans, total_bans=2)
            view = ChosenBansView(bans)
            embed = nextcord.Embed(title="You banned", color=A_THEME)
            await a_message.edit(embed=embed, view=view)
            embed = nextcord.Embed(title="A banned", color=A_THEME)
            await b_channel.send(embed=embed, view=view)
            await self.bot.store.update(MMBotMatches, id=self.match_id, a_bans=bans)
            await self.increment_state()
        
        if check_state(MatchState.BAN_SWAP):
            embed = nextcord.Embed(title="Team B ban second", description=f"<#{b_channel.id}>", color=B_THEME)
            embed.add_field(name="Team A", 
                value='\n'.join([f"- <@{player.user_id}>" for player in self.players if player.team == Team.A]))
            embed.add_field(name="Team B", 
                value='\n'.join([f"- <@{player.user_id}>" for player in self.players if player.team == Team.B]))
            await match_message.edit(embed=embed)
            await self.increment_state()
        
        if check_state(MatchState.B_BANS):
            time_to_ban = 20
            self.players = await self.bot.store.get_players(self.match_id)
            embed = nextcord.Embed(title="Pick your 2 bans", description=format_duration(time_to_ban), color=B_THEME)
            view = await BanView.create_showable(self.bot, self.guild_id, self.match, self.last_map)
            add_mention = [f"<@{player.user_id}>" for player in self.players if player.team == Team.B]
            b_message = await b_channel.send(''.join(add_mention), embed=embed, view=view)
            await self.bot.store.update(MMBotMatches, id=self.match_id, phase=Phase.B_BAN, b_message=b_message.id)
            await asyncio.sleep(time_to_ban)
            await self.bot.store.update(MMBotMatches, id=self.match_id, phase=Phase.NONE)
            
            bans = await self.bot.store.get_ban_votes(self.match_id, Phase.B_BAN)
            bans = get_preferred_bans(maps, bans, total_bans=2)
            view = ChosenBansView(bans)
            embed = nextcord.Embed(title="You banned", color=B_THEME)
            await b_message.edit(embed=embed, view=view)
            embed = nextcord.Embed(title="B banned", color=B_THEME)
            await a_channel.send(embed=embed, view=view)
            await self.bot.store.update(MMBotMatches, id=self.match_id, b_bans=bans)
            await self.increment_state()
        
        if check_state(MatchState.LOG_BANS):
            a_bans = await self.bot.store.get_bans(self.match_id, Team.A)
            b_bans = await self.bot.store.get_bans(self.match_id, Team.B)
            embed = log_message.embeds[0]
            embed.add_field(name="Bans", value=f"A: {', '.join(a_bans)}\nB: {', '.join(b_bans)}", inline=False)
            log_message = await log_message.edit(embed=embed)
            await self.increment_state()
            
        if check_state(MatchState.PICKING_START):
            embed = nextcord.Embed(title="Team A pick map", description=f"<#{a_channel.id}>", color=A_THEME)
            embed.add_field(name="Team A", 
                value='\n'.join([f"- <@{player.user_id}>" for player in self.players if player.team == Team.A]))
            embed.add_field(name="Team B", 
                value='\n'.join([f"- <@{player.user_id}>" for player in self.players if player.team == Team.B]))
            await match_message.edit(embed=embed)
            await self.increment_state()
        
        if check_state(MatchState.A_PICK):
            time_to_pick = 20
            self.players = await self.bot.store.get_players(self.match_id)
            add_mention = (f"<@{player.user_id}>" for player in self.players if player.team == Team.A)
            embed = nextcord.Embed(title="Pick your map", description=format_duration(time_to_pick), color=A_THEME)
            view = await MapPickView.create_showable(self.bot, self.guild_id, self.match, self.last_map)
            a_message = await a_channel.send(''.join(add_mention), embed=embed, view=view)
            await self.bot.store.update(MMBotMatches, id=self.match_id,  a_message=a_message.id, phase=Phase.A_PICK)
            await asyncio.sleep(time_to_pick)
            await self.bot.store.update(MMBotMatches, id=self.match_id, phase=Phase.NONE)

            map_votes = await self.bot.store.get_map_votes(self.match_id)
            map_pick = get_preferred_map(maps, map_votes)
            view = ChosenMapView(map_pick.map)
            embed = nextcord.Embed(title="You picked", color=A_THEME)
            embed.set_thumbnail(map_pick.media)
            await a_message.edit(embed=embed, view=view)
            embed.title = "A picked"
            await b_channel.send(embed=embed, view=view)
            await self.bot.store.update(MMBotMatches, id=self.match_id, map=map_pick.map)
            await self.increment_state()
        
        if check_state(MatchState.PICK_SWAP):
            embed = nextcord.Embed(title="Team B pick side", description=f"<#{b_channel.id}>", color=B_THEME)
            embed.add_field(name="Team A", 
                value='\n'.join([f"- <@{player.user_id}>" for player in self.players if player.team == Team.A]))
            embed.add_field(name="Team B", 
                value='\n'.join([f"- <@{player.user_id}>" for player in self.players if player.team == Team.B]))
            await match_message.edit(embed=embed)
            await self.increment_state()
        
        if check_state(MatchState.B_PICK):
            time_to_pick = 20
            self.players = await self.bot.store.get_players(self.match_id)
            add_mention = (f"<@{player.user_id}>" for player in self.players if player.team == Team.B)
            embed = nextcord.Embed(title="Pick your side", description=format_duration(time_to_pick), color=B_THEME)
            view = await SidePickView.create_showable(self.bot, self.guild_id, self.match)
            b_message = await b_channel.send(''.join(add_mention), embed=embed, view=view)
            await self.bot.store.update(MMBotMatches, id=self.match_id,  b_message=b_message.id, phase=Phase.B_PICK)
            await asyncio.sleep(time_to_pick)
            await self.bot.store.update(MMBotMatches, id=self.match_id, phase=Phase.NONE)

            side_votes = await self.bot.store.get_side_votes(self.match_id)
            side_pick = get_preferred_side([Side.T, Side.CT], side_votes)
            embed = nextcord.Embed(title="You picked", color=B_THEME)
            await b_message.edit(embed=embed, view=ChosenSideView(side_pick))
            
            a_side = None
            if side_pick == Side.T: a_side = Side.CT
            elif side_pick == Side.CT: a_side = Side.T
            embed = nextcord.Embed(title="You are", color=B_THEME)
            await a_channel.send(embed=embed, view=ChosenSideView(a_side))
            await self.bot.store.update(MMBotMatches, id=self.match_id, b_side=side_pick)
            await self.increment_state()

        if check_state(MatchState.MATCH_STARTING):
            await self.match_channel.purge(bulk=True)
            match_map = await self.bot.store.get_match_map(self.guild_id, self.match_id)
            match_sides = await self.bot.store.get_match_sides(self.match_id)
            embed = nextcord.Embed(title="Starting", description="Setting up server", color=VALORS_THEME1)
            embed.set_image(match_map.media)
            embed.add_field(name=f"Team A - {match_sides[0].name}", 
                value='\n'.join([f"- <@{player.user_id}>" for player in self.players if player.team == Team.A]))
            embed.add_field(name=f"Team B - {match_sides[1].name}", 
                value='\n'.join([f"- <@{player.user_id}>" for player in self.players if player.team == Team.B]))
            embed.add_field(name=f"{match_map.map}:", value="\u200B", inline=False)
            match_message = await self.match_channel.send(embed=embed)

            embed = nextcord.Embed(
                title="Match starting!",
                description=f"Return to {self.match_channel.mention}",
                color=VALORS_THEME1)
            await a_channel.send(embed=embed)
            await b_channel.send(embed=embed)
            await self.bot.store.update(MMBotMatches, id=self.match_id, match_message=match_message.id)
            await self.increment_state()
        
        if check_state(MatchState.LOG_PICKS):
            embed = log_message.embeds[0]
            embed.description = "Server setup"
            embed.set_field_at(0, name=f"[{self.match.a_mmr:.0f}]Team A - {'T' if self.match.b_side == Side.CT else 'CT'}", 
                value='\n'.join([f"- <@{player.user_id}>" for player in self.players if player.team == Team.A]))
            embed.set_field_at(1, name=f"[{self.match.b_mmr:.0f}]Team B - {'CT' if self.match.b_side == Side.CT else 'T'}", 
                value='\n'.join([f"- <@{player.user_id}>" for player in self.players if player.team == Team.B]))
            embed.set_image(match_map.media)
            embed.add_field(name=f"{match_map.map}:", value="\u200B", inline=False)
            log_message = await log_message.edit(embed=embed)
            await self.increment_state()
        
        if check_state(MatchState.MATCH_FIND_SERVER):
            users = await self.bot.store.get_users(self.guild_id, [player.user_id for player in self.players])
            success = None
            rcon_servers: List[RconServers] = await self.bot.store.get_servers(free=True)
            log.debug(f"RCON_SERVERS: {rcon_servers}")

            if rcon_servers:
                estimated_pings = await self.estimate_pings(rcon_servers)
                server_scores = []
                for server in rcon_servers:
                    serveraddr = f"{server.host}:{server.port}"
                    server_pings = estimated_pings[serveraddr]
                    max_ping = max(server_pings.values())
                    avg_ping = sum(server_pings.values()) / len(server_pings)
                    
                    score = max_ping * 0.75 + avg_ping * 0.25
                    server_scores.append((server, score))
                
                sorted_servers = sorted(server_scores, key=lambda x: x[1])

                for server, _ in sorted_servers:
                    successful = await self.bot.rcon_manager.add_server(server.host, server.port, server.password)
                    if successful:
                        log.info(f"[{self.match_id}] Server found running rcon server {server.host}:{server.port} password: {server.password} region: {server.region}")
                        serveraddr = f'{server.host}:{server.port}'
                        success = True
                        await self.bot.store.set_serveraddr(self.match_id, serveraddr)
                        await self.bot.store.use_server(serveraddr)
                        await self.increment_state()
                        break
            if not success:
                await self.show_no_server_found_message()

        if check_state(MatchState.SET_SERVER_MODS):
            mods = await self.bot.store.get_mods(guild.id)
            await self.bot.rcon_manager.clear_mods(serveraddr)
            for mod in mods:
                await self.bot.rcon_manager.add_mod(serveraddr, mod.resource_id)
            await self.increment_state()
        
        if check_state(MatchState.MATCH_CHANGE_TO_LOBBY):
            self.match = await self.bot.store.get_match(self.match_id)
            pin = 5
            server_name = f"PMM Match {self.match_id}"
            await asyncio.gather(
                self.bot.rcon_manager.set_teamdeathmatch(serveraddr, SERVER_DM_MAP),
                self.bot.rcon_manager.unban_all_players(serveraddr),
                self.bot.rcon_manager.comp_mode(serveraddr, state=True),
                self.bot.rcon_manager.max_players(serveraddr, MATCH_PLAYER_COUNT),
                self.bot.rcon_manager.set_pin(serveraddr, pin),
                self.bot.rcon_manager.set_name(serveraddr, server_name)
            )

            embed = nextcord.Embed(title=f"Match [0/{MATCH_PLAYER_COUNT}]", description=f"Server ready!", color=VALORS_THEME1)
            embed.set_image(match_map.media)
            embed.add_field(name=f"Team A - {match_sides[0].name}", 
                value='\n'.join([f"- <@{player.user_id}>" for player in self.players if player.team == Team.A]))
            embed.add_field(name=f"Team B - {match_sides[1].name}", 
                value='\n'.join([f"- <@{player.user_id}>" for player in self.players if player.team == Team.B]))
            embed.add_field(name="TDM Server", value=f"`{server_name}`", inline=False)
            embed.add_field(name="Pin", value=f"`{pin}`")
            embed.add_field(name=f"{match_map.map}:", value="\u200B", inline=False)
            match_message = await match_message.edit(embed=embed)
            await self.increment_state()
        
        if check_state(MatchState.MATCH_WAIT_FOR_PLAYERS):
            embed = match_message.embeds[0]
            current_players = set()
            server_players = set()
            done_event = asyncio.Event()
            warnings_issued = {}
            abandon_view = ForceAbandonView(self.bot, self.match)

            async def run_matchmaking_timer():
                current_message: nextcord.Message | None = None
                start_time = time()
                end_time = start_time + float(cast(int, settings.mm_join_period)) + 1.0
                message_update_interval = 10
                message_post_interval = 60
                force_abandon_view_delay = 300
                player_mention_delays = sorted([cast(int, settings.mm_join_period) - 120, cast(int, settings.mm_join_period) - 60, cast(int, settings.mm_join_period)])

                def get_missing_players():
                    return [p for p in self.players if not any(m.platform_id in server_players for m in p.user_platform_mappings)]

                while not done_event.is_set():
                    missing_players = get_missing_players()
                    abandon_view.missing_players = missing_players

                    current_time = time()
                    elapsed_time = current_time - start_time
                    remaining_time = end_time - current_time
                    overtime = current_time - end_time + 1

                    if current_time < end_time:
                        description = f"## {format_duration(remaining_time)}\nFailure to abide will result in moderative actions."
                        color = 0xff0000
                    else:
                        description = f"You are {format_duration(overtime)} late and have gained a warning."
                        color = 0xff6600

                        for player in missing_players:
                            if player.user_id not in warnings_issued:
                                warnings_issued[player.user_id] = { 'warn_id': None }
                                log.info(f"{player.user_id} was issued a warning for being {format_duration(overtime)} late to a match.")
                            warnings_issued[player.user_id]['overtime'] = overtime
                            warnings_issued[player.user_id]['warn_id'] = await self.bot.store.upsert_warning(
                                guild_id=self.guild_id,
                                user_id=player.user_id,
                                message=f"Late by {format_duration(overtime)}",
                                match_id=self.match_id,
                                warn_type=Warn.LATE,
                                identifier=warnings_issued[player.user_id]['warn_id'])
                    
                    mentions = None
                    if missing_players:
                        mentions = "\n".join(f"‼️ <@{player.user_id}>" for player in missing_players)
                    
                    embed = nextcord.Embed(title="Join the server", description=description, color=color)
                    
                    view = abandon_view if overtime > force_abandon_view_delay else None
                    if elapsed_time % message_post_interval < message_update_interval:
                        if current_message:
                            try:
                                await current_message.delete()
                            except nextcord.NotFound:
                                pass
                        
                        mention = False
                        if player_mention_delays and elapsed_time > player_mention_delays[0]:
                            player_mention_delays.pop(0)
                            mention = True
                        
                        current_message = await self.match_channel.send(view=view, embed=embed, content=mentions if mention else None)
                    elif current_message:
                        try:
                            await current_message.edit(view=view, embed=embed, content=mentions)
                        except Exception:
                            pass
                    
                    await asyncio.sleep(max(message_update_interval - (time() - current_time), 0))
                
                try: await current_message.delete()
                except nextcord.NotFound: pass
            
            timer_task = asyncio.create_task(run_matchmaking_timer())
            self.subtasks.add(timer_task)

            try:
                while len(server_players) < MATCH_PLAYER_COUNT:
                    await asyncio.sleep(3)
                    try:
                        players_data = await self.bot.rcon_manager.inspect_all(serveraddr, retry_attempts=1)
                        if 'InspectList' not in players_data:
                            continue
                        
                        current_players = {str(player['UniqueId']) for player in players_data['InspectList']}
                        
                        new_players = current_players - server_players
                        if new_players:
                            if len(current_players) < MATCH_PLAYER_COUNT:
                                embed.title = f"Match [{len(current_players)}/{MATCH_PLAYER_COUNT}]"
                            else:
                                embed.title = "Match"
                                embed.description = "Match started"
                            await match_message.edit(embed=embed)
                            log.info(f"[{self.match_id}] New players joined: {new_players}")

                            tasks = []
                            for platform_id in new_players:
                                player = next((p for p in self.players if platform_id in [m.platform_id for m in p.user_platform_mappings]), None)
                                if player:
                                    teamid = self.match.b_side.value if player.team == Team.B else 1 - self.match.b_side.value
                                    log.info(f"[{self.match_id}] Moving player {platform_id} to team {teamid}")
                                    tasks.append(self.bot.rcon_manager.allocate_team(serveraddr, platform_id, teamid))
                                else:
                                    log.info(f"[{self.match_id}] Unauthorized player {platform_id} found. Kicking.")
                                    tasks.append(self.bot.rcon_manager.kick_player(serveraddr, platform_id))
                            
                            if tasks:
                                await asyncio.gather(*tasks)

                        server_players = current_players
                    except Exception as e:
                        tb = traceback.extract_tb(e.__traceback__)
                        _, line_number, func_name, _ = tb[-1]
                        log.warning(f"[{self.match_id}] [{func_name}:{line_number}] Error during wait_for_players: {repr(e)}")
                        print("[players_data] ", players_data)
            finally:
                done_event.set()
                self.subtasks.discard(timer_task)
                
            
            async def notify_user(embed: nextcord.Embed):
                try:
                    await self.bot.get_user(uid).send(embed=embed)
                except (nextcord.Forbidden, nextcord.HTTPException):
                    pass

            for uid, data in warnings_issued.items():
                embed = nextcord.Embed(
                    title="You were issued a warning", 
                    description=f"You gained a warning for being late by {format_duration(data['overtime'])} to Match #{self.match_id}.", 
                    color=0xff6600)
                try:
                    asyncio.create_task(notify_user(embed))
                except Exception:
                    pass
            
            await abandon_view.wait_abandon()
            await self.increment_state()
        
        if check_state(MatchState.MATCH_START_SND):
            m = next((m for m in maps if m.map == self.match.map), maps[0])
            server_maps = await self.bot.rcon_manager.list_maps(serveraddr)
            await self.bot.rcon_manager.add_map(serveraddr, m.resource_id if m.resource_id else m.map, 'SND')
            for ma in server_maps.get('MapList', []):
                await self.bot.rcon_manager.remove_map(serveraddr, ma['MapId'], ma['GameMode'], retry_attempts=3)
            await self.bot.rcon_manager.set_searchndestroy(serveraddr, m.resource_id if m.resource_id else m.map)
            log.info(f"[{self.match_id}] Switching to SND")

            embed = nextcord.Embed(title="Match started!", description="May the best team win!", color=VALORS_THEME1)
            
            for player in self.players:
                member = guild.get_member(cast(int, player.user_id))
                if member and member.voice and member.voice.channel.id == settings.mm_voice_channel:
                    await asyncio.sleep(0.1)
                    try:
                        if player.team == Team.A:
                            await member.move_to(a_vc)
                        if player.team == Team.B:
                            await member.move_to(b_vc)
                    except nextcord.HTTPException: pass
            
            await self.match_channel.send(embed=embed)
            await self.increment_state()
        
        if check_state(MatchState.LOG_MATCH_HAPPENING):
            embed = log_message.embeds[0]
            embed.description = "Match just started"
            log_message = await log_message.edit(embed=embed)
            await self.increment_state()

        if check_state(MatchState.MATCH_WAIT_FOR_END):
            a_score = 0 if self.match.a_score is None else cast(int, self.match.a_score)
            b_score = 0 if self.match.b_score is None else cast(int, self.match.b_score)
            if self.match.b_side == Side.CT:    team_scores = [b_score, a_score]
            else:                               team_scores = [a_score, b_score]
            
            last_users_match_stats = {}
            disconnection_tracker = { player.user_id: 0 for player in self.players }
            last_round_number = self.match.a_score + self.match.b_score if self.match.a_score else 0
            changed_users = {}
            players_dict = {}
            
            users_summary_data = await self.bot.store.get_users_summary_stats(self.guild_id, [p.user_id for p in self.players])
            match_stats = await self.bot.store.get_match_stats(self.match_id)
            self.initialize_user_match_stats(match_stats, users_summary_data)

            a_side = 'T' if self.match.b_side == Side.CT else 'CT'
            b_side = 'CT' if self.match.b_side == Side.CT else 'T'
            a_player_list = '\n'.join([f"- <@{player.user_id}>" for player in self.players if player.team == Team.A])
            b_player_list = '\n'.join([f"- <@{player.user_id}>" for player in self.players if player.team == Team.B])

            max_score = max(a_score, b_score)
            if max_score < 10:
                await self.wait_for_snd_mode()

            ready_to_continue = False
            reply = None
            while not ready_to_continue:
                if max_score >= 10:
                    ready_to_continue = True
                await asyncio.sleep(3)
                try:
                    if max(a_score, b_score) < 10:
                        reply = (await self.bot.rcon_manager.server_info(serveraddr))['ServerInfo']
                        if "Team0Score" not in reply: continue
                        team_scores = [int(reply['Team0Score']), int(reply['Team1Score'])]
                        self.current_round = int(reply.get('Round', self.current_round))
                    else: continue

                    max_score = max(team_scores)

                    is_new_round = self.current_round > last_round_number
                    if is_new_round:
                        last_round_number = self.current_round
                        embed = log_message.embeds[0]
                        embed.description = f"\\- ***Match ongoing***\n{generate_score_text(guild, self.persistent_player_stats)}"
                        a_score, b_score = (team_scores[1], team_scores[0]) if self.match.b_side == Side.CT else (team_scores[0], team_scores[1])
                        asyncio.create_task(self.bot.store.update(MMBotMatches, id=self.match_id, a_score=a_score, b_score=b_score))
                        if max_score >= 10:
                            embed.description = f"{'A' if a_score > b_score else 'B'} Wins!"
                        embed.set_field_at(0, name=f"[{self.match.a_mmr:.0f}]Team A - {a_side}: {a_score}", value=a_player_list)
                        embed.set_field_at(1, name=f"[{self.match.b_mmr:.0f}]Team B - {b_side}: {b_score}", value=b_player_list)
                        asyncio.create_task(log_message.edit(embed=embed))
                        log.info(f"[{self.match_id}] Round {self.current_round} completed. Scores: {team_scores[0]} - {team_scores[1]}")

                    players_data = await self.bot.rcon_manager.inspect_all(serveraddr, retry_attempts=1)
                    if not 'InspectList' in players_data: continue
                    players_dict = { player['UniqueId']: player for player in players_data['InspectList'] }

                    await self.process_players(
                        players_dict, 
                        disconnection_tracker, 
                        is_new_round)
                    
                    await self.upsert_user_stats(
                        changed_users,
                        last_users_match_stats,
                        players_dict)
                except Exception as e:
                    tb = traceback.extract_tb(e.__traceback__)
                    _, line_number, func_name, _ = tb[-1]
                    log.warning(f"[{self.match_id}] [{func_name}:{line_number}] Error during match: {repr(e)}")
                    print("[Reply] ", reply)
            
            await self.finalize_match(users_summary_data, team_scores)
            
            embed = log_message.embeds[0]
            embed.description = f"{'A' if a_score > b_score else 'B'} Wins!"
            a_player_list = '\n'.join([f"- <@{player.user_id}> Δ{self.persistent_player_stats[player.user_id]['mmr_change']:+02.2f}" 
                                    for player in self.players if player.team == Team.A])
            b_player_list = '\n'.join([f"- <@{player.user_id}> Δ{self.persistent_player_stats[player.user_id]['mmr_change']:+02.2f}" 
                                    for player in self.players if player.team == Team.B])
            embed.set_field_at(0, name=f"[{self.match.a_mmr:.0f}]Team A - {a_side}: {a_score}", value=a_player_list)
            embed.set_field_at(1, name=f"[{self.match.b_mmr:.0f}]Team B - {b_side}: {b_score}", value=b_player_list)
            asyncio.create_task(log_message.edit(embed=embed))

            await self.increment_state()
        
        if check_state(MatchState.MATCH_CLEANUP):
            pin = 5
            server_name = f"PMM {server.region} Server {server.id}"
            await self.bot.rcon_manager.set_name(serveraddr, server_name)
            await self.bot.rcon_manager.set_pin(serveraddr, pin)
            await self.bot.rcon_manager.add_map(serveraddr, SERVER_DM_MAP, 'TDM')
            m = next((m for m in maps if m.map == self.match.map), maps[0])
            await self.bot.rcon_manager.remove_map(serveraddr, m.resource_id if m.resource_id else m.map, 'SND')
            await self.bot.rcon_manager.set_teamdeathmatch(serveraddr, SERVER_DM_MAP)
            await self.bot.rcon_manager.comp_mode(serveraddr, state=False)
            await self.bot.rcon_manager.clear_mods(serveraddr)
            await self.bot.rcon_manager.max_players(serveraddr, 10)
            await self.increment_state()
        
        if check_state(MatchState.LOG_END):
            self.match = await self.bot.store.get_match(self.match_id)
            match_stats = await self.bot.store.get_match_stats(self.match_id)
            try:
                leaderboard_image = await generate_score_image(self.bot.cache, guild, self.match, match_stats)
                file = nextcord.File(BytesIO(leaderboard_image), filename=f"Match_{self.match_id}_leaderboard.png")
                await log_message.edit(file=file)
            except Exception as e:
                log.error(f"[{self.match_id}] Error in creating score leaderboard image: {repr(e)}")
            await self.increment_state()
        
        if check_state(MatchState.CLEANUP):
            if serveraddr:
                await self.bot.store.free_server(serveraddr)
                await self.bot.rcon_manager.unban_all_players(serveraddr, retry_attempts=1)
                await self.bot.rcon_manager.comp_mode(serveraddr, state=False, retry_attempts=1)
            embed = nextcord.Embed(title="The match is terminating", color=VALORS_THEME1)
            embed.set_footer(text="You will be able to requeue once this channel is deleted")
            
            try:
                await self.match_channel.send(embed=embed)
            except AttributeError:
                pass
            
            asyncio.create_task(update_leaderboard(self.bot.store, guild))
            await self.bot.store.update(MMBotMatches, id=self.match_id, end_timestamp=datetime.now(timezone.utc))
            # a_channel
            try:
                if a_channel: await a_channel.delete()
            except nextcord.HTTPException: pass
            # b_channel
            try:
                if b_channel: await b_channel.delete()
            except nextcord.HTTPException: pass
            # move users back
            voice_channel = guild.get_channel(settings.mm_voice_channel)
            for player in self.players:
                member = guild.get_member(cast(int, player.user_id))
                if member and member.voice and member.voice.channel in [a_vc, b_vc]:
                    await asyncio.sleep(0.1)
                    try: await member.move_to(voice_channel)
                    except nextcord.HTTPException: pass
            # a_vc
            try:
                if a_vc: await a_vc.delete()
            except nextcord.HTTPException: pass
            # b_vc
            try:
                if b_vc: await b_vc.delete()
            except nextcord.HTTPException: pass

            # match_channel
            try:
                if self.match_channel: await self.match_channel.delete()
            except nextcord.HTTPException: pass

            # complete True
            await self.bot.store.update(MMBotMatches, id=self.match_id, complete=True)
            await self.increment_state()

            if self.requeue_players:
                await self.start_requeue_players(settings)
