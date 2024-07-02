import random
from typing import List
from utils.models import MMBotMaps, MMBotUserMapPicks
from utils.models import Side
from config import STARTING_MMR, BASE_MMR_CHANGE

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

def get_preferred_side(sides: List[Side], picks: List[str]) -> str:
    random.shuffle(picks)
    pick_options = { s: 0 for s in sides }
    for pick in picks: pick_options[pick] += 1
    pick = sorted(pick_options.items(), key=lambda x: x[1], reverse=True)[0][0]
    return pick

def calculate_mmr_change(
    player_stats: dict,
    ally_team_score: int=0,
    enemy_team_score: int=0,
    ally_team_avg_mmr: int=STARTING_MMR,
    enemy_team_avg_mmr: int=STARTING_MMR,
    win: bool=False,
    abandoned: bool=False
) -> int:
    kills = player_stats['kills']
    deaths = player_stats['deaths']
    assists = player_stats['assists']
    
    if abandoned: base_change = -BASE_MMR_CHANGE * 2  # Double penalty for abandoning
    elif win: base_change = BASE_MMR_CHANGE
    else: base_change = -BASE_MMR_CHANGE

    s = 400
    closeness_ratio = 4/9

    kd_rate = BASE_MMR_CHANGE / 5 * ((kills+assists/2) - deaths) / 10

    r_ab = ally_team_avg_mmr - enemy_team_avg_mmr
    pr_a = 1 / (1 + pow(10, -r_ab/s))

    closeness = closeness_ratio + (abs(ally_team_score - enemy_team_score) / 10) * (1-closeness_ratio)

    new_r = base_change * (int(win) - pr_a)
    new_r *= closeness
    new_r += kd_rate
    return new_r


