# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # 
# VALORS Match Making Bot is a discord based match making automation and management service #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # 
# 
# Copyright (C) 2024 99oblivius, <projects@oblivius.dev>
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

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
    
    if match.state > MatchState.MATCH_FIND_SERVER:
        await match.change_state(MatchState.MATCH_CLEANUP)
    else:
        await match.change_state(MatchState.CLEANUP)

    task = loop.create_task(match.run())
    task.add_done_callback(lambda t: running_matches.pop(match.match_id, None))
    running_matches[match.match_id] = task
    return True

def get_match(match_id) -> Match:
    return active_matches.get(match_id)