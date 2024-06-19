from typing import List, Tuple
from itertools import combinations
import numpy as np
import random

from utils.models import MMBotUsers

def preparing_user_data(users: List[MMBotUsers]) -> Tuple[int, int, List[int], np.ndarray, np.ndarray]:
    num_players = len(users)
    mmr_results = np.array([user.mmr for user in users], dtype=np.intc)
    rankings = np.argsort(mmr_results)[::-1]
    return num_players, mmr_results, rankings

def calculate_team_combinations(n: int, m: int) -> Tuple[int, np.ndarray]:
    team_combinations_list = np.array(list(combinations(range(n), m)))
    return len(team_combinations_list), team_combinations_list

def rank_teams_based_on_mmr(team_combinations_list: np.ndarray, mmr_results: np.ndarray) -> Tuple[np.ndarray, float]:
    team_mmr_avgs = np.mean(mmr_results[team_combinations_list], axis=1)
    average_team_mmr = np.mean(team_mmr_avgs)
    team_mmr_deviations = np.abs(team_mmr_avgs - average_team_mmr)
    team_mmr_rankings = np.argsort(team_mmr_deviations)
    ranked_team_combinations_list = team_combinations_list[team_mmr_rankings]
    return ranked_team_combinations_list, average_team_mmr

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

        if len(possible_pairs) >= min_options:
            return random.choice(possible_pairs)

        initial_percent += increment_percent

def calculate_average_mmr(team: np.ndarray, mmr_results: np.ndarray) -> float:
    return np.mean(mmr_results[team])

def get_teams(users: List[MMBotUsers]) -> Tuple[list, list, float, float]:
    team_size = len(users) // 2
    num_players, mmr_results, _ = preparing_user_data(users)
    num_team_combinations, team_combinations_list = calculate_team_combinations(num_players, team_size)
    ranked_team_combinations, _ = rank_teams_based_on_mmr(team_combinations_list, mmr_results)
    team1, team2 = find_single_pair(ranked_team_combinations, num_team_combinations)
    team1_mmr = calculate_average_mmr(team1, mmr_results)
    team2_mmr = calculate_average_mmr(team2, mmr_results)
    return list(team1), list(team2), team1_mmr, team2_mmr
