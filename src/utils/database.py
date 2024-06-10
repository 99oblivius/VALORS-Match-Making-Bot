from logging import getLogger
from typing import Dict, Optional
from asyncio import AbstractEventLoop
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select
from config import DATABASE_URL

from .models import Base, BotSettings

log = getLogger(__name__)

class Database:
    def __init__(self, loop: AbstractEventLoop) -> None:
        self._loop = loop
        self._engine: AsyncEngine = create_async_engine(DATABASE_URL, echo=True)
        self._session_maker: sessionmaker = sessionmaker(bind=self._engine, class_=AsyncSession, expire_on_commit=False)

    async def get_settings(self, guild_id: int) -> Optional[BotSettings]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(BotSettings).where(BotSettings.guild_id == guild_id).limit(1)
            )
            return result.scalars().first()

