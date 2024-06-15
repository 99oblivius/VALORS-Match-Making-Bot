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
        result.append(f"{value} {name}")
    return ' '.join(result) if result else "0 seconds"

from typing import List
def format_mm_attendence(user_ids: List[int], accepted: List[int]=[]):
    return "\n".join([f"{'🟢' if user_id in accepted else '🔴'} <@{user_id}>" for user_id in user_ids])