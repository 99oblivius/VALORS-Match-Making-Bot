from typing import List
from utils.models import MMBotUserMatchStats

import plotly.graph_objects as go
from config import VALORS_THEME1, VALORS_THEME1_1, VALORS_THEME1_2, VALORS_THEME2

def create_stat_graph(graph_type: str, match_stats: List[MMBotUserMatchStats]) -> go.Figure:
    x = [stat.timestamp for stat in match_stats]
    
    if graph_type == "mmr_time":
        y = [stat.mmr_before + stat.mmr_change for stat in match_stats]
        title = "MMR over time"
        y_title = "MMR"
        fig = go.Figure(go.Scatter(x=x, y=y, mode='lines+markers', line=dict(color=f'#{hex(VALORS_THEME1)[2:]}')))
    
    elif graph_type == "kills_game":
        y = [stat.kills for stat in match_stats]
        title = "Kills per game"
        y_title = "Kills"
        fig = go.Figure(go.Scatter(x=x, y=y, mode='markers', marker=dict(color=f'#{hex(VALORS_THEME2)[2:]})')))
    
    elif graph_type == "kd_time":
        y = [stat.kills / stat.deaths if stat.deaths > 0 else stat.kills for stat in match_stats]
        title = "K/D ratio over time"
        y_title = "K/D Ratio"
        fig = go.Figure(go.Scatter(x=x, y=y, mode='lines+markers', line=dict(color=f'#{hex(VALORS_THEME1_1)[2:]}')))
    
    elif graph_type == "winrate_time":
        wins = [1 if stat.win else 0 for stat in match_stats]
        y = [sum(wins[:i+1]) / (i+1) for i in range(len(wins))]
        title = "Win rate over time"
        y_title = "Win Rate"
        fig = go.Figure(go.Scatter(x=x, y=y, mode='lines', line=dict(color=f'#{hex(VALORS_THEME1_2)[2:]}')))
    
    elif graph_type == "score_game":
        y = [stat.score for stat in match_stats]
        title = "Score per game"
        y_title = "Score"
        fig = go.Figure(go.Scatter(x=x, y=y, mode='markers', marker=dict(color=f'#{hex(VALORS_THEME2)[2:]}')))

    fig.update_layout(
        title=title,
        xaxis_title="Date",
        yaxis_title=y_title,
        template="plotly_dark",
        font=dict(family="Arial", size=14, color="white"),
        plot_bgcolor=f'#{hex(VALORS_THEME1_2)[2:]}',
        paper_bgcolor=f'#{hex(VALORS_THEME1_2)[2:]}')
    return fig