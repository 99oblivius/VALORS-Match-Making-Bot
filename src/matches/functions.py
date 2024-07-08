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

import random
from typing import List

from config import BASE_MMR_CHANGE, STARTING_MMR
from utils.models import MMBotMaps, MMBotUserMapPicks, Side


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
    kills = player_stats.get('kills', 0)
    deaths = player_stats.get('deaths', 0)
    assists = player_stats.get('assists', 0)
    
    base_change = BASE_MMR_CHANGE
    if abandoned: base_change = BASE_MMR_CHANGE * 2  # Double penalty for abandoning

    s = 400
    closeness_ratio = 4/9

    kd_rate = BASE_MMR_CHANGE / 5 * ((kills+assists/5) - deaths) / 10

    r_ab = ally_team_avg_mmr - enemy_team_avg_mmr
    pr_a = 1 / (1 + pow(10, -r_ab/s))

    closeness = closeness_ratio + (abs(ally_team_score - enemy_team_score) / 10) * (1-closeness_ratio)

    new_r = base_change * (int(win) - pr_a)
    new_r *= closeness
    new_r += kd_rate
    return new_r


