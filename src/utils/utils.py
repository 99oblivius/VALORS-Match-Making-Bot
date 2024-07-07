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
    
    cooldown_end = last_abandon
    if count == 0:
        return 0
    elif count == 1:
        cooldown_end += timedelta(hours=2)
    elif count == 2:
        cooldown_end += timedelta(hours=6)
    elif count == 3:
        cooldown_end += timedelta(days=1)
    else:
        cooldown_end += timedelta(days=3)

    cooldown_seconds = (cooldown_end - datetime.now(timezone.utc)).total_seconds()
    return max(0, int(cooldown_seconds))



ANSI_TARGET_COLORS = {
    0x4E5057: "30",
    0xC34139: "31",
    0x88972E: "32",
    # 0xAE8B2D: "33",
    0x4689CC: "34",
    0xC24480: "35",
    # 0x519F98: "36",
    # 0xFFFFFF: "37",

    # 0x0F2C37: "40;30",
    0x9A4D2D: "41;30",
    0x4D6169: "42:30",
    0x586B74: "43:30",
    0x6F8085: "44:30",
    0x5C65A5: "45:30",
    0x79888B: "46:30",
    0xD5D5C9: "47:30",

    0x302E35: "40;31",
    # 0xBE502C: "41;31",
    0x716468: "42;31",
    0x7A6F74: "43;31",
    0x928384: "44;31",
    0x7F67A3: "45;31",
    0xA28B89: "46;31",
    0xF3D5C6: "47;31",

    0x274033: "40;32",
    0xB0632A: "41;32",
    0x667664: "42;32",
    0x6F7F6E: "43;32",
    # 0x86947E: "44;32",
    0x7279A0: "45;32",
    # 0x929E87: "46;32",
    0xE5E3C1: "47;32",

    0x2D3C33: "40;33",
    0xB95F29: "41;33",
    0x6C7266: "42;33",
    0x767D71: "43;33",
    # 0x8E9180: "44;33",
    0x7A76A0: "45;33",
    0x9B9C88: "46;33",
    0xEADEBC: "47;33",

    0x1A3F56: "40;34",
    0xA35E4A: "41;34",
    0x577285: "42;34",
    # 0x607D93: "43;34",
    0x7690A2: "44;34",
    0x6476C1: "45;34",
    0x839BAA: "46;34",
    0xD7DFDF: "47;34",

    0x342F45: "40;35",
    # 0xBD503B: "41;35",
    0x6F6475: "42;35",
    0x7A6F81: "43;35",
    0x928291: "44;35",
    0x7F67B0: "45;35",
    0xA08998: "46;35",
    0xF0D3D1: "47;35",

    0x1B4048: "40;36",
    0xA5633F: "41;36",
    0x59777B: "42;36",
    0x648186: "43;36",
    # 0x799596: "44;36",
    0x667BB5: "45;36",
    0x88A09F: "46;36",
    0xDAE4D5: "47;36",

    0x384D53: "40;37",
    0xC5714B: "41;37",
    0x788487: "42;37",
    0x859194: "43;37",
    0x9CA5A4: "44;37",
    0x8487C2: "45;37",
    0xA8B0AC: "46;37",
    # 0xF8F3E2: "47;37",
}