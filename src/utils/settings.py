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

from collections import OrderedDict
from asyncio import Lock
from typing import TYPE_CHECKING, overload

if TYPE_CHECKING:
    from main import Bot

from utils.models import BotSettings


class SettingsCache:
    def __init__(self, bot: "Bot", max_size: int = 100):
        self.bot = bot
        self._cache: OrderedDict[int, BotSettings] = OrderedDict()
        self._lock = Lock()
        self.max_size = max_size
    
    async def _update_cache(self, guild_id: int):
        settings = await self.bot.store.get_settings(guild_id)
        self._cache[guild_id] = settings or BotSettings(guild_id=guild_id)
    
    def _set_cache(self, guild_id: int, settings: BotSettings):
        if len(self._cache) >= self.max_size:
            self._cache.popitem(last=False)
        self._cache[guild_id] = settings
        self._cache.move_to_end(guild_id)
    
    def _get_cache(self, guild_id: int) -> BotSettings | None:
        if guild_id in self._cache:
            self._cache.move_to_end(guild_id)
            return self._cache[guild_id]
        return None
    
    @overload
    async def __call__(self, guild_id: int) -> BotSettings:
        """Getter for Settings Cache

        Args:
            guild_id (int): guild_id

        Returns:
            BotSettings: Can be unpopulated in case the DB responds with None
        """
        ...
    
    @overload
    async def __call__(self, guild_id: int, **kwargs) -> BotSettings:
        """Setter for settings Cache

        Args:
            guild_id (int): guild_id
            **kwargs (str, Any): TableArguments

        Returns:
            BotSettings: THe populated settings
        """
    
    async def __call__(self, guild_id: int, **kwargs) -> "BotSettings":
        if not kwargs:
            cached = self._get_cache(guild_id)
            if cached is None:
                await self._update_cache(guild_id)
                return self._cache[guild_id]
            return cached
        else:
            async with self._lock:
                await self.bot.store.upsert(BotSettings, guild_id=guild_id, **kwargs)
                cached = self._get_cache(guild_id) or BotSettings(guild_id=guild_id)
                for key, value in kwargs.items():
                    setattr(cached, key, value)
                self._set_cache(guild_id, cached)
                return cached
