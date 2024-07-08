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
from itertools import combinations
from typing import List, Tuple

import numpy as np

from utils.models import MMBotUsers


def preparing_user_data(users: List[MMBotUsers]) -> Tuple[int, np.ndarray, np.ndarray]:
    num_players = len(users)
    mmr_results = np.array([user.summary_stats.mmr for user in users], dtype=np.int32)
    rankings = np.argsort(mmr_results)[::-1]
    return num_players, mmr_results, rankings

def calculate_team_combinations(n: int, m: int) -> Tuple[int, np.ndarray]:
    team_combinations_list = np.array(list(combinations(range(n), m)), dtype=np.int32)
    return len(team_combinations_list), team_combinations_list

def rank_teams_based_on_mmr(team_combinations_list: np.ndarray, mmr_results: np.ndarray) -> Tuple[np.ndarray, float]:
    team_mmr_avgs = np.mean(mmr_results[team_combinations_list], axis=1)
    average_team_mmr = np.mean(team_mmr_avgs)
    team_mmr_deviations = np.abs(team_mmr_avgs - average_team_mmr)
    team_mmr_rankings = np.argsort(team_mmr_deviations)
    ranked_team_combinations_list = team_combinations_list[team_mmr_rankings]
    return ranked_team_combinations_list, float(average_team_mmr)

def find_single_pair(ranked_team_combinations: np.ndarray, n: int, initial_percent: float=2.0) -> Tuple[np.ndarray, np.ndarray]:
    increment_percent = 2
    min_options = 5

    while True:
        idx = int(n * (initial_percent / 100))
        top_team_combinations = ranked_team_combinations[:idx]
        possible_pairs = [
            (top_team_combinations[i], top_team_combinations[j])
            for i in range(len(top_team_combinations))
            for j in range(i + 1, len(top_team_combinations))
            if not set(top_team_combinations[i]) & set(top_team_combinations[j])
        ]

        if len(possible_pairs) >= min_options or initial_percent > 100:
            return random.choice(possible_pairs)

        initial_percent += increment_percent

def calculate_average_mmr(team: np.ndarray, mmr_results: np.ndarray) -> float:
    return float(np.mean(mmr_results[team]))

def get_teams(users: List[MMBotUsers]) -> Tuple[List[int], List[int], float, float]:
    team_size = len(users) // 2
    num_players, mmr_results, _ = preparing_user_data(users)
    num_team_combinations, team_combinations_list = calculate_team_combinations(num_players, team_size)
    ranked_team_combinations, _ = rank_teams_based_on_mmr(team_combinations_list, mmr_results)
    team1, team2 = find_single_pair(ranked_team_combinations, num_team_combinations)
    team1_mmr = calculate_average_mmr(team1, mmr_results)
    team2_mmr = calculate_average_mmr(team2, mmr_results)
    team1_users = [users[t1].user_id for t1 in team1]
    team2_users = [users[t2].user_id for t2 in team2]
    return team1_users, team2_users, team1_mmr, team2_mmr