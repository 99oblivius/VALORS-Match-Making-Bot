import logging as log

import asyncpg

from config import *

class Database:
    def __init__(self, loop) -> None:
        self._loop = loop
        self._pool = None
    
    async def start(self, url: str):
        self._pool = await asyncpg.create_pool(url)
        log.info("[Database] Pool created!")
