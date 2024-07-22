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
import copy
import traceback
from collections import Counter
from datetime import datetime, timezone
from functools import wraps
from typing import List
from io import BytesIO
from pprint import pprint

import nextcord
from nextcord.ext import commands

from config import (
   B_THEME,
   A_THEME,
   MATCH_PLAYER_COUNT,
   SERVER_DM_MAP,
   STARTING_MMR,
   VALORS_THEME1,
   VALORS_THEME1_2,
   VALORS_THEME2,
)
from utils.logger import Logger as log, VariableLog
from utils.models import *
from utils.utils import format_duration, format_mm_attendance, generate_score_image, get_rank_role
from utils.statistics import create_leaderboard_embed
from views.match.accept import AcceptView
from views.match.banning import BanView, ChosenBansView
from views.match.map_pick import ChosenMapView, MapPickView
from views.match.side_pick import ChosenSideView, SidePickView
from .functions import calculate_mmr_change, get_preferred_bans, get_preferred_map, get_preferred_side
from .match_states import MatchState
from .ranked_teams import get_teams


class Match:
    def __init__(self, bot: commands.Bot, guild_id: int, match_id: int, state=MatchState.NOT_STARTED):
        self.bot       = bot
        self.guild_id  = guild_id
        self.match_id  = match_id
        self.state     = state

        self.players       = []
        self.current_round = None

    async def wait_for_snd_mode(self):
        while True:
            await asyncio.sleep(3)
            try:
                reply = (await self.bot.rcon_manager.server_info(self.match.serveraddr))['ServerInfo']
                log.debug(f"WAITING FOR SND {reply}")
                if reply['GameMode'] == 'SND' and reply['PlayerCount'][0] != '0':
                    break
            except Exception as e:
                log.error(f"Error while waiting for SND mode: {str(e)}")

    async def process_players(self, players_dict, users_match_stats, users_summary_data, disconnection_tracker, is_new_round):
        found_player_ids = {p.user_id: False for p in self.players}
        for platform_id, player_data in players_dict.items():
            player = next((p for p in self.players if any(platform_id == pm.platform_id for pm in p.user_platform_mappings)), None)
            if player:
                user_id = player.user_id
                found_player_ids[user_id] = True
                
                await self.ensure_correct_team(player, platform_id, player_data)
                
                if user_id not in users_match_stats:
                    users_match_stats[user_id] = self.initialize_user_match_stats(user_id, player, users_summary_data)
                
                self.update_user_match_stats(users_match_stats[user_id], player_data)
                
                if is_new_round:
                    users_match_stats[user_id]['rounds_played'] += 1
                    disconnection_tracker[user_id] = 0
            else:
                log.info(f"[{self.match_id}] Unauthorized player {platform_id} detected. Kicking.")
                await self.bot.rcon_manager.kick_player(self.match.serveraddr, platform_id)
        
        return found_player_ids

    async def ensure_correct_team(self, player, platform_id, player_data):
        teamid = self.match.b_side.value if player.team == Team.B else 1 - self.match.b_side.value
        if int(player_data['TeamId']) != int(teamid):
            log.info(f"[{self.match_id}] Moving player {platform_id} to team {teamid}")
            await self.bot.rcon_manager.allocate_team(self.match.serveraddr, platform_id, teamid)

    def initialize_user_match_stats(self, user_id, player, users_summary_data):
        return {
            "mmr_before": users_summary_data.get(user_id, MMBotUserSummaryStats(mmr=STARTING_MMR)).mmr,
            "games": users_summary_data.get(user_id, MMBotUserSummaryStats(games=0)).games + 1,
            "ct_start": (player.team == Team.A) == (self.match.b_side == Side.T),
            "score": 0,
            "kills": 0,
            "deaths": 0,
            "assists": 0,
            "rounds_played": 0
        }

    def update_user_match_stats(self, user_stats, player_data):
        kills, deaths, assists = map(int, player_data['KDA'].split('/'))
        user_stats.update({
            "score": int(player_data['Score']),
            "kills": kills,
            "deaths": deaths,
            "assists": assists
        })

    def check_disconnections(self, found_player_ids, disconnection_tracker, abandoned_users):
        for pid, found in found_player_ids.items():
            if not found:
                disconnection_tracker[pid] += 1
                VariableLog.debug(disconnection_tracker[pid], message=f"[{self.match_id}] Disconnect {pid}")
                if disconnection_tracker[pid] >= 5:
                    abandoned_users.append(pid)

    async def handle_abandons(self, players_dict, abandoned_users, users_match_stats, users_summary_data):
        await self.bot.store.add_match_abandons(self.guild_id, self.match_id, abandoned_users)
        abandonee_match_update = {}
        abandonee_summary_update = {}

        user_to_platform = {
            player.user_id: next(
                (mapping.platform_id for mapping in player.user_platform_mappings 
                if mapping.platform_id in players_dict), None)
            for player in self.players
        }
        
        for abandonee_id in abandoned_users:
            player = next((p for p in self.players if p.user_id == abandonee_id), None)
            if player:
                await self.match_thread.send(f"<@{player.user_id}> has abandoned the match for being disconnected 5 rounds in a row.")
                ally_mmr = self.match.a_mmr if player.team == Team.A else self.match.b_mmr
                enemy_mmr = self.match.b_mmr if player.team == Team.A else self.match.a_mmr
                stats = users_match_stats.get(abandonee_id, self.initialize_user_match_stats(abandonee_id, player, users_summary_data))
                
                player_data = players_dict.get(user_to_platform.get(abandonee_id, None), None)
                ping = int(float(player_data['Ping'])) if player_data else -1
                mmr_change = calculate_mmr_change({}, abandoned=True, ally_team_avg_mmr=ally_mmr, enemy_team_avg_mmr=enemy_mmr)
                stats.update({"mmr_change": mmr_change, "ping": ping})
                
                abandonee_match_update[abandonee_id] = stats
                abandonee_summary_update[abandonee_id] = {"mmr": users_summary_data[abandonee_id].mmr + stats['mmr_change']}

        await self.bot.store.upsert_users_match_stats(self.guild_id, self.match_id, abandonee_match_update)
        await self.bot.store.set_users_summary_stats(self.guild_id, abandonee_summary_update)

    def update_summary_stats(self, summary_data, match_stats):
        return {
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
    
    async def finalize_match(self, players_dict, users_match_stats, users_summary_data, team_scores, last_reply: dict | None):
        if last_reply is None:
            last_reply = (await self.bot.rcon_manager.server_info(self.match.serveraddr))['ServerInfo']
        
        final_updates = {}
        users_summary_stats = {}

        user_to_platform = {
            player.user_id: next(
                (mapping.platform_id for mapping in player.user_platform_mappings 
                if mapping.platform_id in players_dict), None)
            for player in self.players
        }

        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            log.error(f"Could not find guild with id {self.guild_id}")
            return
        
        ranks = await self.bot.store.get_ranks(self.guild_id)
        rank_ids = { r.role_id for r in ranks }

        for player in self.players:
            user_id = player.user_id
            if user_id in users_match_stats:
                current_stats = users_match_stats[user_id]
                ct_start = current_stats['ct_start']
                win = team_scores[0] > team_scores[1] if ct_start else team_scores[1] > team_scores[0]

                ally_score = team_scores[0] if ct_start else team_scores[1]
                enemy_score = team_scores[1] if ct_start else team_scores[0]
                ally_mmr = self.match.a_mmr if player.team == Team.A else self.match.b_mmr
                enemy_mmr = self.match.b_mmr if player.team == Team.A else self.match.a_mmr
                mmr_change = calculate_mmr_change(current_stats, 
                    ally_team_score=ally_score, enemy_team_score=enemy_score, 
                    ally_team_avg_mmr=ally_mmr, enemy_team_avg_mmr=enemy_mmr, win=win)
                
                player_data = players_dict.get(user_to_platform[user_id], None)
                ping = int(float(player_data['Ping'])) if player_data else -1
                current_stats.update({"win": win, "mmr_change": mmr_change, "ping": ping})

                summary_data = users_summary_data[user_id]
                new_mmr = summary_data.mmr + current_stats['mmr_change']

                new_rank_id = next((r.role_id for r in sorted(ranks, key=lambda x: x.mmr_threshold, reverse=True) if new_mmr >= r.mmr_threshold), None)

                member = guild.get_member(user_id)
                if member:
                    current_rank_role_ids = set(role.id for role in member.roles if role.id in rank_ids)
                
                    if new_rank_id not in current_rank_role_ids:
                        
                        roles_to_remove = [guild.get_role(role_id) for role_id in current_rank_role_ids]
                        roles_to_remove = [role for role in roles_to_remove if role is not None]
                        if roles_to_remove:
                            asyncio.create_task(member.remove_roles(*roles_to_remove, reason="Updating MMR rank"))
                            log.info(f"Roles {', '.join(role.name for role in roles_to_remove)} removed from {member.display_name}")
                        
                        new_role = guild.get_role(new_rank_id)
                        if new_role:
                            asyncio.create_task(member.add_roles(new_role, reason="Updating MMR rank"))
                            log.info(f"Role {new_role.name} added to {member.display_name}")

                users_summary_stats[user_id] = self.update_summary_stats(summary_data, current_stats)
                final_updates[user_id] = current_stats
        
        side_a_score = int(last_reply['Team0Score'])
        side_b_score = int(last_reply['Team1Score'])
        team_a_score, team_b_score = (side_b_score, side_a_score) if self.match.b_side == Side.CT else (side_a_score, side_b_score)
        self.match.a_score = team_a_score
        self.match.b_score = team_b_score
        await self.bot.store.update(MMBotMatches, id=self.match_id, a_score=team_a_score, b_score=team_b_score, end_timestamp=datetime.now(timezone.utc))

        await self.bot.store.upsert_users_match_stats(self.guild_id, self.match_id, final_updates)
        await self.bot.store.set_users_summary_stats(self.guild_id, users_summary_stats)

    async def increment_state(self):
        self.state = MatchState(self.state + 1)
        log.debug(f"Match state -> {self.state}")
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
                log.critical(f"Exception in match {self.match_id}: {traceback.format_exc()}")
                guild = self.bot.get_guild(self.guild_id)
                match = await self.bot.store.get_match(self.match_id)
                if match and match.match_thread:
                    match_thread = guild.get_thread(match.match_thread)
                    if match_thread:
                        await self.match_thread.send(f"```diff\n- An error occurred: {e}```\nThe match has been frozen.")
                event = asyncio.Event()
                await event.wait()
        return wrapper
    
    @safe_exception
    async def run(self):
        await self.bot.wait_until_ready()
        if self.state > 0: log.info(
            f"Loaded ongoing match {self.match_id} state:{self.state}")
        
        def check_state(state: MatchState):
            return True if self.state == state else False
        
        self.state = await self.load_state()
        settings: BotSettings             = await self.bot.store.get_settings(self.guild_id)
        self.match: MMBotMatches               = await self.bot.store.get_match(self.match_id)
        self.players: List[MMBotMatchPlayers]  = await self.bot.store.get_players(self.match_id)
        maps: List[MMBotMaps]             = await self.bot.store.get_maps(self.guild_id)
        match_map: MMBotMaps              = await self.bot.store.get_match_map(self.match_id)
        match_sides                       = await self.bot.store.get_match_sides(self.match_id)

        serveraddr                        = await self.bot.store.get_serveraddr(self.match_id)
        if serveraddr:
            host, port = serveraddr.split(':')
            server = await self.bot.store.get_server(host, int(port))
            await self.bot.rcon_manager.add_server(server.host, server.port, server.password)
        
        guild = self.bot.get_guild(self.guild_id)
        queue_channel = guild.get_channel(settings.mm_queue_channel)
        text_channel = guild.get_channel(settings.mm_text_channel)

        self.match_thread  = guild.get_thread(self.match.match_thread)
        log_channel   = guild.get_channel(settings.mm_log_channel)
        a_thread      = guild.get_thread(self.match.a_thread)
        b_thread      = guild.get_thread(self.match.b_thread)

        a_vc          = guild.get_channel(self.match.a_vc)
        b_vc          = guild.get_channel(self.match.b_vc)

        try:
            if self.match.log_message:
                log_message    = await log_channel.fetch_message(self.match.log_message)
        except Exception: pass
        try:
            if self.match.match_message: 
                match_message  = await self.match_thread.fetch_message(self.match.match_message)
        except Exception: pass
        try:
            if self.match.a_message: 
                a_message      = await self.match_thread.fetch_message(self.match.a_message)
        except Exception: pass
        try:
            if self.match.b_message: 
                b_message      = await self.match_thread.fetch_message(self.match.b_message)
        except Exception: pass

        if check_state(MatchState.NOT_STARTED):
            await self.increment_state()
        
        if check_state(MatchState.CREATE_MATCH_THREAD):
            self.match_thread = await queue_channel.create_thread(
                name=f"Match - #{self.match_id}",
                auto_archive_duration=1440,
                invitable=False,
                reason=f"Match - #{self.match_id}")
            await self.bot.store.update(MMBotMatches, id=self.match_id, match_thread=self.match_thread.id)
            await self.increment_state()
        
        if check_state(MatchState.ACCEPT_PLAYERS):
            add_mention = []
            for player in self.players:
                add_mention.append(f"<@{player.user_id}>")
            embed = nextcord.Embed(title=f"Match - #{self.match_id}", color=VALORS_THEME2)
            embed.add_field(name=f"Attendance - {format_duration(settings.mm_accept_period)} to accept", value=format_mm_attendance(self.players))
            done_event = asyncio.Event()
            view = AcceptView(self.bot, done_event)
            await self.match_thread.send(''.join(add_mention), embed=embed, view=view)

            async def notify_unaccepted_players(delay: int=30):
                await asyncio.sleep(delay)
                if not done_event.is_set():
                    unaccepted_players = await self.bot.store.get_unaccepted_players(self.match_id)
                    for player in unaccepted_players:
                        member = guild.get_member(player.user_id)
                        if member:
                            embed = nextcord.Embed(
                                title="Queue Popped!", 
                                description=f"{format_duration(settings.mm_accept_period - delay)} left to ACCEPT\n{self.match_thread.mention}!", 
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
                await self.match_thread.send(embed=embed)
                player_ids = [p.user_id for p in self.players]
                dodged_mentions = ' '.join((f'<@{userid}>' for userid in player_ids if userid not in view.accepted_players))
                await text_channel.send(f"{dodged_mentions}\nDid not accept the last match in time.\nPlayers can queue up again in 10 seconds.")
            finally: [task.cancel() for task in notify_tasks]
            await self.increment_state()

        if check_state(MatchState.MAKE_TEAMS):
            users = await self.bot.store.get_users(self.guild_id, [player.user_id for player in self.players])
            a_players, b_players, a_mmr, b_mmr = get_teams(users)
            await self.bot.store.set_players_team(
                match_id=self.match_id, 
                user_teams={Team.A: a_players, Team.B: b_players})
            self.players = await self.bot.store.get_players(self.match_id)
            await self.bot.store.update(MMBotMatches, id=self.match_id, a_mmr=a_mmr, b_mmr=b_mmr)
            await self.increment_state()
        
        if check_state(MatchState.LOG_MATCH):
            embed = nextcord.Embed(
                title=f"[{self.match_id}] VALORS MM Match",
                description="Teams created\nInitiating team votes",
                color=VALORS_THEME1)
            embed.add_field(name="Team A", 
                value='\n'.join([f"- <@{player.user_id}>" for player in self.players if player.team == Team.A]))
            embed.add_field(name="Team B", 
                value='\n'.join([f"- <@{player.user_id}>" for player in self.players if player.team == Team.B]))
            embed.set_footer(text=f"Match started ")
            embed.timestamp = datetime.now(timezone.utc)
            log_message = await log_channel.send(embed=embed)
            await self.bot.store.update(MMBotMatches, id=self.match_id, log_message=log_message.id)
            await self.increment_state()
        
        if check_state(MatchState.MAKE_TEAM_VC_A):
            player_overwrites = { guild.get_member(player.user_id): nextcord.PermissionOverwrite(connect=True) for player in self.players if player.team == Team.A }
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
            player_overwrites = { guild.get_member(player.user_id): nextcord.PermissionOverwrite(connect=True) for player in self.players if player.team == Team.B }
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
            await self.match_thread.purge(bulk=True)
            embed = nextcord.Embed(title="Team A ban first", description=f"<#{a_thread.id}>", color=A_THEME)
            embed.add_field(name="Team A", 
                value='\n'.join([f"- <@{player.user_id}>" for player in self.players if player.team == Team.A]))
            embed.add_field(name="Team B", 
                value='\n'.join([f"- <@{player.user_id}>" for player in self.players if player.team == Team.B]))
            match_message = await self.match_thread.send(embed=embed)
            await self.bot.store.update(MMBotMatches, id=self.match_id, match_message=match_message.id)
            await self.increment_state()
        
        if check_state(MatchState.A_BANS):
            time_to_ban = 20
            self.players = await self.bot.store.get_players(self.match_id)
            add_mention = []
            for player in self.players:
                if player.team != Team.A: continue
                add_mention.append(f"<@{player.user_id}>")
                await self.match_thread.add_user(nextcord.Object(id=player.user_id))
            embed = nextcord.Embed(title="Pick your 2 bans", description=format_duration(time_to_ban), color=A_THEME)
            view = await BanView.create_showable(self.bot, self.guild_id, self.match)
            a_message = await a_thread.send(''.join(add_mention), embed=embed, view=view)
            await self.bot.store.update(MMBotMatches, id=self.match_id,  a_message=a_message.id, phase=Phase.A_BAN)
            await asyncio.sleep(time_to_ban)
            await self.bot.store.update(MMBotMatches, id=self.match_id, phase=Phase.NONE)

            bans = await self.bot.store.get_ban_votes(self.match_id, Phase.A_BAN)
            bans = get_preferred_bans(maps, bans, total_bans=2)
            view = ChosenBansView(bans)
            embed = nextcord.Embed(title="You banned", color=A_THEME)
            await a_message.edit(embed=embed, view=view)
            embed = nextcord.Embed(title="A banned", color=A_THEME)
            await b_thread.send(embed=embed, view=view)
            await self.bot.store.update(MMBotMatches, id=self.match_id, a_bans=bans)
            await self.increment_state()
        
        if check_state(MatchState.BAN_SWAP):
            embed = nextcord.Embed(title="Team B ban second", description=f"<#{b_thread.id}>", color=B_THEME)
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
            view = await BanView.create_showable(self.bot, self.guild_id, self.match)
            add_mention = []
            for player in self.players:
                if player.team != Team.B: continue
                add_mention.append(f"<@{player.user_id}>")
                await self.match_thread.add_user(nextcord.Object(id=player.user_id))
            b_message = await b_thread.send(''.join(add_mention), embed=embed, view=view)
            await self.bot.store.update(MMBotMatches, id=self.match_id, phase=Phase.B_BAN, b_message=b_message.id)
            await asyncio.sleep(time_to_ban)
            await self.bot.store.update(MMBotMatches, id=self.match_id, phase=Phase.NONE)
            
            bans = await self.bot.store.get_ban_votes(self.match_id, Phase.B_BAN)
            bans = get_preferred_bans(maps, bans, total_bans=2)
            view = ChosenBansView(bans)
            embed = nextcord.Embed(title="You banned", color=B_THEME)
            await b_message.edit(embed=embed, view=view)
            embed = nextcord.Embed(title="B banned", color=B_THEME)
            await a_thread.send(embed=embed, view=view)
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
            embed = nextcord.Embed(title="Team A pick map", description=f"<#{a_thread.id}>", color=A_THEME)
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
            view = await MapPickView.create_showable(self.bot, self.guild_id, self.match)
            a_message = await a_thread.send(''.join(add_mention), embed=embed, view=view)
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
            await b_thread.send(embed=embed, view=view)
            await self.bot.store.update(MMBotMatches, id=self.match_id, map=map_pick.map)
            await self.increment_state()
        
        if check_state(MatchState.PICK_SWAP):
            embed = nextcord.Embed(title="Team B pick side", description=f"<#{b_thread.id}>", color=B_THEME)
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
            b_message = await b_thread.send(''.join(add_mention), embed=embed, view=view)
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
            await a_thread.send(embed=embed, view=ChosenSideView(a_side))
            await self.bot.store.update(MMBotMatches, id=self.match_id, b_side=side_pick)
            await self.increment_state()

        if check_state(MatchState.MATCH_STARTING):
            await self.match_thread.purge(bulk=True)
            match_map = await self.bot.store.get_match_map(self.match_id)
            match_sides = await self.bot.store.get_match_sides(self.match_id)
            embed = nextcord.Embed(title="Starting", description="Setting up server", color=VALORS_THEME1)
            embed.set_image(match_map.media)
            embed.add_field(name=f"Team A - {match_sides[0].name}", 
                value='\n'.join([f"- <@{player.user_id}>" for player in self.players if player.team == Team.A]))
            embed.add_field(name=f"Team B - {match_sides[1].name}", 
                value='\n'.join([f"- <@{player.user_id}>" for player in self.players if player.team == Team.B]))
            embed.add_field(name=f"{match_map.map}:", value="\u200B", inline=False)
            match_message = await self.match_thread.send(embed=embed)

            embed = nextcord.Embed(
                title="Match starting!",
                description=f"Return to {self.match_thread.mention}",
                color=VALORS_THEME1)
            await a_thread.send(embed=embed)
            await b_thread.send(embed=embed)
            await self.bot.store.update(MMBotMatches, id=self.match_id, match_message=match_message.id)
            await self.increment_state()
         
        if check_state(MatchState.LOG_PICKS):
            embed = log_message.embeds[0]
            embed.description = "Server setup"
            embed.set_field_at(0, name=f"Team A - {'T' if self.match.b_side == Side.CT else 'CT'}", 
                value='\n'.join([f"- <@{player.user_id}>" for player in self.players if player.team == Team.A]))
            embed.set_field_at(1, name=f"Team B - {'CT' if self.match.b_side == Side.CT else 'T'}", 
                value='\n'.join([f"- <@{player.user_id}>" for player in self.players if player.team == Team.B]))
            embed.set_image(match_map.media)
            embed.add_field(name=f"{match_map.map}:", value="\u200B", inline=False)
            log_message = await log_message.edit(embed=embed)
            await self.increment_state()
        
        if check_state(MatchState.MATCH_FIND_SERVER):
            users = await self.bot.store.get_users(self.guild_id, [player.user_id for player in self.players])
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
                        log.info(f"[{self.match_id}] Match found running rcon server {best_server.host}:{best_server.port} password: {best_server.password} region: {best_server.region}")
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
                    value='\n'.join([f"- <@{player.user_id}>" for player in self.players if player.team == Team.A]))
                embed.add_field(name=f"Team B - {match_sides[1].name}", 
                    value='\n'.join([f"- <@{player.user_id}>" for player in self.players if player.team == Team.B]))
                embed.add_field(name=f"{match_map.map}:", value="\u200B", inline=False)
                await match_message.edit(embed=embed)
                log.debug(f"[{self.match_id}] No running rcon servers found")
                self.state = MatchState.CLEANUP - 1
            await self.increment_state()

        if check_state(MatchState.SET_SERVER_MODS):
            mods = await self.bot.store.get_mods(guild.id)
            await self.bot.rcon_manager.clear_mods(serveraddr)
            for mod in mods:
                await self.bot.rcon_manager.add_mod(serveraddr, mod.resource_id)
            await self.increment_state()
        
        if check_state(MatchState.MATCH_WAIT_FOR_PLAYERS):
            self.match = await self.bot.store.get_match(self.match_id)
            await self.bot.rcon_manager.set_teamdeathmatch(serveraddr, SERVER_DM_MAP)
            await self.bot.rcon_manager.unban_all_players(serveraddr)
            await self.bot.rcon_manager.comp_mode(serveraddr, state=True)
            await self.bot.rcon_manager.max_players(serveraddr, MATCH_PLAYER_COUNT)

            pin = 5
            await self.bot.rcon_manager.set_pin(serveraddr, pin)
            server_name = f"VALORS MM - {self.match_id}"
            await self.bot.rcon_manager.set_name(serveraddr, server_name)

            embed = nextcord.Embed(title=f"Match [0/{MATCH_PLAYER_COUNT}]", description=f"Server ready!", color=VALORS_THEME1)
            embed.set_image(match_map.media)
            embed.add_field(name=f"Team A - {match_sides[0].name}", 
                value='\n'.join([f"- <@{player.user_id}>" for player in self.players if player.team == Team.A]))
            embed.add_field(name=f"Team B - {match_sides[1].name}", 
                value='\n'.join([f"- <@{player.user_id}>" for player in self.players if player.team == Team.B]))
            embed.add_field(name="TDM Server", value=f"`{server_name}`", inline=False)
            embed.add_field(name="Pin", value=f"`{pin}`")
            embed.add_field(name=f"{match_map.map}:", value="\u200B", inline=False)
            await match_message.edit(embed=embed)

            current_players = set()
            server_players = set()
            expected_unique_ids = {
                str(platform_id)
                for player in self.players
                for platform_id in player.user_platform_mappings
            }
            
            while True:
                player_log = f"[{self.match_id}] Waiting on players: {len(server_players)}/{MATCH_PLAYER_COUNT}"
                VariableLog.debug(player_log)
                player_list = await self.bot.rcon_manager.player_list(serveraddr)
                current_players = { str(p['UniqueId']) for p in player_list.get('PlayerList', []) }

                if len(current_players) == MATCH_PLAYER_COUNT:
                    break
                # if expected_unique_ids.intersection(current_players):
                #     break

                new_players = current_players - server_players

                if current_players != server_players:
                    embed.title = f"Match [{len(current_players)}/{MATCH_PLAYER_COUNT}]"
                    asyncio.create_task(match_message.edit(embed=embed))
                    log.info(f"[{self.match_id}] New players joined: {new_players}")
                    for platform_id in new_players:
                        player = next((
                            player for player in self.players 
                            for p in player.user_platform_mappings
                            if p.platform_id == platform_id
                        ), None)
                        
                        if player:
                            teamid = self.match.b_side.value if player.team == Team.B else 1 - self.match.b_side.value
                            team_list = await self.bot.rcon_manager.inspect_team(serveraddr, Team(teamid))
                            if platform_id not in (p['UniqueId'] for p in team_list.get('InspectList', [])):
                                log.info(f"[{self.match_id}] Moving player {platform_id} to team {teamid}")
                                await self.bot.rcon_manager.allocate_team(serveraddr, platform_id, teamid)
                            else:
                                log.info(f"[{self.match_id}] Player {platform_id} already in team {teamid}")
                        else:
                            log.info(f"[{self.match_id}] Unauthorized player {platform_id} found. Kicking.")
                            await self.bot.rcon_manager.kick_player(serveraddr, platform_id)
                
                server_players = current_players
                await asyncio.sleep(3)
            await self.increment_state()
        
        if check_state(MatchState.MATCH_START_SND):
            m = next((m for m in maps if m.map == self.match.map), maps[0])
            server_maps = await self.bot.rcon_manager.list_maps(serveraddr)
            await self.bot.rcon_manager.add_map(serveraddr, m.resource_id if m.resource_id else m.map, 'SND')
            for ma in server_maps.get('MapList', []):
                await self.bot.rcon_manager.remove_map(serveraddr, ma['MapId'], ma['GameMode'], retry_attempts=1)
            await self.bot.rcon_manager.set_searchndestroy(serveraddr, m.resource_id if m.resource_id else m.map)
            log.info(f"[{self.match_id}] Switching to SND")

            embed = nextcord.Embed(title="Match started!", description="May the best team win!", color=VALORS_THEME1)
            await self.match_thread.send(embed=embed)
            await self.increment_state()
        
        if check_state(MatchState.LOG_MATCH_HAPPENING):
            embed = log_message.embeds[0]
            embed.description = "Match in progress"
            log_message = await log_message.edit(embed=embed)
            await self.increment_state()

        if check_state(MatchState.MATCH_WAIT_FOR_END):
            team_scores = [0, 0]
            users_match_stats = {}
            last_users_match_stats = {}
            disconnection_tracker = { player.user_id: 0 for player in self.players }
            last_round_number = 0
            abandoned_users = []
            changed_users = {}
            players_dict = {}
            
            users_summary_data = await self.bot.store.get_users_summary_stats(
                self.guild_id, [p.user_id for p in self.players]
            )

            a_side = 'T' if self.match.b_side == Side.CT else 'CT'
            b_side = 'CT' if self.match.b_side == Side.CT else 'T'
            a_player_list = '\n'.join([f"- <@{player.user_id}>" for player in self.players if player.team == Team.A])
            b_player_list = '\n'.join([f"- <@{player.user_id}>" for player in self.players if player.team == Team.B])

            await self.wait_for_snd_mode()

            ready_to_continue = False
            max_score = 0
            reply = None
            while not ready_to_continue:
                if max_score >= 10:
                    ready_to_continue = True
                await asyncio.sleep(2)
                try:
                    reply = (await self.bot.rcon_manager.server_info(self.match.serveraddr))['ServerInfo']
                    if "Team0Score" not in reply: continue

                    team_scores = [int(reply['Team0Score']), int(reply['Team1Score'])]
                    max_score = max(team_scores)
                    self.current_round = int(reply.get('Round', self.current_round))

                    is_new_round = self.current_round > last_round_number
                    if is_new_round:
                        last_round_number = self.current_round
                        embed = log_message.embeds[0]
                        embed.description = "- Ongoing\n- Scores updating live"
                        a_score, b_score = (team_scores[1], team_scores[0]) if self.match.b_side == Side.CT else (team_scores[0], team_scores[1])
                        asyncio.create_task(self.bot.store.update(MMBotMatches, id=self.match_id, a_score=a_score, b_score=b_score))
                        if max_score >= 10: embed.description = f"{'A' if a_score > b_score else 'B'} Wins!"
                        embed.set_field_at(0, name=f"Team A - {a_side}: {a_score}", value=a_player_list)
                        embed.set_field_at(1, name=f"Team B - {b_side}: {b_score}", value=b_player_list)
                        asyncio.create_task(log_message.edit(embed=embed))
                        log.debug(f"[{self.match_id}] Round {self.current_round} completed. Scores: {team_scores[0]} - {team_scores[1]}")

                    players_data = await self.bot.rcon_manager.inspect_all(self.match.serveraddr, retry_attempts=1)
                    if not 'InspectList' in players_data: continue
                    players_dict = { player['UniqueId']: player for player in players_data['InspectList'] }
                    
                    changed_users.clear()
                    for user_id, current_stats in users_match_stats.items():
                        if user_id not in last_users_match_stats or current_stats != last_users_match_stats[user_id]:
                            changed_users[user_id] = current_stats

                    if changed_users:
                        await self.bot.store.upsert_users_match_stats(self.guild_id, self.match_id, changed_users)
                        for user_id, stats in changed_users.items():
                            last_users_match_stats[user_id] = copy.deepcopy(stats)

                    found_player_ids = await self.process_players(
                        players_dict, 
                        users_match_stats, 
                        users_summary_data, 
                        disconnection_tracker, 
                        is_new_round)
                    
                    if is_new_round:
                        self.check_disconnections(
                            found_player_ids, 
                            disconnection_tracker, 
                            abandoned_users)
                    
                    if abandoned_users:
                        await self.handle_abandons(
                            players_dict, 
                            abandoned_users, 
                            users_match_stats, 
                            users_summary_data, 
                            self.match_thread)
                        self.state = MatchState.MATCH_CLEANUP - 1
                        break
                except Exception as e:
                    tb = traceback.extract_tb(e.__traceback__)
                    _, line_number, func_name, _ = tb[-1]
                    log.warning(f"[{self.match_id}] [{func_name}:{line_number}] Error during match: {repr(e)}")
                    print("[Reply] ", reply)
            
            if not abandoned_users:
                await self.finalize_match(
                    players_dict, 
                    users_match_stats, 
                    users_summary_data, 
                    team_scores,
                    reply)

            await self.increment_state()
        
        if check_state(MatchState.MATCH_CLEANUP):
            pin = 5
            server_name = f"VALORS {server.region} #{server.id}"
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
            match = await self.bot.store.get_match(self.match_id)
            match_stats = await self.bot.store.get_match_stats(self.match_id)
            try:
                leaderboard_image = await generate_score_image(self.bot.cache, guild, match, match_stats)
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
            embed = nextcord.Embed(title="The match will terminate in 10 seconds", color=VALORS_THEME1)
            
            channel = guild.get_channel(settings.leaderboard_channel)
            try:
                await self.match_thread.send(embed=embed)
            except AttributeError:
                pass
            
            guild = self.bot.get_guild(self.guild_id)
            message = await channel.fetch_message(settings.leaderboard_message)
            ranks = await self.bot.store.get_ranks(guild.id)
            
            data = await self.bot.store.get_leaderboard(guild.id)
            previous_data = await self.bot.store.get_last_mmr_for_users(guild.id)
            embed = create_leaderboard_embed(guild, data, previous_data, ranks)
            asyncio.create_task(message.edit(embed=embed))
            await asyncio.sleep(10)
            # match_thread
            try:
                if self.match_thread: await self.match_thread.delete()
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
            for player in self.players:
                member = guild.get_member(player.user_id)
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
            # complete True
            await self.bot.store.update(MMBotMatches, id=self.match_id, complete=True)
            await self.increment_state()
