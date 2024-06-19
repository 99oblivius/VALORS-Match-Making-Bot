from typing import List

from utils.models import MMBotMatchUsers

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

def format_mm_attendance(users: List[MMBotMatchUsers]):
    return "\n".join([f"{'🟢' if user.accepted else '🔴'} <@{user.user_id}>" for user in users])

def format_team(team: bool) -> str:
    return 'B' if team else 'A'

def shifted_window(l: List, phase: int=0, range: int=1) -> List:
    l = l + l[:range - 1]
    return l[phase:phase + range]