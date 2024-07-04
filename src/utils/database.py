from typing import List, Tuple, Dict, Any
from datetime import timedelta, datetime
from sqlalchemy import inspect, delete, update, func, or_, text, desc
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine, AsyncSession
from sqlalchemy.ext.declarative import DeclarativeMeta
from sqlalchemy.orm import sessionmaker, joinedload, selectinload
from sqlalchemy.future import select
from config import DATABASE_URL

from .models import *
from matches import MatchState


class Database:
    def __init__(self) -> None:
        self._engine: AsyncEngine = create_async_engine(DATABASE_URL, echo=True)
        self._session_maker: sessionmaker = sessionmaker(bind=self._engine, class_=AsyncSession, expire_on_commit=False)
    
    def __del__(self):
        self._engine.dispose()
    
###########
# CLASSIC #
###########
    async def upsert(self, table: DeclarativeMeta, **data) -> None:
        async with self._session_maker() as session:
            await session.execute(
                insert(table)
                .values(**data)
                .on_conflict_do_update(index_elements=[key.name for key in inspect(table).primary_key], set_=data))
            await session.commit()
    
    async def update(self, table: DeclarativeMeta, **data) -> None:
        async with self._session_maker() as session:
            await session.execute(update(table), [data])
            await session.commit()

    async def insert(self, table: DeclarativeMeta, **data) -> None:
        async with self._session_maker() as session:
            await session.execute(
                insert(table)
                .values(**data))
            await session.commit()
    
    async def remove(self, table: DeclarativeMeta, **conditions) -> None:
        async with self._session_maker() as session:
            stmt = delete(table).where(*[getattr(table, key) == value for key, value in conditions.items()])
            await session.execute(stmt)
            await session.commit()

################
# RCON SERVERS #
################
    async def set_serveraddr(self, match_id: int, serveraddr: str) -> None:
        async with self._session_maker() as session:
            await session.execute(
                update(MMBotMatches)
                .where(MMBotMatches.id == match_id)
                .values(serveraddr=serveraddr))
            await session.commit()
        
    async def get_serveraddr(self, match_id: int) -> None:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotMatches.serveraddr)
                .where(MMBotMatches.id == match_id))
            return result.scalars().first()
        
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
            return result.scalars().all()
    
    async def get_server(self, host: str, port: int) -> RconServers:
        async with self._session_maker() as session:
            result = await session.execute(
                select(RconServers)
                .where(
                    RconServers.host == host, 
                    RconServers.port == port))
            return result.scalars().first()
    
    async def add_server(self, host: str, port: int, password: str, region: str) -> None:
        async with self._session_maker() as session:
            session.add(RconServers(host=host, port=port, password=password, region=region))
            await session.commit()

    async def remove_server(self, host: str, port: int) -> None:
        async with self._session_maker() as session:
            await session.execute(
                delete(RconServers)
                .where(
                    RconServers.host == host,
                    RconServers.port == port))
            await session.commit()

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

###########
# GET BOT #
###########
    async def get_settings(self, guild_id: int) -> BotSettings | None:
        async with self._session_maker() as session:
            result = await session.execute(
                select(BotSettings)
                .where(BotSettings.guild_id == guild_id))
            return result.scalars().first()
    
    async def get_regions(self, guild_id: int) -> List[BotRegions]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(BotRegions)
                .where(BotRegions.guild_id == guild_id)
                .order_by(BotRegions.index))
            return result.scalars().all()

    async def get_ranks(self, guild_id: int) -> List[MMBotRanks]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotRanks)
                .where(MMBotRanks.guild_id == guild_id)
                .order_by(MMBotRanks.mmr_threshold))
            return result.scalars().all()
    
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

########
# USER #
########
    async def get_user(self, guild_id: int, user_id: int) -> MMBotUsers:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotUsers)
                .where(
                    MMBotUsers.guild_id == guild_id, 
                    MMBotUsers.user_id == user_id))
            return result.scalars().first()
    
    async def get_user_platforms(self, guild_id: int, user_id: int) -> List[UserPlatformMappings]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(UserPlatformMappings)
                .where(
                    UserPlatformMappings.guild_id == guild_id, 
                    UserPlatformMappings.user_id == user_id)
                .order_by(UserPlatformMappings.platform))
            return result.scalars().all()
    
    async def get_users_summary_stats(self, guild_id: int, user_ids: List[int]) -> Dict[int, MMBotUserSummaryStats]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotUserSummaryStats)
                .where(
                    MMBotUserSummaryStats.guild_id == guild_id,
                    MMBotUserSummaryStats.user_id.in_(user_ids)))
            stats_list = result.scalars().all()
            return {stat.user_id: stat for stat in stats_list}
    
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
    
    async def get_users(self, guild_id: int, user_ids: List[int] = None) -> List[MMBotUsers]:
        async with self._session_maker() as session:
            query = select(MMBotUsers).options(selectinload(MMBotUsers.summary_stats)).where(MMBotUsers.guild_id == guild_id)
            if user_ids:
                query = query.where(MMBotUsers.user_id.in_(user_ids))
            result = await session.execute(query)
            return result.scalars().all()
    
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

    async def null_user_region(self, guild_id: int, label: str):
        async with self._session_maker() as session:
            await session.execute(
                update(MMBotUsers)
                .where(MMBotUsers.guild_id == guild_id, MMBotUsers.region == label)
                .values(region=None))
            await session.commit()

    async def get_user_team(self, guild_id: int, user_id: int, match_id: int) -> Team:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotMatchPlayers.team)
                .where(
                    MMBotMatchPlayers.guild_id == guild_id,
                    MMBotMatchPlayers.user_id == user_id,
                    MMBotMatchPlayers.match_id == match_id))
            return result.scalars().first()


############
# ABANDONS #
############
    async def add_abandon(self, guild_id: int, user_id: int):
        async with self._session_maker() as session:
            session.add(MMBotUserAbandons(
                guild_id=guild_id,
                user_id=user_id))
            await session.commit()
    
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

    async def set_match_abandons(self, match_id: int, abandoned_user_ids: List[int]) -> None:
        async with self._session_maker() as session:
            await session.execute(
                update(MMBotUserMatchStats)
                .where(MMBotUserMatchStats.match_id == match_id)
                .values(abandoned=True))
            await session.execute(
                update(MMBotMatches)
                .where(MMBotMatches.id == match_id)
                .values(abandoned_by=abandoned_user_ids))
            await session.commit()

#########
# QUEUE #
#########
    async def get_queue_users(self, channel_id: int) -> List[MMBotQueueUsers]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotQueueUsers)
                .where(
                    MMBotQueueUsers.queue_channel == channel_id, 
                    MMBotQueueUsers.in_queue == True))
            return result.scalars().all()
    
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
                    maps_range=settings.mm_maps_range, 
                    maps_phase=settings.mm_maps_phase)
                session.add(match)
                await session.flush()

                result = await session.execute(
                    select(MMBotMatches)
                    .where(
                        MMBotMatches.queue_channel == channel_id,
                        MMBotMatches.complete == False))
                new_match = result.scalars().first()


                match_users = [
                    { 'guild_id': user.guild_id, 'user_id': user.user_id, 'match_id': new_match.id }
                    for user in queue_users
                ]
                insert_stmt = insert(MMBotMatchPlayers).values(match_users)
                await session.execute(insert_stmt)
                return new_match.id
    
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
    async def get_ongoing_matches(self) -> List[MMBotMatches]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotMatches)
                .where(MMBotMatches.complete == False))
            return result.scalars().all()
    
    async def save_match_state(self, match_id: int, state: MatchState):
        async with self._session_maker() as session:
            await session.execute(
                update(MMBotMatches)
                .where(MMBotMatches.id == match_id)
                .values(state=state))
            await session.commit()
    
    async def load_match_state(self, match_id: int) -> MatchState:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotMatches.state)
                .where(MMBotMatches.id == match_id))
            return MatchState(result.scalars().first())
    
    async def get_match(self, match_id: int) -> MMBotMatches:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotMatches)
                .where(MMBotMatches.id == match_id))
            return result.scalars().first()
    
    async def get_thread_match(self, thread_id: int) -> MMBotMatches:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotMatches)
                .where(or_(
                    MMBotMatches.match_thread == thread_id,
                    MMBotMatches.a_thread == thread_id,
                    MMBotMatches.b_thread == thread_id)))
            return result.scalars().first()

    async def get_players(self, match_id: int) -> List[MMBotMatchPlayers]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotMatchPlayers)
                .options(selectinload(MMBotMatchPlayers.user_platform_mappings))
                .where(MMBotMatchPlayers.match_id == match_id))
            return result.scalars().all()
    
    async def get_unaccepted_players(self, match_id: int) -> List[MMBotMatchPlayers]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotMatchPlayers)
                .where(
                    MMBotMatchPlayers.match_id == match_id, 
                    MMBotMatchPlayers.accepted == False))
            return result.scalars().all()
        
    async def get_player(self, match_id: int, user_id: int) -> MMBotMatchPlayers:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotMatchPlayers)
                .options(joinedload(MMBotMatchPlayers.user_platform_mappings))
                .where(MMBotMatchPlayers.match_id == match_id)
                .where(MMBotMatchPlayers.user_id == user_id))
            return result.scalars().first()
    
    async def get_accepted_players(self, match_id: int) -> int:
        async with self._session_maker() as session:
            stmt = select(func.count(MMBotMatchPlayers.user_id)).where(
                MMBotMatchPlayers.match_id == match_id,
                MMBotMatchPlayers.accepted == True)
            result = await session.execute(stmt)
            return result.scalars().first()
    
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
    async def set_map_bans(self, match_id: int, bans: list, team: Team):
        async with self._session_maker() as session:
            stmt = update(MMBotMatches).where(MMBotMatches.id == match_id)
            if team == Team.A:
                stmt = stmt.values(a_bans=bans)
            elif team == Team.B:
                stmt = stmt.values(b_bans=bans)
            await session.execute(stmt)
            await session.commit()

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
                .where(MMBotMaps.guild_id == guild_id)
                .where(MMBotMaps.active == True)
                .group_by(MMBotMaps.map, MMBotMaps.order)
                .order_by(MMBotMaps.order))
            ban_counts = result.all()
            return [(row.map, row.ban_count) for row in ban_counts]
    
    async def get_ban_votes(self, match_id: int, phase: Phase) -> List[str]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotUserBans.map)
                .where(
                    MMBotUserBans.match_id == match_id,
                    MMBotUserBans.phase == phase))
            return result.scalars().all()
    
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
    
    async def get_user_map_bans(self, match_id: int, user_id: int) -> List[str]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotUserBans.map)
                .where(
                    MMBotUserBans.match_id == match_id,
                    MMBotUserBans.user_id == user_id))
            return result.scalars().all()

###############
# MATCH PICKS #
###############
    async def get_map_vote_count(self, guild_id: int, match_id: int) -> List[Tuple[str, int]]:
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

    async def get_map_votes(self, match_id: int) -> List[MMBotUserMapPicks]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotUserMapPicks)
                .where(
                    MMBotUserMapPicks.match_id == match_id))
            return result.scalars().all()

    async def get_user_map_pick(self, match_id: int, user_id: int) -> List[str]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotUserMapPicks.map)
                .where(
                    MMBotUserMapPicks.match_id == match_id,
                    MMBotUserMapPicks.user_id == user_id))
            return result.scalars().all()

    async def get_match_map(self, match_id: int) -> MMBotMaps | None:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotMatches.map)
                .where(MMBotMatches.id == match_id))
            map_string = result.scalars().first()
            if not map_string:
                return None
            
            result = await session.execute(
                select(MMBotMaps)
                .where(MMBotMaps.map == map_string))
            map_object = result.scalars().first()
            return map_object

    async def get_match_sides(self, match_id: int) -> Tuple[Side | None, Side | None]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotMatches.b_side)
                .where(MMBotMatches.id == match_id))
            b_side = result.scalars().first()
            if b_side is None:
                return (None, None)
            
            a_side = Side.CT if b_side == Side.T else Side.T
            return (a_side, b_side)

########
# MAPS #
########
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

    async def get_maps(self, guild_id: int) -> List[MMBotMaps]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotMaps)
                .where(
                    MMBotMaps.guild_id == guild_id,
                    MMBotMaps.active == True)
                .order_by(MMBotMaps.order))
            return result.scalars().all()

##############
# SIDE PICKS #
##############
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
    
    async def get_side_votes(self, match_id: int) -> List[str]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotUserSidePicks.side)
                .where(MMBotUserSidePicks.match_id == match_id))
            return result.scalars().all()

    async def get_user_side_pick(self, match_id: int, user_id: int) -> List[str]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotUserSidePicks.side)
                .where(
                    MMBotUserSidePicks.match_id == match_id,
                    MMBotUserSidePicks.user_id == user_id))
            return result.scalars().all()

###############
# MATCH STATs #
###############
    async def get_user_summary_stats(self, guild_id: int, user_id: int) -> MMBotUserSummaryStats:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotUserSummaryStats)
                .where(
                    MMBotUserSummaryStats.guild_id == guild_id,
                    MMBotUserSummaryStats.user_id == user_id))
            return result.scalars().first()

    async def get_recent_match_stats(self, guild_id: int, user_id: int, limit: int = 10) -> List[MMBotUserMatchStats]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotUserMatchStats)
                .where(
                    MMBotUserMatchStats.guild_id == guild_id,
                    MMBotUserMatchStats.user_id == user_id)
                .order_by(desc(MMBotUserMatchStats.timestamp))
                .limit(limit))
            return result.scalars().all()

    async def get_match_stats_in_period(self, guild_id: int, user_id: int, start_date: datetime, end_date: datetime) -> List[MMBotUserMatchStats]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotUserMatchStats)
                .where(
                    MMBotUserMatchStats.guild_id == guild_id,
                    MMBotUserMatchStats.user_id == user_id,
                    MMBotUserMatchStats.timestamp.between(start_date, end_date))
                .order_by(MMBotUserMatchStats.timestamp))
            return result.scalars().all()

    async def get_avg_stats_last_n_games(self, guild_id: int, user_id: int, n: int = 10) -> Dict[str, float] | None:
        async with self._session_maker() as session:
            subquery = select(MMBotUserMatchStats).where(
                MMBotUserMatchStats.guild_id == guild_id,
                MMBotUserMatchStats.user_id == user_id
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
                    'avg_kills': row.avg_kills,
                    'avg_deaths': row.avg_deaths,
                    'avg_assists': row.avg_assists,
                    'avg_score': row.avg_score,
                    'avg_mmr_change': row.avg_mmr_change }
            return None

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
    
    async def get_last_n_match_stats(self, guild_id: int, user_id: int, n: int) -> List[MMBotUserMatchStats]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotUserMatchStats)
                .where(
                    MMBotUserMatchStats.guild_id == guild_id,
                    MMBotUserMatchStats.user_id == user_id)
                .order_by(desc(MMBotUserMatchStats.timestamp))
                .limit(n))
            return list(reversed(result.scalars().all()))
    
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
                    MMBotUserMatchStats.user_id == user_id)
                .group_by(func.extract('hour', MMBotUserMatchStats.timestamp))
                .order_by(func.extract('hour', MMBotUserMatchStats.timestamp)))
            return [dict(row) for row in result]