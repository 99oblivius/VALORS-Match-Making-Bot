from typing import List
import uuid
from datetime import datetime, timedelta, timezone

from utils.models import MMBotMatchPlayers

def format_duration(seconds):
    intervals = (
        ('days', 86400),
        ('hours', 3600),
        ('minutes', 60),
        ('seconds', 1))
    result = []
    for name, count in intervals:
        value = seconds // count
        seconds -= value * count
        if value == 1: name = name.rstrip('s')
        if value != 0: result.append(f"{value} {name}")
    return ' '.join(result) if result else "0 seconds"

def format_mm_attendance(users: List[MMBotMatchPlayers]):
    return "\n".join([f"{'🟢' if user.accepted else '🔴'} <@{user.user_id}>" for user in users])

def format_team(team: bool) -> str:
    return 'B' if team else 'A'

def shifted_window(l: list, phase: int=0, range: int=1) -> list:
    l = l + l[:range - 1]
    return l[phase:phase + range]

def generate_auth_url(cache, guild_id: int, user_id: int, platform: str) -> str:
    token = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    cache.hmset(token, {'guild_id': guild_id, 'discord_uuid': user_id, 'expires_at': expires_at.isoformat(), 'platform': platform})
    cache.expire(token, 300)
    return f"https://valorsbotapi.oblivius.dev/auth/{platform}/{token}"

def abandon_cooldown(count: int, last_abandon: datetime | None=None) -> int:
    if last_abandon is None:
        last_abandon = datetime.now(timezone.utc)
    if count == 0:
        return 0
    elif count == 1:
        cooldown_end = last_abandon + timedelta(hours=2)
    elif count == 2:
        cooldown_end = last_abandon + timedelta(hours=6)
    elif count == 3:
        cooldown_end = last_abandon + timedelta(days=1)
    else:
        cooldown_end = last_abandon + timedelta(days=3)

    cooldown_seconds = (cooldown_end - datetime.now(timezone.utc)).total_seconds()
    return max(0, int(cooldown_seconds))