from enum import IntEnum, auto

import asyncio
from pavlov import PavlovRCON


class PavlovState(IntEnum):
    NOT_STARTED   = auto()
    INITIALIZING  = auto()
    RUNNING       = auto()
    ENDED         = auto()


class Pavlov:
    def __init__(self, loop):
        self.state: PavlovState = PavlovState.NOT_STARTED
        self._conn: PavlovRCON = PavlovRCON("127.0.0.1", 9104, "password")
        loop.create_task(self.match_state())
    
    async def match_state(self):
        self.state = PavlovState.INITIALIZING
        while True:
            data = await self._conn.send("ServerInfo")
            if not data:
                break
            self.state = PavlovState.RUNNING
            await asyncio.sleep(1)
            
        self.state = PavlovState.ENDED