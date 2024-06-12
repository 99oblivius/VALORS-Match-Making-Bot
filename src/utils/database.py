from logging import getLogger
from typing import List
from asyncio import AbstractEventLoop
from sqlalchemy import inspect, delete, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine, AsyncSession
from sqlalchemy.ext.declarative import DeclarativeMeta
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select
from config import DATABASE_URL

from .models import (
    Base, 
    BotSettings, 
    BotRegions,
    MMBotQueueUsers,
    MMBotMatchUsers,
    MMBotMatches,
    MMBotUsers,
)

log = getLogger(__name__)

class Database:
    def __init__(self, loop: AbstractEventLoop) -> None:
        self._loop = loop
        self._engine: AsyncEngine = create_async_engine(DATABASE_URL, echo=True)
        self._session_maker: sessionmaker = sessionmaker(bind=self._engine, class_=AsyncSession, expire_on_commit=False)

    async def upsert(self, table: DeclarativeMeta, **data) -> None:
        async with self._session_maker() as session:
            await session.execute(
                insert(table)
                .values(**data)
                .on_conflict_do_update(index_elements=[key.name for key in inspect(table).primary_key], set_=data))
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
    
    async def get_settings(self, guild_id: int) -> BotSettings | None:
        async with self._session_maker() as session:
            result = await session.execute(
                select(BotSettings)
                .where(BotSettings.guild_id == guild_id)
                .limit(1))
            return result.scalars().first()
    
    async def get_regions(self, guild_id: int) -> BotRegions | None:
        async with self._session_maker() as session:
            result = await session.execute(
                select(BotRegions)
                .where(BotRegions.guild_id == guild_id))
            return result.scalars().all()
    
    async def get_queue_users(self, channel_id: int) -> MMBotQueueUsers:
        async with self._session_maker() as session:
            result = await session.execute(
                select(MMBotQueueUsers)
                .where(
                    MMBotQueueUsers.queue_channel == channel_id, 
                    MMBotQueueUsers.in_queue == True))
            return result.scalars().all()
    
    async def unqueue_add_match_users(self, channel_id: int):
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
                
                session.add(MMBotMatches(queue_channel=channel_id))
                await session.flush()
                result = await session.execute(
                    select(MMBotMatches)
                    .where(
                        MMBotMatches.queue_channel == channel_id,
                        MMBotMatches.complete == False))
                new_match = result.scalar_one()
                
                match_users = [
                    { 'guild_id': user.guild_id,
                      'user_id': user.user_id,
                      'match_id': new_match.id }
                    for user in queue_users
                ]
                insert_stmt = insert(MMBotMatchUsers).values(match_users)
                await session.execute(insert_stmt)
                await session.commit()
    
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

    async def get_regions(self, guild_id: int) -> List[BotRegions]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(BotRegions)
                .where(BotRegions.guild_id == guild_id))
            return result.scalars().all()

            