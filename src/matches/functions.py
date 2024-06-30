import random
from typing import List
from utils.models import MMBotMaps, MMBotUserMapPicks

def get_preferred_bans(maps: List[MMBotMaps], bans: List[str], total_bans: int=2) -> List[str]:
    map_options = { m.map: 0 for m in maps }
    for ban in bans: map_options[ban] += 1

    ban_votes = [(k, v) for k, v in sorted(map_options.items(), key=lambda item: item[1], reverse=True)]

    bans = []
    while len(bans) < total_bans and ban_votes:
        votes = ban_votes[0][1]
        i = 0
        while i < len(ban_votes) and ban_votes[i][1] == votes:
            i += 1
        chosen_ban = random.choice(ban_votes[0:i])
        bans.append(chosen_ban[0])
        ban_votes.remove(chosen_ban)
    
    order_map = {m.map: n for n, m in enumerate(maps)}
    bans.sort(key=lambda x: order_map[x])
    
    return bans

def get_preferred_map(maps: List[MMBotMaps], picks: List[MMBotUserMapPicks]) -> MMBotMaps:
    random.shuffle(picks)
    map_dict = { m.map: m for m in maps }
    pick_options = { m.map: 0 for m in maps }
    for pick in picks:
        if pick.map in pick_options:
            pick_options[pick.map] += 1
    most_picked_map_name = sorted(pick_options.items(), key=lambda x: x[1], reverse=True)[0][0]
    return map_dict[most_picked_map_name]

from utils.models import Side
def get_preferred_side(sides: List[Side], picks: List[str]) -> str:
    random.shuffle(picks)
    pick_options = { s: 0 for s in sides }
    for pick in picks: pick_options[pick] += 1
    pick = sorted(pick_options.items(), key=lambda x: x[1], reverse=True)[0][0]
    return pick