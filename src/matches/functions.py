import random
from typing import List

import numpy as np
from itertools import combinations, compress
import collections
import copy

from utils.models import MMBotUsers

def get_preferred_bans(maps: List[str], bans: List[str], total_bans: int=2) -> List[str]:
    map_options = { m: 0 for m in maps }
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
    
    order_map = {m: n for n, m in enumerate(maps)}
    bans.sort(key=lambda x: order_map[x])
    
    return bans
