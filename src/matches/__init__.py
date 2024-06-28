import asyncio

from .match import Match
from .match_states import MatchState

active_matches = {}
running_matches = {}

def make_match(loop, bot, guild_id, match_id):
    match = Match(bot, guild_id, match_id)
    task = loop.create_task(match.run())
    task.add_done_callback(lambda t: running_matches.pop(match.match_id, None))

    active_matches[match.match_id] = match
    running_matches[match.match_id] = task

def load_ongoing_matches(loop, bot, guild_id, matches):
    for match in matches:
        match = Match(bot, guild_id, match.id, match.state)
        task = loop.create_task(match.run())
        task.add_done_callback(lambda t: running_matches.pop(match.match_id, None))
        
        active_matches[match.match_id] = match
        running_matches[match.match_id] = task

async def cleanup_match(loop, match_id) -> bool:
    task = running_matches.pop(match_id, None)
    match = active_matches.get(match_id)
    if not task or not match: return False
    
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    await match.change_state(MatchState.CLEANUP)

    task = loop.create_task(match.run())
    task.add_done_callback(lambda t: running_matches.pop(match.match_id, None))
    running_matches[match.match_id] = task
    return True