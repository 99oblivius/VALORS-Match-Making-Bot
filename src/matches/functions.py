import random
from typing import List

def get_preferred_bans(maps: List[str], bans: List[str], total_bans: int=2) -> List[str]:
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
    
    order_map = {m: n for n, m in enumerate(maps)}
    n = len(bans)
    for i in range(n):
        swapped = False
        for j in range(0, n - i - 1):
            if order_map[bans[j]] > order_map[bans[j + 1]]:
                bans[j], bans[j + 1] = bans[j + 1], bans[j]
                swapped = True
        if not swapped: break
    
    return bans