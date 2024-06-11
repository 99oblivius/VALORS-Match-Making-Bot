from logging import getLogger
from typing import Optional
from asyncio import AbstractEventLoop
from sqlalchemy import inspect, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine, AsyncSession
from sqlalchemy.ext.declarative import DeclarativeMeta
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select
from config import DATABASE_URL

from .models import (
    Base, 
    BotSettings, 
    MMBotQueueUsers,
)

log = getLogger(__name__)

class Database:
    def __init__(self, loop: AbstractEventLoop) -> None:
        self._loop = loop
        self._engine: AsyncEngine = create_async_engine(DATABASE_URL, echo=True)
        self._session_maker: sessionmaker = sessionmaker(bind=self._engine, class_=AsyncSession, expire_on_commit=False)

    async def push(self, table: DeclarativeMeta, **data) -> None:
        async with self._session_maker() as session:
            stmt = pg_insert(table).values(**data)
            primary_keys = [key.name for key in inspect(table).primary_key]
            on_conflict_stmt = stmt.on_conflict_do_update(index_elements=primary_keys, set_=data)
            await session.execute(on_conflict_stmt)
            await session.commit()
    
    async def remove(self, table: DeclarativeMeta, **conditions) -> None:
        async with self._session_maker() as session:
            stmt = delete(table).where(*[getattr(table, key) == value for key, value in conditions.items()])
            await session.execute(stmt)
            await session.commit()
    
    async def get_settings(self, guild_id: int) -> Optional[BotSettings]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(BotSettings).where(BotSettings.guild_id == guild_id).limit(1))
            return result.scalars().first()
    
    async def get_queue_users(self, channel_id: int):
        async with self._session_maker() as session:
            result = await session.execute(select(MMBotQueueUsers).where(MMBotQueueUsers.queue_channel == channel_id))
            return result.scalars().all()
