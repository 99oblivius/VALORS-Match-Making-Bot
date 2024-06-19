import threading
from .matches import Match

def make_match(loop, bot, guild_id, match_id):
    match = Match(bot, guild_id, match_id)
    loop.create_task(match.run())

def load_ongoing_matches(loop, bot, guild_id, matches):
    for match in matches:
        match = Match(bot, guild_id, match.id, match.state)
        loop.create_task(match.run())
