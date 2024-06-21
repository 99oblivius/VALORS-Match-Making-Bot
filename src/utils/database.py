import logging
from logging import getLogger
from typing import List, Tuple, Dict
from asyncio import AbstractEventLoop
from sqlalchemy import inspect, delete, update, func, or_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine, AsyncSession
from sqlalchemy.ext.declarative import DeclarativeMeta
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select
from config import DATABASE_URL

from .models import (
    BotSettings, 
    BotRegions,
    MMBotQueueUsers,
    MMBotMatchUsers,
    MMBotMatches,
    MMBotUsers,
    MMBotUserBans,
    MMBotMaps,
    Phase,
    Team,
    MMBotUserMapPicks,
    MMBotUserSidePicks
)

from matches import MatchState

logging.getLogger('sqlalchemy').disabled = True

log = getLogger(__name__)

class Database:
    def __init__(self) -> None:
        self._engine: AsyncEngine = create_async_engine(DATABASE_URL, echo=True)
        self._session_maker: sessionmaker = sessionmaker(bind=self._engine, class_=AsyncSession, expire_on_commit=False)
    
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

###########
# GET BOT #
###########
    async def get_settings(self, guild_id: int) -> BotSettings | None:
        async with self._session_maker() as session:
            result = await session.execute(
                select(BotSettings)
                .where(BotSettings.guild_id == guild_id))
            return result.scalars().first()
    
    async def get_regions(self, guild_id: int) -> List[BotRegions] | None:
        async with self._session_maker() as session:
            result = await session.execute(
                select(BotRegions)
                .where(BotRegions.guild_id == guild_id))
            return result.scalars().all()

    async def get_regions(self, guild_id: int) -> List[BotRegions]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(BotRegions)
                .where(BotRegions.guild_id == guild_id)
                .order_by(BotRegions.index))
            return result.scalars().all()


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
    
    async def get_users(self, guild_id: int) -> List[MMBotUsers]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotUsers)
                .where(MMBotUsers.guild_id == guild_id))
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
                select(MMBotMatchUsers.team)
                .where(
                    MMBotMatchUsers.guild_id == guild_id,
                    MMBotMatchUsers.user_id == user_id,
                    MMBotMatchUsers.match_id == match_id))
            return result.scalars().first()

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
                insert_stmt = insert(MMBotMatchUsers).values(match_users)
                await session.execute(insert_stmt)
                await session.commit()
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
    
    async def get_players(self, match_id: int) -> List[MMBotMatchUsers]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotMatchUsers)
                .where(MMBotMatchUsers.match_id == match_id))
            return result.scalars().all()
    
    async def get_accepted_players(self, match_id: int) -> int:
        async with self._session_maker() as session:
            stmt = select(func.count(MMBotMatchUsers.user_id)).where(
                MMBotMatchUsers.match_id == match_id,
                MMBotMatchUsers.accepted == True)
            result = await session.execute(stmt)
            return result.scalars().first()
    
    async def is_user_in_match(self, user_id: int) -> bool:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotMatchUsers)
                .join(MMBotMatches, MMBotMatchUsers.match_id == MMBotMatches.id)
                .filter(
                    MMBotMatchUsers.user_id == user_id,
                    MMBotMatches.complete == False))
            match_user = result.scalars().first()
            return match_user is not None
    
    async def set_players_team(self, match_id: int, user_teams: Dict[Team, List[int]]):
        async with self._session_maker() as session:
            async with session.begin():
                for team, user_ids in user_teams.items():
                    await session.execute(
                        update(MMBotMatchUsers)
                        .where(
                            MMBotMatchUsers.match_id == match_id,
                            MMBotMatchUsers.user_id.in_(user_ids))
                        .values(team=team))

    async def remove_match_and_players(self, match_id: int) -> None:
        async with self._session_maker() as session:
            async with session.begin():
                await session.execute(
                    delete(MMBotMatchUsers)
                    .where(MMBotMatchUsers.match_id == match_id))
                await session.execute(
                    delete(MMBotMatches)
                    .where(MMBotMatches.id == match_id))
                await session.commit()


##############
# MATCH BANS #
##############
    async def set_map_bans(self, match_id: int, bans: list, team: bool):
        async with self._session_maker() as session:
            if team == Team.A:
                await session.execute(
                    update(MMBotMatches)
                    .where(MMBotMatches.id == match_id)
                    .values(a_bans=bans))
                await session.commit()
            elif team == Team.B:
                await session.execute(
                    update(MMBotMatches)
                    .where(MMBotMatches.id == match_id)
                    .values(b_bans=bans))
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
                select(MMBotUserBans)
                .where(
                    MMBotUserBans.match_id == match_id,
                    MMBotUserBans.phase == phase))
            return [ban.map for ban in result.scalars().all()]
    
    async def get_bans(self, match_id: int, team: Team | None = None) -> List[str]:
        async with self._session_maker() as session:
            if team == Team.A:
                result = await session.execute(
                    select(MMBotMatches.a_bans)
                    .where(MMBotMatches.id == match_id))
                bans = result.scalars().first()
                return bans or []
            elif team == Team.B:
                result = await session.execute(
                    select(MMBotMatches.b_bans)
                    .where(MMBotMatches.id == match_id))
                bans = result.scalars().first()
                return bans or []
            else:
                result = await session.execute(
                    select(MMBotMatches.a_bans, MMBotMatches.b_bans)
                    .where(MMBotMatches.id == match_id))
                row = result.fetchone()
                if row:
                    a_bans, b_bans = row
                    return (a_bans or []) + (b_bans or [])
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
    async def set_map_pick(self, match_id: int, picked_map: str):
        async with self._session_maker() as session:
            await session.execute(
                update(MMBotMatches)
                .where(MMBotMatches.id == match_id)
                .values(a_picked_map=picked_map))
            await session.commit()
    
    async def get_map_vote_count(self, guild_id: int, match_id: int) -> List[Tuple[str, int]]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(
                    MMBotMaps.map,
                    func.count(MMBotUserMapPicks.map).label('pick_count'))
                .outerjoin(MMBotUserMapPicks, 
                    (MMBotUserMapPicks.map == MMBotMaps.map) & 
                    (MMBotUserMapPicks.match_id == match_id))
                .where(MMBotMaps.guild_id == guild_id)
                .where(MMBotMaps.active == True)
                .group_by(MMBotMaps.map, MMBotMaps.order)
                .order_by(MMBotMaps.order))
            pick_counts = result.all()
            return [(row.map, row.pick_count) for row in pick_counts]

    async def get_map_votes(self, match_id: int) -> List[str]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotUserMapPicks.map)
                .where(
                    MMBotUserBans.match_id == match_id))
            return result.scalars().all()

    async def get_user_map_pick(self, match_id: int, user_id: int) -> List[str]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotUserMapPicks.map)
                .where(
                    MMBotUserMapPicks.match_id == match_id,
                    MMBotUserMapPicks.user_id == user_id))
            return result.scalars().all()

########
# MAPS #
########
    async def set_maps(self, guild_id: int, maps: List[Tuple[str, str]]):
        data = [{"guild_id": guild_id, "map": m[0], "media": m[1], "active": True, "order": n} for n, m in enumerate(maps)]
        
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
                        "media": insert_stmt.excluded.media})
                await session.execute(update_stmt)

    async def get_maps(self, guild_id: int) -> List[str]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotMaps)
                .where(
                    MMBotMaps.guild_id == guild_id,
                    MMBotMaps.active == True)
                .order_by(MMBotMaps.order))
            return result.scalars().all()
    