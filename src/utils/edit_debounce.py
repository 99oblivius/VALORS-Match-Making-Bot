import asyncio
from typing import Callable, Dict

from nextcord import Interaction, HTTPException

from utils.logger import Logger as log


class DebounceInterMsg:
    def __init__(self):
        self.tasks: Dict[str, asyncio.Task] = {}
    
    async def __call__(self, callback: Callable, interaction: Interaction, *args, _delay: float=1.5):
        if not interaction.message: return
        _id = f"{interaction.message.id}"
        
        async def edit(wait: float=0.):
            try:
                if wait:
                    if not interaction.response.is_done:
                        await interaction.response.defer()
                    await asyncio.sleep(wait)
                    await callback(interaction, *args)
                else:
                    await callback(interaction, *args)
                    await asyncio.sleep(wait)
            except asyncio.CancelledError:
                log.debug(f"Cancelled {_id}")
                pass
            except HTTPException: pass
            except Exception as e:
                print(f"Error in debounce for {callback.__name__}: {repr(e)}")
            finally:
                if _id in self.tasks and self.tasks[_id] == asyncio.current_task():
                    del self.tasks[_id]
                    log.debug(f"Deleted {_id}")

        log.debug(f"Tasks: {self.tasks.keys()}")
        if _id in self.tasks:
            self.tasks[_id].cancel()
            self.tasks[_id] = asyncio.create_task(edit(_delay))
        else:
            self.tasks[_id] = asyncio.create_task(edit())
