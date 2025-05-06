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

import time
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Callable, Dict, List, Tuple, cast
import random
from statistics import mean, median, stdev

from sqlalchemy import delete, desc, func, inspect, or_, text, update, case, and_
from sqlalchemy.dialects.postgresql import insert, INTERVAL
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.declarative import DeclarativeMeta
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.sql.functions import concat

from config import DATABASE_URL, PLACEMENT_MATCHES
from matches import MatchState
from utils.logger import Logger as log
from utils.utils import extract_late_time
from .models import *


class Database:

    @staticmethod
    def log_db_operation(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            result = await func(*args, **kwargs)
            if log.get_level() > log.DEBUG:
                return result
            end_time = time.time()
            execution_time = end_time - start_time

            return_size = len(result) if result is not None and hasattr(result, '__len__') else None

            log_message = f"{func.__name__} {execution_time*1000:.3f}ms"
            if return_size is not None:
                log_message += f", Return Size: {return_size}"

            log.debug(log_message)

            return result
        return wrapper

    def __init__(self) -> None:
        self._session_maker = async_sessionmaker(
            create_async_engine(DATABASE_URL, pool_size=20, max_overflow=0), 
            class_=AsyncSession, 
            autoflush=True, 
            expire_on_commit=False, 
            info=None)
    
###########
# TICKETS #
###########

    @log_db_operation
    async def create_ticket(self, guild_id: int, user_id: int, username: str) -> int | None:
        async with self._session_maker() as session:
            ticket_id = await session.scalar(
                insert(Tickets)
                .values({
                    "guild_id": guild_id,
                    "user_id": user_id,
                    "username": username})
                .returning(Tickets.id))
            await session.commit()
            return ticket_id

    @log_db_operation
    async def get_ticket(self, ticket_id: int) -> Tickets:
        async with self._session_maker() as session:
            result = await session.execute(
                select(Tickets)
                .where(Tickets.id == ticket_id))
            return result.scalars().first()

    @log_db_operation
    async def get_ticket_by_channel(self, channel_id: int) -> Tickets:
        async with self._session_maker() as session:
            result = await session.execute(
                select(Tickets)
                .where(Tickets.channel_id == channel_id))
            return result.scalars().first()
    
    @log_db_operation
    async def update_ticket(self, ticket_id: int, **data):
        async with self._session_maker() as session:
            await session.execute(
                update(Tickets)
                .where(Tickets.id == ticket_id)
                .values(**data))
            await session.commit()
    
    @log_db_operation
    async def update_ticket_by_channel(self, channel_id: int, **data):
        async with self._session_maker() as session:
            await session.execute(
                update(Tickets)
                .where(Tickets.channel_id == channel_id)
                .values(**data))
            await session.commit()
    
    @log_db_operation
    async def save_transcript(self, archive: TicketTranscripts):
        async with self._session_maker() as session:
            session.add(archive)
            await session.commit()

###########
# CLASSIC #
###########
    @log_db_operation
    async def upsert(self, table: DeclarativeMeta, **data) -> None:
        async with self._session_maker() as session:
            await session.execute(
                insert(table)
                .values(**data)
                .on_conflict_do_update(index_elements=[key.name for key in inspect(table).primary_key], set_=data))
            await session.commit()
    
    @log_db_operation
    async def update(self, table: DeclarativeMeta, **data) -> None:
        async with self._session_maker() as session:
            await session.execute(update(table), [data])
            await session.commit()

    @log_db_operation
    async def insert(self, table: DeclarativeMeta, **data) -> None:
        async with self._session_maker() as session:
            await session.execute(
                insert(table)
                .values(**data))
            await session.commit()
    
    @log_db_operation
    async def remove(self, table: DeclarativeMeta, **conditions) -> None:
        async with self._session_maker() as session:
            stmt = delete(table).where(*[getattr(table, key) == value for key, value in conditions.items()])
            await session.execute(stmt)
            await session.commit()

################
# RCON SERVERS #
################
    @log_db_operation
    async def set_serveraddr(self, match_id: int, serveraddr: str) -> None:
        async with self._session_maker() as session:
            await session.execute(
                update(MMBotMatches)
                .where(MMBotMatches.id == match_id)
                .values(serveraddr=serveraddr))
            await session.commit()
        
    @log_db_operation
    async def get_serveraddr(self, match_id: int) -> str | None:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotMatches.serveraddr)
                .where(MMBotMatches.id == match_id))
            return result.scalars().first()
        
    @log_db_operation
    async def get_servers(self, free: bool=False) -> List[RconServers]:
        async with self._session_maker() as session:
            if free:
                result = await session.execute(
                    select(RconServers)
                    .where(RconServers.being_used == False)
                    .order_by(RconServers.id))
            else:
                result = await session.execute(
                    select(RconServers)
                    .order_by(RconServers.id))
            return list(result.scalars().all())
    
    @log_db_operation
    async def get_server(self, host: str, port: int) -> RconServers:
        async with self._session_maker() as session:
            result = await session.execute(
                select(RconServers)
                .where(
                    RconServers.host == host, 
                    RconServers.port == int(port)))
            return result.scalar_one_or_none()
    
    @log_db_operation
    async def add_server(self, host: str, port: int, password: str, region: str) -> None:
        async with self._session_maker() as session:
            session.add(RconServers(host=host, port=port, password=password, region=region))
            await session.commit()

    @log_db_operation
    async def remove_server(self, host: str, port: int) -> None:
        async with self._session_maker() as session:
            await session.execute(
                delete(RconServers)
                .where(
                    RconServers.host == host,
                    RconServers.port == port))
            await session.commit()

    @log_db_operation
    async def use_server(self, serveraddr: str) -> None:
        async with self._session_maker() as session:
            host, port = serveraddr.split(':')
            await session.execute(
                update(RconServers)
                .where(
                    RconServers.host == host,
                    RconServers.port == int(port))
                .values(being_used=True))
            await session.commit()

    @log_db_operation
    async def free_server(self, serveraddr: str) -> None:
        async with self._session_maker() as session:
            host, port = serveraddr.split(':')
            await session.execute(
                update(RconServers)
                .where(
                    RconServers.host == host,
                    RconServers.port == int(port))
                .values(being_used=False))
            await session.commit()

    @log_db_operation
    async def get_last_users_to_server_pings(self, guild_id: int, user_ids: List[int], serveraddr: str) -> Dict[int, int]:
        async with self._session_maker() as session:
            subquery = (
                select(
                    MMBotUserMatchStats.user_id,
                    func.max(MMBotUserMatchStats.timestamp).label("max_ts"))
                .join(MMBotMatches, MMBotUserMatchStats.match_id == MMBotMatches.id)
                .where(
                    MMBotUserMatchStats.guild_id == guild_id,
                    MMBotUserMatchStats.user_id.in_(user_ids),
                    MMBotMatches.serveraddr == serveraddr)
                .group_by(MMBotUserMatchStats.user_id)
                .subquery())
            
            result = await session.execute(
                select(MMBotUserMatchStats)
                .join(subquery, and_(
                    MMBotUserMatchStats.user_id == subquery.c.user_id,
                    MMBotUserMatchStats.timestamp == subquery.c.max_ts)))
            
            return { cast(int, stat.user_id): cast(int, stat.ping) for stat in result.scalars().all() }

########
# BOT #
########
    @log_db_operation
    async def get_settings(self, guild_id: int) -> BotSettings | None:
        async with self._session_maker() as session:
            result = await session.execute(
                select(BotSettings)
                .where(BotSettings.guild_id == guild_id))
            return result.scalars().first()
    
    @log_db_operation
    async def get_regions(self, guild_id: int) -> List[BotRegions]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(BotRegions)
                .where(BotRegions.guild_id == guild_id)
                .order_by(BotRegions.index))
            return list(result.scalars().all())

    @log_db_operation
    async def get_ranks(self, guild_id: int) -> List[MMBotRanks]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotRanks)
                .where(MMBotRanks.guild_id == guild_id)
                .order_by(MMBotRanks.mmr_threshold))
            return list(result.scalars().all())
    
    @log_db_operation
    async def set_ranks(self, guild_id: int, ranks: Dict[str, Dict[str, int]]) -> None:
        async with self._session_maker() as session:
            ranks_list = [
                {**rank_data, 'guild_id': guild_id}
                for _, rank_data in ranks.items()
            ]
            await session.execute(
                insert(MMBotRanks)
                .values(ranks_list))
            await session.commit()
    
    @log_db_operation
    async def update_user_coords(self, guild_id: int, user_coords: Dict[int, tuple]) -> None:
            column_mapping = {
                'lat': (0, MMBotUsers.lat),
                'lon': (1, MMBotUsers.lon),
                'height': (2, MMBotUsers.height),
                'uncertainty': (3, MMBotUsers.uncertainty)
            }
            
            case_values = {
                column_name: case(
                    *[(MMBotUsers.user_id == uid, coords[idx]) for uid, coords in user_coords.items()],
                    else_=default_attr)
                for column_name, (idx, default_attr) in column_mapping.items()
            }
            
            async with self._session_maker() as session:
                await session.execute(
                    update(MMBotUsers)
                    .where(
                        MMBotUsers.guild_id == guild_id,
                        MMBotUsers.user_id.in_(list(user_coords.keys())))
                    .values(**case_values))
                await session.commit()
    
    @log_db_operation
    async def set_user_platform(self, user_id: int, platform: str, platform_id: str, guild_id: int) -> None:
        async with self._session_maker() as session:
            await session.execute(
                insert(UserPlatformMappings)
                .values({"user_id": user_id, "guild_id": guild_id, "platform": platform, "platform_id": platform_id})
                .on_conflict_do_update(index_elements=["user_id", "platform", "guild_id"], set_={"platform": platform, "platform_id": platform_id}))
            await session.commit()
    
    @log_db_operation
    async def transfer_guild_data(self, source_guild_id: int, destination_guild_id: int):
        async with self._session_maker() as session:
            async with session.begin():
                guilds = await session.execute(
                    select(BotSettings).where(BotSettings.guild_id.in_([source_guild_id, destination_guild_id]))
                )
                if len(guilds.all()) != 2:
                    raise ValueError("Both source and destination guilds must exist in the BotSettings table")

                await session.execute(text("SET session_replication_role = 'replica'"))
                
                tables = [
                    BotSettings, 
                    UserPlatformMappings, 
                    MMBotUsers, 
                    MMBotQueueUsers, 
                    MMBotBlockedUsers, 
                    MMBotWarnedUsers, 
                    MMBotUserMatchStats, 
                    MMBotUserSummaryStats, 
                    MMBotUserAbandons, 
                    MMBotMatchPlayers, 
                    MMBotUserBans, 
                    MMBotUserMapPicks, 
                    MMBotUserSidePicks, 
                    MMBotUserNotifications, 
                    MMBotMods
                ]

                for table in tables:
                    source_data = await session.execute(
                        select(table).where(table.guild_id == source_guild_id))
                    source_data = source_data.all()

                    for row in source_data:
                        row_dict = {c.key: getattr(row[0], c.key) for c in inspect(table).mapper.column_attrs}
                        row_dict['guild_id'] = destination_guild_id
                        
                        # Remove id from row_dict if it's an auto-incrementing field
                        # This will let the database assign a new id automatically
                        if 'id' in row_dict and hasattr(table, 'id') and isinstance(getattr(table, 'id').type, Integer) and getattr(table, 'id').primary_key:
                            del row_dict['id']
                        
                        # Generate filter condition for matching existing records
                        filter_conditions = []
                        for key in inspect(table).primary_key:
                            if key.name in row_dict and key.name != 'id':  # Skip 'id' as it's being regenerated
                                filter_conditions.append(getattr(table, key.name) == row_dict[key.name])
                        
                        # Only delete existing record if we have filter conditions
                        if filter_conditions:
                            await session.execute(
                                delete(table).where(*filter_conditions))

                        # Insert new record with values from row_dict
                        stmt = insert(table).values(**row_dict)
                        await session.execute(stmt)
                
                await session.execute(text("SET session_replication_role = 'origin'"))
                
                log.info(f"Transferred guild data from {source_guild_id} to {destination_guild_id}")


########
# USER #
########
    @log_db_operation
    async def get_user(self, guild_id: int, user_id: int) -> MMBotUsers:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotUsers)
                .where(
                    MMBotUsers.guild_id == guild_id, 
                    MMBotUsers.user_id == user_id))
            return result.scalars().first()
    
    @log_db_operation
    async def get_user_platforms(self, guild_id: int, user_id: int) -> List[UserPlatformMappings]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(UserPlatformMappings)
                .where(
                    UserPlatformMappings.guild_id == guild_id, 
                    UserPlatformMappings.user_id == user_id)
                .order_by(UserPlatformMappings.platform))
            return list(result.scalars().all())
    
    @log_db_operation
    async def get_users_summary_stats(self, guild_id: int, user_ids: List[int]) -> Dict[int, MMBotUserSummaryStats]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotUserSummaryStats)
                .where(
                    MMBotUserSummaryStats.guild_id == guild_id,
                    MMBotUserSummaryStats.user_id.in_(user_ids)))
            stats_list = result.scalars().all()
            return { int(cast(int, stat.user_id)): stat for stat in stats_list }
    
    @log_db_operation
    async def set_users_summary_stats(self, guild_id: int, users_data: Dict[int, Dict[str, Any]]) -> None:
        async with self._session_maker() as session:
            async with session.begin():
                for user_id, user_data in users_data.items():
                    await session.execute(
                        update(MMBotUserSummaryStats)
                        .where(
                            MMBotUserSummaryStats.guild_id == guild_id,
                            MMBotUserSummaryStats.user_id == user_id)
                        .values(user_data))

    @log_db_operation
    async def upsert_users_match_stats(self, guild_id: int, match_id: int, user_stats: Dict[int, Dict[str, Any]]) -> None:
        async with self._session_maker() as session:
            async with session.begin():
                for user_id, stats in user_stats.items():
                    stmt = insert(MMBotUserMatchStats).values(
                        guild_id=guild_id,
                        user_id=user_id,
                        match_id=match_id,
                        **stats)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=['guild_id', 'user_id', 'match_id'],
                        set_=stats)
                    await session.execute(stmt)
    
    @log_db_operation
    async def get_users(self, guild_id: int, user_ids: List[int] | None = None) -> List[MMBotUsers]:
        async with self._session_maker() as session:
            query = select(MMBotUsers).options(selectinload(MMBotUsers.summary_stats)).where(MMBotUsers.guild_id == guild_id)
            if user_ids:
                query = query.where(MMBotUsers.user_id.in_(user_ids))
            result = await session.execute(query)
            return list(result.scalars().all())
    
    @log_db_operation
    async def add_user(self, guild_id: int, user_id: int) -> MMBotUsers:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotUsers)
                .where(
                    MMBotUsers.guild_id == guild_id, 
                    MMBotUsers.user_id == user_id))
            user = result.scalars().first()

            if user is None:
                session.add(MMBotUsers(guild_id=guild_id, user_id=user_id,))
                await session.commit()

                result = await session.execute(
                    select(MMBotUsers)
                    .where(
                        MMBotUsers.guild_id == guild_id, 
                        MMBotUsers.user_id == user_id))
                user = result.scalars().first()
            return user

    @log_db_operation
    async def null_user_region(self, guild_id: int, label: str):
        async with self._session_maker() as session:
            await session.execute(
                update(MMBotUsers)
                .where(MMBotUsers.guild_id == guild_id, MMBotUsers.region == label)
                .values(region=None))
            await session.commit()

    @log_db_operation
    async def get_user_team(self, guild_id: int, user_id: int, match_id: int) -> Team:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotMatchPlayers.team)
                .where(
                    MMBotMatchPlayers.guild_id == guild_id,
                    MMBotMatchPlayers.user_id == user_id,
                    MMBotMatchPlayers.match_id == match_id))
            return result.scalars().first()
    
    @log_db_operation
    async def get_leaderboard(self, guild_id: int) -> List[Dict[str, Any]]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotUserSummaryStats)
                .where(
                    MMBotUserSummaryStats.guild_id == guild_id,
                    MMBotUserSummaryStats.games > PLACEMENT_MATCHES)
                .order_by(desc(MMBotUserSummaryStats.mmr)))
            return [
                {
                    "user_id": row.MMBotUserSummaryStats.user_id,
                    "mmr": row.MMBotUserSummaryStats.mmr,
                    "games": row.MMBotUserSummaryStats.games,
                    "wins": row.MMBotUserSummaryStats.wins,
                    "win_rate": row.MMBotUserSummaryStats.wins / row.MMBotUserSummaryStats.games if row.MMBotUserSummaryStats.games > 0 else 0,
                    "avg_kills": row.MMBotUserSummaryStats.total_kills / row.MMBotUserSummaryStats.games if row.MMBotUserSummaryStats.games > 0 else 0,
                    "avg_deaths": row.MMBotUserSummaryStats.total_deaths / row.MMBotUserSummaryStats.games if row.MMBotUserSummaryStats.games > 0 else 0,
                    "avg_assists": row.MMBotUserSummaryStats.total_assists / row.MMBotUserSummaryStats.games if row.MMBotUserSummaryStats.games > 0 else 0,
                    "avg_score": row.MMBotUserSummaryStats.total_score / row.MMBotUserSummaryStats.games if row.MMBotUserSummaryStats.games > 0 else 0,
                }
                for row in result
            ]
        
    @log_db_operation
    async def get_last_mmr_for_users(self, guild_id: int) -> Dict[int, int]:
        async with self._session_maker() as session:
            subquery = (
                select(
                    MMBotUserMatchStats.user_id,
                    func.max(MMBotUserMatchStats.match_id).label('latest_match_id'))
                .where(
                    MMBotUserMatchStats.guild_id == guild_id,
                    MMBotUserMatchStats.abandoned == False)
                .group_by(MMBotUserMatchStats.user_id)
                .subquery())

            query = (
                select(
                    MMBotUserMatchStats.user_id,
                    MMBotUserMatchStats.mmr_before)
                .join(
                    subquery,
                    (MMBotUserMatchStats.user_id == subquery.c.user_id) &
                    (MMBotUserMatchStats.match_id == subquery.c.latest_match_id))
                .where(MMBotUserMatchStats.guild_id == guild_id))

            result = await session.execute(query)
            return { row.user_id: row.mmr_before for row in result }
        
    async def get_leaderboard_with_previous_mmr(self, guild_id: int) -> List[Dict[str, Any]]:
        async with self._session_maker() as session:
            subquery = (
                select(
                    MMBotUserMatchStats.user_id,
                    func.max(MMBotUserMatchStats.match_id).label('latest_match_id'))
                .where(
                    MMBotUserMatchStats.guild_id == guild_id,
                    MMBotUserMatchStats.abandoned == False)
                .group_by(MMBotUserMatchStats.user_id)
                .subquery())

            query = (
                select(
                    MMBotUserSummaryStats,
                    MMBotUserMatchStats.mmr_before.label('previous_mmr'))
                .join(
                    subquery,
                    (MMBotUserSummaryStats.user_id == subquery.c.user_id))
                .join(
                    MMBotUserMatchStats,
                    (MMBotUserMatchStats.user_id == subquery.c.user_id) &
                    (MMBotUserMatchStats.match_id == subquery.c.latest_match_id))
                .where(
                    MMBotUserSummaryStats.guild_id == guild_id,
                    MMBotUserSummaryStats.games >= PLACEMENT_MATCHES)
                .order_by(desc(MMBotUserSummaryStats.mmr)))

            result = await session.execute(query)
            return [
                {
                    "user_id": row.MMBotUserSummaryStats.user_id,
                    "mmr": row.MMBotUserSummaryStats.mmr,
                    "previous_mmr": row.previous_mmr,
                    "games": row.MMBotUserSummaryStats.games,
                    "wins": row.MMBotUserSummaryStats.wins,
                    "win_rate": row.MMBotUserSummaryStats.wins / row.MMBotUserSummaryStats.games if row.MMBotUserSummaryStats.games > 0 else 0,
                    "avg_kills": row.MMBotUserSummaryStats.total_kills / row.MMBotUserSummaryStats.games if row.MMBotUserSummaryStats.games > 0 else 0,
                    "avg_deaths": row.MMBotUserSummaryStats.total_deaths / row.MMBotUserSummaryStats.games if row.MMBotUserSummaryStats.games > 0 else 0,
                    "avg_assists": row.MMBotUserSummaryStats.total_assists / row.MMBotUserSummaryStats.games if row.MMBotUserSummaryStats.games > 0 else 0,
                    "avg_score": row.MMBotUserSummaryStats.total_score / row.MMBotUserSummaryStats.games if row.MMBotUserSummaryStats.games > 0 else 0,
                }
                for row in result
            ]

    async def get_user_pick_preferences(self, guild_id: int, user_id: int) -> Dict[str, Dict[str, int]]:
        async with self._session_maker() as session:
            bans_query = select(MMBotUserBans.map, func.count(MMBotUserBans.map).label('count')).\
                where(MMBotUserBans.guild_id == guild_id, MMBotUserBans.user_id == user_id).\
                group_by(MMBotUserBans.map)
            bans_result = await session.execute(bans_query)
            bans = dict(bans_result.all())

            picks_query = select(MMBotUserMapPicks.map, func.count(MMBotUserMapPicks.map).label('count')).\
                where(MMBotUserMapPicks.guild_id == guild_id, MMBotUserMapPicks.user_id == user_id).\
                group_by(MMBotUserMapPicks.map)
            picks_result = await session.execute(picks_query)
            picks = dict(picks_result.all())

            sides_query = select(MMBotUserSidePicks.side, func.count(MMBotUserSidePicks.side).label('count')).\
                where(MMBotUserSidePicks.guild_id == guild_id, MMBotUserSidePicks.user_id == user_id).\
                group_by(MMBotUserSidePicks.side)
            sides_result = await session.execute(sides_query)
            sides = dict(sides_result.all())

            return { 'bans': bans, 'picks': picks, 'sides': sides }

    @log_db_operation
    async def get_user_last_queue_time_remaining(self, guild_id: int, match_id: int, user_ids: List[int]) -> Dict[int, int]:
        async with self._session_maker() as session:
            match_start = (
                select(MMBotMatches.start_timestamp)
                .where(MMBotMatches.id == match_id)
                .scalar_subquery())

            query = (
                select(
                    MMBotQueueUsers.user_id,
                    func.coalesce(
                        func.round(MMBotQueueUsers.queue_expiry - func.extract('epoch', match_start)), 0
                    ).label('time_remaining'))
                .where(
                    MMBotQueueUsers.guild_id == guild_id,
                    MMBotQueueUsers.user_id.in_(user_ids))
                .order_by(MMBotQueueUsers.user_id, desc(MMBotQueueUsers.timestamp))
                .distinct(MMBotQueueUsers.user_id))

            result = await session.execute(query)
            return { row.user_id: max(0, int(row.time_remaining)) for row in result }

    @log_db_operation
    async def get_player_play_periods(self, guild_id: int, user_id: int, limit: int=50) -> List[Tuple[datetime, datetime]]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(
                    MMBotMatches.start_timestamp,
                    MMBotMatches.end_timestamp)
                .join(
                    MMBotUserMatchStats,
                    (MMBotUserMatchStats.match_id == MMBotMatches.id) &
                    (MMBotUserMatchStats.guild_id == guild_id) &
                    (MMBotUserMatchStats.user_id == user_id))
                .where(
                    MMBotMatches.end_timestamp.isnot(None))
                .order_by(desc(MMBotMatches.start_timestamp))
                .limit(limit))
            matches = result.all()
            return [(match.start_timestamp, match.end_timestamp) for match in matches]
    
    @log_db_operation
    async def get_user_blocks(self, guild_id: int) -> List[MMBotBlockedUsers]:
        async with self._session_maker() as session:
            now = datetime.now(timezone.utc)
            result = await session.execute(
                select(MMBotBlockedUsers)
                .where(
                    MMBotBlockedUsers.guild_id == guild_id,
                    MMBotBlockedUsers.expiration > now))
            return result.scalars().all()
    
    @log_db_operation
    async def set_user_block(self, guild_id: int, user_id: int, expiration: datetime, reason: str = None, blocked_by: int = None):
        async with self._session_maker() as session:
            now = datetime.now(timezone.utc)
            existing_block = await session.execute(
                select(MMBotBlockedUsers)
                .where(
                    MMBotBlockedUsers.guild_id == guild_id,
                    MMBotBlockedUsers.user_id == user_id,
                    MMBotBlockedUsers.expiration > now))
            existing_block = existing_block.scalar_one_or_none()

            if existing_block:
                update_values = {"expiration": expiration}
                if reason is not None:
                    update_values["reason"] = reason
                if blocked_by is not None:
                    update_values["blocked_by"] = blocked_by
                
                await session.execute(
                    update(MMBotBlockedUsers)
                    .where(
                        MMBotBlockedUsers.guild_id == guild_id,
                        MMBotBlockedUsers.user_id == user_id)
                    .values(**update_values))
            else:
                insert_values = {
                    "guild_id": guild_id,
                    "user_id": user_id,
                    "expiration": expiration
                }
                if reason is not None:
                    insert_values["reason"] = reason
                if blocked_by is not None:
                    insert_values["blocked_by"] = blocked_by
                
                await session.execute(
                    insert(MMBotBlockedUsers)
                    .values(**insert_values))
            
            await session.commit()

    @log_db_operation
    async def transfer_user(self, guild_id: int, old_user_id: int, new_user_id: int):
        async with self._session_maker() as session:
            async with session.begin():
                old_user = await session.execute(
                    select(MMBotUsers).where(
                        MMBotUsers.guild_id == guild_id,
                        MMBotUsers.user_id == old_user_id))
                new_user = await session.execute(
                    select(MMBotUsers).where(
                        MMBotUsers.guild_id == guild_id,
                        MMBotUsers.user_id == new_user_id))
                
                if not old_user.scalar_one_or_none() or not new_user.scalar_one_or_none():
                    raise ValueError("Both old and new users must exist in the database")

                tables_columns = [
                    (UserPlatformMappings, ['user_id']),
                    (MMBotQueueUsers, ['user_id']),
                    (MMBotBlockedUsers, ['user_id', 'blocked_by']),
                    (MMBotWarnedUsers, ['user_id', 'moderator_id']),
                    (MMBotUserMatchStats, ['user_id']),
                    (MMBotUserAbandons, ['user_id']),
                    (MMBotMatchPlayers, ['user_id']),
                    (MMBotUserBans, ['user_id']),
                    (MMBotUserMapPicks, ['user_id']),
                    (MMBotUserSidePicks, ['user_id']),
                    (MMBotUserNotifications, ['user_id'])
                ]

                for table, columns in tables_columns:
                    for column in columns:
                        await session.execute(
                            update(table)
                            .where(
                                table.guild_id == guild_id,
                                getattr(table, column) == old_user_id)
                            .values(**{column: new_user_id}))
                
                await session.execute(
                    delete(MMBotUserSummaryStats)
                    .where(
                        MMBotUserSummaryStats.guild_id == guild_id,
                        MMBotUserSummaryStats.user_id == new_user_id))
                
                await session.execute(
                    update(MMBotUserSummaryStats)
                    .where(
                        MMBotUserSummaryStats.guild_id == guild_id,
                        MMBotUserSummaryStats.user_id == old_user_id)
                    .values(user_id=new_user_id))

                log.info(f"Transferred user data from {old_user_id} to {new_user_id} in guild {guild_id}")

    @log_db_operation
    async def get_user_missed_accepts(self, guild_id: int, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        async with self._session_maker() as session:
            query = (
                select(MMBotMatchPlayers.match_id, MMBotMatchPlayers.accepted, MMBotMatches.start_timestamp)
                .join(MMBotMatches, MMBotMatchPlayers.match_id == MMBotMatches.id)
                .where(MMBotMatchPlayers.guild_id == guild_id,
                    MMBotMatchPlayers.user_id == user_id,
                    MMBotMatchPlayers.accepted == False)
                .order_by(desc(MMBotMatches.start_timestamp))
                .limit(limit))

            result = await session.execute(query)
            return [{"match_id": row.match_id, "timestamp": row.start_timestamp} for row in result]


    @log_db_operation
    async def get_missed_accept_rankings(self, guild_id: int, limit: int = 100, offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
        async with self._session_maker() as session:
            subquery = (
                select(MMBotMatchPlayers.user_id,
                    func.count(MMBotMatchPlayers.match_id).label('total_matches'),
                    func.sum(case((MMBotMatchPlayers.accepted == False, 1), else_=0)).label('missed_accepts'))
                .where(MMBotMatchPlayers.guild_id == guild_id)
                .group_by(MMBotMatchPlayers.user_id)
                .subquery())

            query = (
                select(subquery.c.user_id,
                    subquery.c.total_matches,
                    subquery.c.missed_accepts,
                    (subquery.c.missed_accepts / subquery.c.total_matches).label('missed_rate'))
                .where(subquery.c.missed_accepts > 0)
                .order_by(desc('missed_rate')))

            count_query = select(func.count()).select_from(query.subquery())
            total_count = await session.execute(count_query)
            total_count = total_count.scalar_one()

            query = query.offset(offset).limit(limit)
            result = await session.execute(query)
            
            rankings = [{
                "user_id": row.user_id,
                "total_matches": row.total_matches,
                "missed_accepts": row.missed_accepts,
                "missed_rate": row.missed_rate
            } for row in result]

            return rankings, total_count


############
# ABANDONS #
############
    @log_db_operation
    async def ignore_abandon(self, guild_id: int, user_id: int):
        async with self._session_maker() as session:
            async with session.begin():
                last_abandon = await session.execute(
                    select(MMBotUserAbandons)
                    .where(
                        MMBotUserAbandons.guild_id == guild_id,
                        MMBotUserAbandons.user_id == user_id,
                        MMBotUserAbandons.ignored == False)
                    .order_by(MMBotUserAbandons.timestamp.desc())
                    .limit(1)
                    .with_for_update())
                last_abandon_record = last_abandon.scalars().first()
                if last_abandon_record:
                    last_abandon_record.ignored = True
                    await session.commit()

    @log_db_operation
    async def get_abandon_count_last_period(self, guild_id: int, user_id: int, period: int=60) -> Tuple[int, datetime]:
        async with self._session_maker() as session:
            last_abandon_query = (
                select(MMBotUserAbandons.timestamp)
                .where(
                    MMBotUserAbandons.guild_id == guild_id, 
                    MMBotUserAbandons.user_id == user_id,
                    MMBotUserAbandons.ignored == False)
                .order_by(MMBotUserAbandons.timestamp.desc())
                .limit(1))

            result = await session.execute(last_abandon_query)
            last_abandon = result.scalar()

            if last_abandon is None:
                return 0, None
            
            count_abandons = (
                select(func.count(MMBotUserAbandons.id))
                .where(
                    MMBotUserAbandons.guild_id == guild_id,
                    MMBotUserAbandons.user_id == user_id,
                    MMBotUserAbandons.ignored == False,
                    MMBotUserAbandons.timestamp >= last_abandon - timedelta(days=period)))
            
            result = await session.execute(count_abandons)
            count = result.scalar()
            return count, last_abandon

    @log_db_operation
    async def add_match_abandons(self, guild_id: int, match_id: int, abandoned_user_ids: List[int], mmr_losses: List[int]) -> None:
        if len(abandoned_user_ids) != len(mmr_losses):
            raise ValueError("Length of abandoned_user_ids must match length of mmr_losses")

        async with self._session_maker() as session:
            async with session.begin():
                abandons = [
                    {
                        'guild_id': guild_id, 
                        'user_id': user_id, 
                        'match_id': match_id
                    } for user_id in abandoned_user_ids
                ]
                await session.execute(insert(MMBotUserAbandons).values(abandons))

                mmr_updates = [
                    {'user_id': uid, 'mmr_change': mmr_loss}
                    for uid, mmr_loss in zip(abandoned_user_ids, mmr_losses)
                ]
                await session.execute(
                    update(MMBotUserMatchStats)
                    .where(MMBotUserMatchStats.match_id == match_id)
                    .values(
                        abandoned=True,
                        mmr_change=case(
                            *((
                                MMBotUserMatchStats.user_id == update['user_id'], 
                                update['mmr_change']
                            ) for update in mmr_updates),
                            else_=MMBotUserMatchStats.mmr_change)))
                
                await session.execute(
                    update(MMBotUserSummaryStats)
                    .where(MMBotUserSummaryStats.user_id.in_(abandoned_user_ids))
                    .values(mmr=case(
                        *((
                            MMBotUserSummaryStats.user_id == update['user_id'], 
                            MMBotUserSummaryStats.mmr + update['mmr_change']
                        ) for update in mmr_updates),
                        else_=MMBotUserSummaryStats.mmr)))

    @log_db_operation
    async def get_user_abandons(self, guild_id: int, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        async with self._session_maker() as session:
            query = (
                select(MMBotUserAbandons.match_id, MMBotUserAbandons.timestamp)
                .where(MMBotUserAbandons.guild_id == guild_id,
                    MMBotUserAbandons.user_id == user_id)
                .order_by(desc(MMBotUserAbandons.timestamp))
                .limit(limit)
            )

            result = await session.execute(query)
            return [{"match_id": row.match_id, "timestamp": row.timestamp} for row in result]

    @log_db_operation
    async def get_abandon_rankings(self, guild_id: int, limit: int = 100, offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
        async with self._session_maker() as session:
            matches_subquery = (
                select(MMBotUserMatchStats.user_id,
                    func.count(MMBotUserMatchStats.match_id).label('total_matches'))
                .where(MMBotUserMatchStats.guild_id == guild_id)
                .group_by(MMBotUserMatchStats.user_id)
                .subquery())

            abandons_subquery = (
                select(MMBotUserAbandons.user_id,
                    func.count(MMBotUserAbandons.match_id).label('abandons'))
                .where(MMBotUserAbandons.guild_id == guild_id)
                .group_by(MMBotUserAbandons.user_id)
                .subquery())

            query = (
                select(matches_subquery.c.user_id,
                    matches_subquery.c.total_matches,
                    func.coalesce(abandons_subquery.c.abandons, 0).label('abandons'),
                    (func.coalesce(abandons_subquery.c.abandons, 0) / matches_subquery.c.total_matches).label('abandon_rate'))
                .outerjoin(abandons_subquery, matches_subquery.c.user_id == abandons_subquery.c.user_id)
                .where(func.coalesce(abandons_subquery.c.abandons, 0) > 0)
                .order_by(desc('abandons')))

            count_query = select(func.count()).select_from(query.subquery())
            total_count = await session.execute(count_query)
            total_count = total_count.scalar_one()

            query = query.offset(offset).limit(limit)
            result = await session.execute(query)
            
            rankings = [{
                "user_id": row.user_id,
                "total_matches": row.total_matches,
                "abandons": row.abandons,
                "abandon_rate": row.abandon_rate
            } for row in result]

            return rankings, total_count

#########
# QUEUE #
#########
    @log_db_operation
    async def get_queue_users(self, channel_id: int) -> List[MMBotQueueUsers]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotQueueUsers)
                .where(
                    MMBotQueueUsers.queue_channel == channel_id, 
                    MMBotQueueUsers.in_queue == True))
            return list(result.scalars().all())
    
    @log_db_operation
    async def upsert_queue_user(self, user_id: int, guild_id: int, queue_channel: int, queue_expiry: int):
        if await self.in_queue(guild_id, user_id):
            async with self._session_maker() as session:
                await session.execute(
                    update(MMBotQueueUsers)
                    .where(
                        MMBotQueueUsers.user_id == user_id,
                        MMBotQueueUsers.guild_id == guild_id,
                        MMBotQueueUsers.queue_channel == queue_channel, 
                        MMBotQueueUsers.in_queue == True)
                    .values(queue_expiry=queue_expiry))
                await session.commit()
            return True
        await self.insert(MMBotQueueUsers, user_id=user_id, guild_id=guild_id, queue_channel=queue_channel, queue_expiry=queue_expiry)
        return False
    
    @log_db_operation
    async def unqueue_add_match_users(self, settings: BotSettings, channel_id: int) -> int:
        async with self._session_maker() as session:
            async with session.begin():
                result = await session.execute(
                    select(MMBotQueueUsers)
                    .where(
                        MMBotQueueUsers.queue_channel == channel_id, 
                        MMBotQueueUsers.in_queue == True))
                queue_users = result.scalars().all()
                
                await session.execute(
                    update(MMBotQueueUsers)
                    .where(
                        MMBotQueueUsers.queue_channel == channel_id, 
                        MMBotQueueUsers.in_queue == True)
                    .values(in_queue=False))
                
                match = MMBotMatches(
                    queue_channel=channel_id, 
                    maps_range=settings.mm_maps_range)
                session.add(match)
                await session.flush()

                result = await session.execute(
                    select(MMBotMatches)
                    .where(
                        MMBotMatches.queue_channel == channel_id,
                        MMBotMatches.complete == False)
                    .order_by(MMBotMatches.id.desc()))
                
                new_match = result.scalars().first()


                match_users = [
                    { 'guild_id': user.guild_id, 'user_id': user.user_id, 'match_id': new_match.id }
                    for user in queue_users
                ]
                insert_stmt = insert(MMBotMatchPlayers).values(match_users)
                await session.execute(insert_stmt)
                return new_match.id
    
    @log_db_operation
    async def unqueue_user_guild(self, guild_id: int, user_id: int):
        async with self._session_maker() as session:
            await session.execute(
                update(MMBotQueueUsers)
                .where(
                    MMBotQueueUsers.guild_id == guild_id, 
                    MMBotQueueUsers.user_id == user_id,
                    MMBotQueueUsers.in_queue == True)
                .values(in_queue=False))
            await session.commit()
    
    @log_db_operation
    async def unqueue_user(self, channel_id: int, user_id: int):
        async with self._session_maker() as session:
            await session.execute(
                update(MMBotQueueUsers)
                .where(
                    MMBotQueueUsers.queue_channel == channel_id, 
                    MMBotQueueUsers.user_id == user_id,
                    MMBotQueueUsers.in_queue == True)
                .values(in_queue=False))
            await session.commit()
    
    @log_db_operation
    async def in_queue(self, guild_id: int, user_id: int) -> bool:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotQueueUsers)
                .where(
                    MMBotQueueUsers.guild_id == guild_id, 
                    MMBotQueueUsers.user_id == user_id,
                    MMBotQueueUsers.in_queue == True))
            return result.scalars().first() is not None

###########
# MATCHES #
###########
    @log_db_operation
    async def get_ongoing_matches(self) -> List[MMBotMatches]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotMatches)
                .where(MMBotMatches.complete == False))
            return result.scalars().all()
    
    @log_db_operation
    async def save_match_state(self, match_id: int, state: MatchState):
        async with self._session_maker() as session:
            await session.execute(
                update(MMBotMatches)
                .where(MMBotMatches.id == match_id)
                .values(state=state))
            await session.commit()
    
    @log_db_operation
    async def load_match_state(self, match_id: int) -> MatchState:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotMatches.state)
                .where(MMBotMatches.id == match_id))
            return MatchState(result.scalars().first())
    
    @log_db_operation
    async def get_match(self, match_id: int) -> MMBotMatches:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotMatches)
                .where(MMBotMatches.id == match_id))
            return result.scalars().first()
    
    @log_db_operation
    async def get_last_match(self, guild_id: int) -> MMBotMatches:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotMatches)
                .join(BotSettings, MMBotMatches.queue_channel == BotSettings.mm_queue_channel)
                .where(
                    MMBotMatches.end_timestamp.isnot(None),
                    BotSettings.guild_id == guild_id)
                .order_by(desc(MMBotMatches.id))
                .limit(1))
            return result.scalars().first()
    
    @log_db_operation
    async def get_match_from_channel(self, channel_id: int) -> MMBotMatches:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotMatches)
                .where(or_(
                    MMBotMatches.match_thread == channel_id,
                    MMBotMatches.a_thread == channel_id,
                    MMBotMatches.b_thread == channel_id)))
            return result.scalars().first()

    @log_db_operation
    async def get_players(self, match_id: int) -> List[MMBotMatchPlayers]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotMatchPlayers)
                .options(selectinload(MMBotMatchPlayers.user_platform_mappings))
                .where(MMBotMatchPlayers.match_id == match_id))
            return result.scalars().all()
    
    @log_db_operation
    async def get_unaccepted_players(self, match_id: int) -> List[MMBotMatchPlayers]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotMatchPlayers)
                .where(
                    MMBotMatchPlayers.match_id == match_id, 
                    MMBotMatchPlayers.accepted == False))
            return result.scalars().all()
        
    @log_db_operation
    async def get_player(self, match_id: int, user_id: int) -> MMBotMatchPlayers:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotMatchPlayers)
                .options(joinedload(MMBotMatchPlayers.user_platform_mappings))
                .where(MMBotMatchPlayers.match_id == match_id)
                .where(MMBotMatchPlayers.user_id == user_id))
            return result.scalars().first()
    
    @log_db_operation
    async def get_accepted_players(self, match_id: int) -> int:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotMatchPlayers.user_id)
                .where(
                    MMBotMatchPlayers.match_id == match_id,
                    MMBotMatchPlayers.accepted == True))
            return result.scalars().all()
    
    @log_db_operation
    async def is_user_in_match(self, user_id: int) -> bool:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotMatchPlayers)
                .join(MMBotMatches, MMBotMatchPlayers.match_id == MMBotMatches.id)
                .filter(
                    MMBotMatchPlayers.user_id == user_id,
                    MMBotMatches.complete == False))
            match_user = result.scalars().first()
            return match_user is not None
    
    @log_db_operation
    async def set_players_team(self, match_id: int, user_teams: Dict[Team, List[int]]):
        async with self._session_maker() as session:
            async with session.begin():
                for team, user_ids in user_teams.items():
                    await session.execute(
                        update(MMBotMatchPlayers)
                        .where(
                            MMBotMatchPlayers.match_id == match_id,
                            MMBotMatchPlayers.user_id.in_(user_ids))
                        .values(team=team))

    @log_db_operation
    async def remove_match_and_players(self, match_id: int) -> None:
        async with self._session_maker() as session:
            async with session.begin():
                await session.execute(
                    delete(MMBotMatchPlayers)
                    .where(MMBotMatchPlayers.match_id == match_id))
                await session.execute(
                    delete(MMBotMatches)
                    .where(MMBotMatches.id == match_id))
                await session.commit()


##############
# MATCH BANS #
##############
    @log_db_operation
    async def set_map_bans(self, match_id: int, bans: list, team: Team):
        async with self._session_maker() as session:
            stmt = update(MMBotMatches).where(MMBotMatches.id == match_id)
            if team == Team.A:
                stmt = stmt.values(a_bans=bans)
            elif team == Team.B:
                stmt = stmt.values(b_bans=bans)
            await session.execute(stmt)
            await session.commit()

    @log_db_operation
    async def get_ban_counts(self, guild_id: int, match_id: int, phase: Phase) -> List[Tuple[str, int]]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(
                    MMBotMaps.map,
                    func.count(MMBotUserBans.map).label('ban_count'))
                .outerjoin(MMBotUserBans, 
                    (MMBotUserBans.map == MMBotMaps.map) & 
                    (MMBotUserBans.match_id == match_id) & 
                    (MMBotUserBans.phase == phase))
                .where(
                    MMBotMaps.guild_id == guild_id,
                    MMBotMaps.active == True)
                .group_by(MMBotMaps.map, MMBotMaps.order)
                .order_by(MMBotMaps.order))
            ban_counts = result.all()
            return [(row.map, row.ban_count) for row in ban_counts]
    
    @log_db_operation
    async def get_ban_votes(self, match_id: int, phase: Phase) -> List[str]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotUserBans.map)
                .where(
                    MMBotUserBans.match_id == match_id,
                    MMBotUserBans.phase == phase))
            return list(result.scalars().all())
    
    @log_db_operation
    async def get_bans(self, match_id: int, team: Team | None = None) -> List[str]:
        async with self._session_maker() as session:
            if team == Team.A:
                result = await session.execute(
                    select(MMBotMatches.a_bans)
                    .where(MMBotMatches.id == match_id))
                bans = result.scalar_one_or_none()
                return bans if bans else []
            elif team == Team.B:
                result = await session.execute(
                    select(MMBotMatches.b_bans)
                    .where(MMBotMatches.id == match_id))
                bans = result.scalar_one_or_none()
                return bans if bans else []
            else:
                result = await session.execute(
                    select(MMBotMatches.a_bans, MMBotMatches.b_bans)
                    .where(MMBotMatches.id == match_id))
                bans = result.one_or_none()
                if bans:
                    a_bans, b_bans = bans
                    return (a_bans if a_bans else []) + (b_bans if b_bans else [])
                return []
    
    @log_db_operation
    async def get_user_map_bans(self, match_id: int, user_id: int) -> List[str]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotUserBans.map)
                .where(
                    MMBotUserBans.match_id == match_id,
                    MMBotUserBans.user_id == user_id))
            return list(result.scalars().all())

###############
# MATCH PICKS #
###############
    @log_db_operation
    async def get_map_vote_counts(self, guild_id: int, match_id: int) -> List[Tuple[str, int]]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(
                    MMBotMaps.map,
                    func.count(MMBotUserMapPicks.map).label('pick_count'))
                .outerjoin(MMBotUserMapPicks, 
                    (MMBotUserMapPicks.map == MMBotMaps.map) & 
                    (MMBotUserMapPicks.match_id == match_id))
                .where(
                    MMBotMaps.guild_id == guild_id, 
                    MMBotMaps.active == True)
                .group_by(MMBotMaps.map, MMBotMaps.order)
                .order_by(MMBotMaps.order))
            pick_counts = result.all()
            return [(row.map, row.pick_count) for row in pick_counts]

    @log_db_operation
    async def get_map_votes(self, match_id: int) -> List[str] | None:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotUserMapPicks.map)
                .where(
                    MMBotUserMapPicks.match_id == match_id))
            return list(result.scalars().all())

    @log_db_operation
    async def get_user_map_picks(self, match_id: int, user_id: int) -> List[str]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotUserMapPicks.map)
                .where(
                    MMBotUserMapPicks.match_id == match_id,
                    MMBotUserMapPicks.user_id == user_id))
            return list(result.scalars().all())

    @log_db_operation
    async def get_maps(self, guild_id: int, maps: List[str]) -> List[MMBotMaps]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotMaps)
                .where(
                    MMBotMaps.guild_id == guild_id,
                    MMBotMaps.map.in_(maps)))
            return list(result.scalars().all()) or []
    
    @log_db_operation
    async def get_match_map(self, guild_id: int, match_id: int) -> MMBotMaps | None:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotMatches.map)
                .where(MMBotMatches.id == match_id))
            map_string = result.scalars().first()
            if not map_string:
                return None
            
            result = await session.execute(
                select(MMBotMaps)
                .where(
                    MMBotMaps.guild_id == guild_id,
                    MMBotMaps.map == map_string))
            map_object = result.scalars().first()
            return map_object

    @log_db_operation
    async def get_match_sides(self, match_id: int) -> Tuple[str, str]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotMatches.b_side)
                .where(MMBotMatches.id == match_id))
            b_side = result.scalars().first()
            a_side = Side.CT if b_side == Side.T else Side.T
            return (str(a_side), str(b_side))

    @log_db_operation
    async def get_last_players(self, guild_id: int) -> List[MMBotMatchPlayers]:
        async with self._session_maker() as session:
            subquery = select(func.max(MMBotMatches.id)).where(MMBotMatches.complete == True).scalar_subquery()
            result = await session.execute(
                select(MMBotMatchPlayers)
                .options(selectinload(MMBotMatchPlayers.user_platform_mappings))
                .join(MMBotMatches, MMBotMatchPlayers.match_id == MMBotMatches.id)
                .where(
                    MMBotMatchPlayers.guild_id == guild_id,
                    MMBotMatches.id == subquery))
            return result.scalars().all()

########
# MAPS #
########

    @log_db_operation
    async def get_last_played_maps(self, queue_channel: int, limit: int = 3) -> list[str]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotMatches.map)
                .where(
                    MMBotMatches.queue_channel == queue_channel,
                    MMBotMatches.end_timestamp.is_not(None),
                    MMBotMatches.complete)
                .order_by(desc(MMBotMatches.id))
                .limit(limit))
            return list(result.scalars().all())

    @log_db_operation
    async def shuffle_map_order(self, guild_id: int) -> None:
        async with self._session_maker() as session:
            async with session.begin():
                result = await session.execute(
                    select(MMBotMaps.map)
                    .where(
                        MMBotMaps.guild_id == guild_id,
                        MMBotMaps.active == True)
                    .order_by(MMBotMaps.order))
                maps = result.scalars().all()
                shuffled_maps = random.sample(maps, len(maps))
                for new_order, map_name in enumerate(shuffled_maps):
                    await session.execute(
                        update(MMBotMaps)
                        .where(
                            MMBotMaps.guild_id == guild_id,
                            MMBotMaps.map == map_name)
                        .values(order=new_order))
            await session.commit()

    @log_db_operation
    async def set_maps(self, guild_id: int, maps: List[Dict[str, str]]):
        data = [{"guild_id": guild_id, "map": m[0], "resource_id": m[1]['resource_id'], "media": m[1]['media'], "active": True, "order": n} for n, m in enumerate(maps)]
        
        async with self._session_maker() as session:
            async with session.begin():
                await session.execute(
                    update(MMBotMaps)
                    .where(
                        MMBotMaps.guild_id == guild_id, 
                        MMBotMaps.map.not_in([m[0] for m in maps]))
                    .values(active=False))
                insert_stmt = insert(MMBotMaps).values(data)
                update_stmt = insert_stmt.on_conflict_do_update(
                    index_elements=[key.name for key in inspect(MMBotMaps).primary_key],
                    set_={
                        "active": insert_stmt.excluded.active,
                        "order": insert_stmt.excluded.order,
                        "media": insert_stmt.excluded.media,
                        "resource_id": insert_stmt.excluded.resource_id})
                await session.execute(update_stmt)

    @log_db_operation
    async def get_all_maps(self, guild_id: int) -> List[MMBotMaps]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotMaps)
                .where(
                    MMBotMaps.guild_id == guild_id,
                    MMBotMaps.active == True)
                .order_by(MMBotMaps.order))
            return list(result.scalars().all())

########
# MODS #
########
    @log_db_operation
    async def set_mods(self, guild_id: int, mods: List[Dict[str, str]]):
        data = [{"guild_id": guild_id, "mod": m[0], "resource_id": m[1]['resource_id']} for m in mods]
        async with self._session_maker() as session:
            async with session.begin():
                await session.execute(
                    delete(MMBotMods).where(
                        MMBotMods.guild_id == guild_id,
                        MMBotMods.mod.not_in([m[0] for m in mods])))
                insert_stmt = insert(MMBotMods).values(data)
                update_stmt = insert_stmt.on_conflict_do_update(
                    index_elements=[key.name for key in inspect(MMBotMods).primary_key],
                    set_={"resource_id": insert_stmt.excluded.resource_id})
                await session.execute(update_stmt)

    @log_db_operation
    async def get_mods(self, guild_id: int) -> List[MMBotMods]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotMods)
                .where(MMBotMods.guild_id == guild_id))
            return result.scalars().all()

##############
# SIDE PICKS #
##############
    @log_db_operation
    async def get_side_vote_count(self, guild_id: int, match_id: int) -> List[Tuple[Side, int]]:
        async with self._session_maker() as session:
            sides_subquery = select(func.unnest(text('enum_range(NULL::side)')).label('side')).subquery()
            result = await session.execute(
                select(sides_subquery.c.side, func.count(MMBotUserSidePicks.side).label('pick_count'))
                .outerjoin(MMBotUserSidePicks, 
                    (MMBotUserSidePicks.side == sides_subquery.c.side) & 
                    (MMBotUserSidePicks.guild_id == guild_id) & 
                    (MMBotUserSidePicks.match_id == match_id))
                .group_by(sides_subquery.c.side))
            pick_counts = result.fetchall()
            return [(Side[row.side], row.pick_count) for row in pick_counts]
    
    @log_db_operation
    async def get_side_votes(self, match_id: int) -> List[Side] | None:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotUserSidePicks.side)
                .where(MMBotUserSidePicks.match_id == match_id))
            return list(result.scalars().all())

    @log_db_operation
    async def get_user_side_pick(self, match_id: int, user_id: int) -> List[Side]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotUserSidePicks.side)
                .where(
                    MMBotUserSidePicks.match_id == match_id,
                    MMBotUserSidePicks.user_id == user_id))
            return list(result.scalars().all())

###############
# MATCH STATs #
###############
    @log_db_operation
    async def get_user_summary_stats(self, guild_id: int, user_id: int) -> MMBotUserSummaryStats:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotUserSummaryStats)
                .where(
                    MMBotUserSummaryStats.guild_id == guild_id,
                    MMBotUserSummaryStats.user_id == user_id))
            return result.scalars().first()

    @log_db_operation
    async def get_match_stats(self, match_id: int) -> List[MMBotUserMatchStats]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotUserMatchStats)
                .where(MMBotUserMatchStats.match_id == match_id))
            return result.scalars().all()

    @log_db_operation
    async def get_recent_match_stats(self, guild_id: int, user_id: int, limit: int = 10) -> List[MMBotUserMatchStats]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotUserMatchStats)
                .where(
                    MMBotUserMatchStats.guild_id == guild_id,
                    MMBotUserMatchStats.user_id == user_id,
                    MMBotUserMatchStats.abandoned == False)
                .order_by(desc(MMBotUserMatchStats.timestamp))
                .limit(limit))
            return result.scalars().all()

    @log_db_operation
    async def get_match_stats_in_period(self, guild_id: int, user_id: int, start_date: datetime, end_date: datetime) -> List[MMBotUserMatchStats]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotUserMatchStats)
                .where(
                    MMBotUserMatchStats.guild_id == guild_id,
                    MMBotUserMatchStats.user_id == user_id,
                    MMBotUserMatchStats.abandoned == False,
                    MMBotUserMatchStats.timestamp.between(start_date, end_date))
                .order_by(MMBotUserMatchStats.timestamp))
            return result.scalars().all()

    @log_db_operation
    async def get_avg_stats_last_n_games(self, guild_id: int, user_id: int, n: int = 10) -> Dict[str, float] | None:
        async with self._session_maker() as session:
            subquery = select(MMBotUserMatchStats).where(
                MMBotUserMatchStats.guild_id == guild_id,
                MMBotUserMatchStats.user_id == user_id,
                MMBotUserMatchStats.abandoned == False
            ).order_by(desc(MMBotUserMatchStats.timestamp)).limit(n).subquery()

            result = await session.execute(
                select(
                    func.avg(subquery.c.kills).label('avg_kills'),
                    func.avg(subquery.c.deaths).label('avg_deaths'),
                    func.avg(subquery.c.assists).label('avg_assists'),
                    func.avg(subquery.c.score).label('avg_score'),
                    func.avg(subquery.c.mmr_change).label('avg_mmr_change')))
            row = result.first()
            if row:
                return {
                    'avg_kills': float(row.avg_kills) if row.avg_kills else None,
                    'avg_deaths': float(row.avg_deaths) if row.avg_deaths else None,
                    'avg_assists': float(row.avg_assists) if row.avg_assists else None,
                    'avg_score': float(row.avg_score) if row.avg_score else None,
                    'avg_mmr_change': float(row.avg_mmr_change) if row.avg_mmr_change else None }
            return None

    @log_db_operation
    async def get_last_match_mmr_impact(self, guild_id: int, user_id: int) -> Tuple[float, float] | None:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotUserMatchStats.mmr_before, MMBotUserMatchStats.mmr_change)
                .where(
                    MMBotUserMatchStats.guild_id == guild_id,
                    MMBotUserMatchStats.user_id == user_id)
                .order_by(desc(MMBotUserMatchStats.timestamp))
                .limit(1))
            last_match = result.first()
            if last_match:
                return last_match.mmr_before, last_match.mmr_change
            return None
    
    @log_db_operation
    async def get_last_n_match_stats(self, guild_id: int, user_id: int, n: int) -> List[MMBotUserMatchStats]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotUserMatchStats)
                .where(
                    MMBotUserMatchStats.guild_id == guild_id,
                    MMBotUserMatchStats.user_id == user_id,
                    MMBotUserMatchStats.abandoned == False)
                .order_by(desc(MMBotUserMatchStats.timestamp))
                .limit(n))
            return list(reversed(result.scalars().all()))
    
    @log_db_operation
    async def get_performance_by_time(self, guild_id: int, user_id: int) -> List[Dict[str, Any]]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(
                    func.extract('hour', MMBotUserMatchStats.timestamp).label('hour'),
                    func.avg(MMBotUserMatchStats.kills).label('avg_kills'),
                    func.avg(MMBotUserMatchStats.deaths).label('avg_deaths'),
                    func.avg(MMBotUserMatchStats.assists).label('avg_assists'),
                    func.avg(MMBotUserMatchStats.score).label('avg_score'),
                    func.avg(MMBotUserMatchStats.mmr_change).label('avg_mmr_change'),
                    func.count(MMBotUserMatchStats.id).label('games_played'))
                .where(
                    MMBotUserMatchStats.guild_id == guild_id,
                    MMBotUserMatchStats.user_id == user_id,
                    MMBotUserMatchStats.abandoned == False)
                .group_by(func.extract('hour', MMBotUserMatchStats.timestamp))
                .order_by(func.extract('hour', MMBotUserMatchStats.timestamp)))
            return [dict(row) for row in result]

    @log_db_operation
    async def get_last_match_stats(self, guild_id: int) -> List[MMBotUserMatchStats]:
        async with self._session_maker() as session:
            subquery = select(func.max(MMBotMatches.id)).where(MMBotMatches.complete == True).scalar_subquery()
            result = await session.execute(
                select(MMBotUserMatchStats)
                .join(MMBotMatches, MMBotUserMatchStats.match_id == MMBotMatches.id)
                .where(
                    MMBotUserMatchStats.guild_id == guild_id,
                    MMBotMatches.id == subquery))
            return result.scalars().all()
    
    @log_db_operation
    async def get_user_played_games(self, user_id: int, guild_id: int | None = None) -> int:
        async with self._session_maker() as session:
            query = select(func.count(MMBotUserMatchStats.id)).where(
                MMBotUserMatchStats.user_id == user_id,
                MMBotUserMatchStats.abandoned == False)

            if guild_id is not None:
                query = query.where(MMBotUserMatchStats.guild_id == guild_id)

            result = await session.execute(query)
            return result.scalar_one()
    
    @log_db_operation
    async def get_user_games(self, user_id: int, guild_id: int | None = None) -> List[MMBotUserMatchStats]:
        async with self._session_maker() as session:
            query = select(MMBotUserMatchStats).where(
                MMBotUserMatchStats.user_id == user_id,
                MMBotUserMatchStats.abandoned == False)

            if guild_id is not None:
                query = query.where(MMBotUserMatchStats.guild_id == guild_id)

            result = await session.execute(query)
            return result.scalars().all()

    @log_db_operation
    async def get_users_played_games(self, user_ids: List[int], guild_id: int | None = None) -> Dict[int, int]:
        async with self._session_maker() as session:
            query = (
                select(
                    MMBotUserMatchStats.user_id,
                    func.count(MMBotUserMatchStats.id).label('games_played'))
                .where(
                    MMBotUserMatchStats.user_id.in_(user_ids),
                    MMBotUserMatchStats.abandoned == False)
                .group_by(MMBotUserMatchStats.user_id))

            if guild_id is not None:
                query = query.where(MMBotUserMatchStats.guild_id == guild_id)

            result = await session.execute(query)
            played_games = {row.user_id: row.games_played for row in result}
            
            return { user_id: played_games.get(user_id, 0) for user_id in user_ids }


#######################
# USER NOTIFICARTIONS #
#######################

    @log_db_operation
    async def set_user_notification(self, guild_id: int, user_id: int, count: int=0, expiry: int | None=None, one_time: bool=False) -> None:
        async with self._session_maker() as session:
            if count == 0:
                stmt = delete(MMBotUserNotifications).where(
                        MMBotUserNotifications.guild_id == guild_id,
                        MMBotUserNotifications.user_id == user_id)
            else:
                stmt = insert(MMBotUserNotifications).values(
                    guild_id=guild_id, 
                    user_id=user_id, 
                    queue_count=count, 
                    expiry=expiry,
                    one_time=one_time).on_conflict_do_update(
                        index_elements=[key.name for key in inspect(MMBotUserNotifications).primary_key], set_={
                            'queue_count': count,
                            'expiry': expiry,
                            'one_time': one_time
                        })
            await session.execute(stmt)
            await session.commit()
    
    @log_db_operation
    async def delete_user_notifications(self, guild_id: int, user_ids: List[int]) -> None:
        async with self._session_maker() as session:
            await session.execute(
                delete(MMBotUserNotifications)
                .where(
                    MMBotUserNotifications.guild_id == guild_id,
                    MMBotUserNotifications.user_id.in_(user_ids)))
            await session.commit()
    
    @log_db_operation
    async def get_user_notifications(self, guild_id: int) -> Dict[int, Dict[str, Any]]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotUserNotifications)
                .where(MMBotUserNotifications.guild_id == guild_id)
            )
            return {
                cast(int, notification.user_id): {
                    'queue_count': notification.queue_count,
                    'expiry': notification.expiry,
                    'one_time': notification.one_time
                }
                for notification in result.scalars()
            }

##############
# MODERATION #
##############

    @log_db_operation
    async def upsert_warning(self, 
        guild_id: int, 
        user_id: int, 
        message: str = None, 
        match_id: int = None, 
        warn_type: Warn = Warn.WARNING, 
        moderator_id: int = None,
        identifier: int = None
    ) -> int:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotWarnedUsers)
                .where(MMBotWarnedUsers.id == identifier))
            existing_warning = result.scalar_one_or_none()

            if existing_warning:
                values = {}
                if message: values['message'] = message
                if match_id: values['match_id'] = match_id
                if warn_type: values['type'] = warn_type
                if moderator_id: values['moderator_id'] = moderator_id

                result = await session.execute(
                    update(MMBotWarnedUsers)
                    .where(MMBotWarnedUsers.id == existing_warning.id)
                    .values(**values)
                    .returning(MMBotWarnedUsers.id))
                warning_id = result.scalar_one()
            else:
                new_warning = MMBotWarnedUsers(
                    guild_id=guild_id,
                    user_id=user_id,
                    match_id=match_id,
                    message=message,
                    type=warn_type,
                    moderator_id=moderator_id)
                session.add(new_warning)
                await session.flush()
                warning_id = new_warning.id

            await session.commit()
            return warning_id

    @log_db_operation
    async def get_user_warnings(self, guild_id: int, user_id: int, warn_filters: List[Warn] | None = None) -> List[MMBotWarnedUsers]:
        async with self._session_maker() as session:
            query = (select(MMBotWarnedUsers)
                .where(
                    MMBotWarnedUsers.guild_id == guild_id,
                    MMBotWarnedUsers.user_id == user_id,
                    MMBotWarnedUsers.ignored == False))
            if warn_filters:
                query = query.where(MMBotWarnedUsers.type.in_(warn_filters))
            result = await session.execute(query)
            return result.scalars().all()

    @log_db_operation
    async def get_warning(self, warning_id: int) -> MMBotWarnedUsers:
        async with self._session_maker() as session:
            result = await session.execute(select(MMBotWarnedUsers).where(MMBotWarnedUsers.id == warning_id))
            return result.scalar_one_or_none()

    @log_db_operation
    async def get_muted(self, muted_id: int) -> MMBotMutedUsers:
        async with self._session_maker() as session:
            result = await session.execute(select(MMBotMutedUsers).where(MMBotMutedUsers.id == muted_id))
            return result.scalar_one_or_none()

    @log_db_operation
    async def get_user_mutes(self, guild_id: int, user_id: int) -> List[MMBotMutedUsers]:
        async with self._session_maker() as session:
            query = (select(MMBotMutedUsers)
                .where(
                    MMBotMutedUsers.guild_id == guild_id,
                    MMBotMutedUsers.user_id == user_id,
                    MMBotMutedUsers.active == True,
                    MMBotMutedUsers.ignored == False))
            result = await session.execute(query)
            return result.scalars().all()

    @log_db_operation
    async def get_mutes(self, guild_id: int) -> List[Dict[str, Any]]:
        async with self._session_maker() as session:
            latest_mutes = (
                select(MMBotMutedUsers.user_id,
                    func.max(MMBotMutedUsers.timestamp).label('latest_timestamp'))
                .where(MMBotMutedUsers.guild_id == guild_id)
                .group_by(MMBotMutedUsers.user_id)
                .subquery())

            query = (
                select(MMBotMutedUsers)
                .join(latest_mutes, and_(
                    MMBotMutedUsers.user_id == latest_mutes.c.user_id,
                    MMBotMutedUsers.timestamp == latest_mutes.c.latest_timestamp))
                .where(
                    MMBotMutedUsers.guild_id == guild_id,
                    MMBotMutedUsers.active == True,
                    MMBotMutedUsers.ignored == False,
                    or_(
                        MMBotMutedUsers.duration.is_(None),
                        MMBotMutedUsers.timestamp + func.cast(concat(MMBotMutedUsers.duration, ' SECONDS'), INTERVAL) > func.now())))

            result = await session.execute(query)
            mutes = result.scalars().all()

            return {
                mute.user_id: {
                    "id": mute.id,
                    "moderator_id": mute.moderator_id,
                    "reason": mute.message,
                    "duration": mute.duration,
                    "timestamp": mute.timestamp,
                    "expiry": (mute.timestamp + timedelta(seconds=mute.duration)) if mute.duration else None
            } for mute in mutes }
    
    @log_db_operation
    async def get_user_mute_history(self, guild_id: int, user_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        async with self._session_maker() as session:
            query = (
                select(MMBotMutedUsers)
                .where(
                    MMBotMutedUsers.guild_id == guild_id,
                    MMBotMutedUsers.user_id == user_id,
                    MMBotMutedUsers.ignored == False)
                .order_by(desc(MMBotMutedUsers.timestamp)))
            
            query = query.offset(offset).limit(limit)

            result = await session.execute(query)
            mutes = result.scalars().all()

            return [{
                "id": mute.id,
                "moderator_id": mute.moderator_id,
                "reason": mute.message,
                "duration": mute.duration,
                "timestamp": mute.timestamp,
                "active": mute.active,
                "ignored": mute.ignored,
                "expiry": (mute.timestamp + timedelta(seconds=mute.duration)) if mute.duration else None
            } for mute in mutes]

    @log_db_operation
    async def add_mute(self, guild_id: int, user_id: int, moderator_id: int, duration: int | None, reason: str) -> int:
        async with self._session_maker() as session:
            async with session.begin():
                await session.execute(
                    update(MMBotMutedUsers)
                    .where(
                        MMBotMutedUsers.guild_id == guild_id,
                        MMBotMutedUsers.user_id == user_id,
                        MMBotMutedUsers.ignored == False,
                        or_(
                            MMBotMutedUsers.duration.is_(None),
                            MMBotMutedUsers.timestamp + func.cast(concat(MMBotMutedUsers.duration, ' SECONDS'), INTERVAL) > func.now()))
                    .values(active=False))

                new_mute = MMBotMutedUsers(
                    guild_id=guild_id,
                    user_id=user_id,
                    moderator_id=moderator_id,
                    duration=duration,
                    message=reason,
                    ignored=False,
                    timestamp=func.now())
                session.add(new_mute)
                await session.flush()
                mute_id = new_mute.id

            await session.commit()
            return mute_id
    
    @log_db_operation
    async def update_mute(self, 
        guild_id: int | None = None, 
        user_id: int | None = None, 
        mute_id: int | None = None, 
        duration: int | None = None, 
        reason: str | None = None, 
        active: bool | None = None,
        ignored: bool | None = None
    ):
        async with self._session_maker() as session:
            async with session.begin():
                values = {}
                if duration is not None:
                    values["duration"] = duration
                if reason is not None:
                    values["message"] = reason
                if active is not None:
                    values["active"] = active
                if ignored is not None:
                    values["ignored"] = ignored

                query = select(MMBotMutedUsers)
                
                if mute_id:
                    query = query.where(MMBotMutedUsers.id == mute_id)
                elif guild_id and user_id:
                    query = query.where(
                        MMBotMutedUsers.guild_id == guild_id,
                        MMBotMutedUsers.user_id == user_id)

                query = query.order_by(desc(MMBotMutedUsers.timestamp)).limit(1)
                
                result = await session.execute(query)
                mute = result.scalar_one_or_none()

                for key, value in values.items():
                    setattr(mute, key, value)
                await session.commit()

    @log_db_operation
    async def get_punctuality_ratio(self, guild_id: int, user_id: int) -> float:
        async with self._session_maker() as session:
            late_warnings_count = await session.execute(
                select(func.count(MMBotWarnedUsers.id))
                .where(
                    MMBotWarnedUsers.guild_id == guild_id,
                    MMBotWarnedUsers.user_id == user_id,
                    MMBotWarnedUsers.type == Warn.LATE,
                    MMBotWarnedUsers.ignored == False))
            late_warnings = late_warnings_count.scalar_one()

            games_played = await session.execute(
                select(MMBotUserSummaryStats.games)
                .where(
                    MMBotUserSummaryStats.guild_id == guild_id,
                    MMBotUserSummaryStats.user_id == user_id))
            total_games = games_played.scalar_one()

            if total_games == 0:
                return 1.0
            return 1 - (late_warnings / total_games)

    @log_db_operation
    async def get_late_stats(self, guild_id: int, user_id: int) -> Dict[str, Any]:
        async with self._session_maker() as session:
            late_warnings = await session.execute(
                select(MMBotWarnedUsers)
                .where(
                    MMBotWarnedUsers.guild_id == guild_id,
                    MMBotWarnedUsers.user_id == user_id,
                    MMBotWarnedUsers.type == Warn.LATE,
                    MMBotWarnedUsers.ignored == False)
                .order_by(MMBotWarnedUsers.timestamp))
            late_warnings = late_warnings.scalars().all()

            user_games = await self.get_user_games(user_id, guild_id)
            user_games.sort(key=lambda x: x.timestamp)
            total_games = len(user_games)
            total_late_warnings = len(late_warnings)

            if total_games == 0:
                return {
                    "rate": 0.0,
                    "total_games": 0,
                    "total_lates": 0,
                    "total_late_time": 0,
                    "games_between": {
                        "average": None, "median": None, "std_dev": None,
                        "q1": None, "q3": None, "min": None, "max": None
                    },
                    "late_durations": {
                        "average": None, "median": None, "std_dev": None,
                        "q1": None, "q3": None, "min": None, "max": None
                    }
                }

            games_between_warnings = []
            late_durations = []
            last_warning_index = -1
            total_late_time = 0
            for warning in late_warnings:
                warning_index = next((i for i, game in enumerate(user_games) if game.timestamp > warning.timestamp), total_games)
                games_between = warning_index - last_warning_index - 1
                if games_between > 0:
                    games_between_warnings.append(games_between)
                last_warning_index = warning_index
                
                late_time = extract_late_time(warning.message)
                late_durations.append(late_time)
                total_late_time += late_time

            def calculate_stats(data):
                if not data:
                    return {
                        "average": None, "median": None, "std_dev": None,
                        "q1": None, "q3": None, "min": None, "max": None
                    }
                sorted_data = sorted(data)
                return {
                    "average": mean(data),
                    "median": median(data),
                    "std_dev": stdev(data) if len(data) > 1 else None,
                    "q1": sorted_data[len(sorted_data)//4],
                    "q3": sorted_data[3*len(sorted_data)//4],
                    "min": min(data),
                    "max": max(data)
                }

            return {
                "rate": total_late_warnings / total_games if total_games > 0 else 0,
                "total_games": total_games,
                "total_lates": total_late_warnings,
                "total_late_time": total_late_time,
                "games_between": calculate_stats(games_between_warnings),
                "late_durations": calculate_stats(late_durations)
            }

    @log_db_operation
    async def get_late_rankings(self, guild_id: int, limit: int = 100, offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
        async with self._session_maker() as session:
            late_warnings = (
                select(MMBotWarnedUsers.user_id,
                    func.count(MMBotWarnedUsers.id).label('late_count'),
                    func.array_agg(MMBotWarnedUsers.message).label('late_messages'))
                .where(MMBotWarnedUsers.guild_id == guild_id,
                    MMBotWarnedUsers.type == Warn.LATE,
                    MMBotWarnedUsers.ignored == False)
                .group_by(MMBotWarnedUsers.user_id)
                .subquery())

            query = (
                select(MMBotUserSummaryStats.user_id,
                    MMBotUserSummaryStats.games,
                    late_warnings.c.late_count,
                    late_warnings.c.late_messages)
                .join(late_warnings, MMBotUserSummaryStats.user_id == late_warnings.c.user_id)
                .where(MMBotUserSummaryStats.guild_id == guild_id,
                    MMBotUserSummaryStats.games > 0,
                    late_warnings.c.late_count > 0)
                .order_by(desc(late_warnings.c.late_count)))

            count_query = select(func.count()).select_from(query.subquery())
            total_count = await session.execute(count_query)
            total_count = total_count.scalar_one()

            query = query.offset(offset).limit(limit)

            result = await session.execute(query)
            rankings = []
            for row in result:
                total_late_time = sum(extract_late_time(message) for message in row.late_messages)
                rankings.append({
                    "user_id": row.user_id,
                    "games": row.games,
                    "late_count": row.late_count,
                    "total_late_time": total_late_time,
                    "late_rate": row.late_count / row.games
                })

            return rankings, total_count