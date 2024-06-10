from logging import log

from typing import Dict
from asyncio import AbstractEventLoop
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, DeclarativeMeta
from sqlalchemy.future import select
from sqlalchemy import Column, inspect
from config import DATABASE_URL

from .schema import *

class Database:
    def __init__(self, loop: AbstractEventLoop) -> None:
        self._loop = loop
        self._engine: AsyncEngine = create_async_engine(
            DATABASE_URL, 
            echo=True, 
            future=True)
        self._session_maker: sessionmaker = sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False)

    async def setup_database(self, tables: Dict[str, Dict[str, str]]) -> None:
        async with self._engine.begin() as conn:
            for table_name, columns in tables.items():
                inspector = inspect(conn)
                if not inspector.has_table(table_name):
                    table = self._create_table_class(table_name, columns)
                    await conn.run_sync(table.__table__.create)
                    log.info(f"[Database] Table '{table_name}' created.")
                else:
                    table = self._create_table_class(table_name, columns)
                    await self._check_and_add_new_columns(conn, table_name, table, columns)

    def _create_table_class(self, table_name: str, columns: Dict[str, str]) -> DeclarativeMeta:
        attrs = {'__tablename__': table_name, '__table_args__': {'extend_existing': True}}
        for col, typ in columns.items():
            attrs[col] = Column(col, eval(typ))
        return type(table_name, (Base,), attrs)

    async def get_settings(self, guild_id: int) -> BotSettings | None:
        async with self._session_maker() as session:
            result = await session.execute(
                select(BotSettings).where(BotSettings.guild_id == guild_id).limit(1))
            return result.scalars().first()
