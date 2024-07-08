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

from typing import Dict, List

import nextcord
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from config import VALORS_THEME1, VALORS_THEME1_1, VALORS_THEME1_2, VALORS_THEME2
from utils.models import MMBotRanks, MMBotUserMatchStats


def create_graph(graph_type: str, match_stats: List[MMBotUserMatchStats], ranks: List[Dict[nextcord.Role, MMBotRanks]]) -> go.Figure:
    df = pd.DataFrame([vars(stat) for stat in match_stats])
    df['game_number'] = range(1, len(df) + 1)
    df['cumulative_wins'] = df['win'].cumsum()
    df['win_rate'] = df['cumulative_wins'] / df['game_number']
    df['kd_ratio'] = df['kills'] / df['deaths'].replace(0, 1)

    theme_color1 = f'#{hex(VALORS_THEME1)[2:]}'
    theme_color1_1 = f'#{hex(VALORS_THEME1_1)[2:]}'
    theme_color1_2 = f'#{hex(VALORS_THEME1_2)[2:]}'
    theme_color2 = f'#{hex(VALORS_THEME2)[2:]}'

    if graph_type == "mmr_game":
        mmr_values = df['mmr_before'] + df['mmr_change']
        fig = go.Figure(go.Scatter(
            x=df['game_number'], 
            y=mmr_values, 
            mode='lines', 
            line=dict(color=theme_color1),
            name='MMR'
        ))

        y_min = mmr_values.min()
        y_max = mmr_values.max()
        y_range = y_max - y_min
        y_padding = y_range * 0.1

        if ranks:
            for role, rank in sorted(ranks.items(), key=lambda x: x[1].mmr_threshold):
                if y_min - y_padding <= rank.mmr_threshold <= y_max + y_padding:
                    color = f'rgb({role.color.r},{role.color.g},{role.color.b})'
                    fig.add_shape(
                        type="line",
                        x0=0,
                        y0=rank.mmr_threshold,
                        x1=len(df),
                        y1=rank.mmr_threshold,
                        line=dict(color=color, width=3, dash="dash"),
                    )

                    fig.add_annotation(
                        x=len(df),
                        y=rank.mmr_threshold,
                        xref="x",
                        yref="y",
                        text=f"{role.name}",
                        showarrow=False,
                        xanchor="right",
                        yanchor="top",
                        xshift=-5,
                        yshift=-2,
                        font=dict(size=12, color=color),
                    )

        fig.update_layout(
            xaxis_title="Games", 
            yaxis_title="MMR", 
            showlegend=False, 
            yaxis=dict(range=[y_min - y_padding, y_max + y_padding])
        )

    elif graph_type == "kills_game":
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df['game_number'], 
            y=df['kills'], 
            mode='markers', 
            marker=dict(color=theme_color2)
        ))
        fig.add_trace(go.Scatter(
            x=df['game_number'], 
            y=df['kills'].rolling(window=10).mean(), 
            mode='lines', 
            line=dict(color=theme_color1)
        ))
        fig.update_layout(xaxis_title="Games", yaxis_title="Kills", showlegend=False)

    elif graph_type == "kd_game":
        fig = go.Figure(go.Scatter(
            x=df['game_number'], 
            y=df['kd_ratio'], 
            mode='markers',
            marker=dict(color=theme_color2)
        ))
        fig.add_trace(go.Scatter(
            x=df['game_number'], 
            y=df['kd_ratio'].rolling(window=10).mean(), 
            mode='lines', 
            line=dict(color=theme_color1)
        ))
        fig.update_layout(xaxis_title="Games", yaxis_title="K/D Ratio", showlegend=False)

    elif graph_type == "winrate_time":
        fig = go.Figure(go.Scatter(
            x=df['timestamp'], 
            y=df['win_rate'], 
            mode='lines', 
            line=dict(color=theme_color1)
        ))
        fig.update_layout(
            title="Win rate over time", 
            xaxis_title="Date", 
            yaxis_title="Win Rate", 
            yaxis_range=[0,1], 
            yaxis_tickformat='.0%', 
            showlegend=False)

    elif graph_type == "score_game":
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df['game_number'], 
            y=df['score'], 
            mode='markers', 
            marker=dict(color=theme_color2)
        ))
        fig.add_trace(go.Scatter(
            x=df['game_number'], 
            y=df['score'].rolling(window=10).mean(), 
            mode='lines', 
            line=dict(color=theme_color1)
        ))
        fig.update_layout(xaxis_title="Games", yaxis_title="Score", showlegend=False)

    elif graph_type == "performance_overview":
        fig = make_subplots(
            rows=2, 
            cols=2, 
            subplot_titles=("MMR", "K/D Ratio", "Win Rate", "Score"),
            vertical_spacing=0.1,
            horizontal_spacing=0.05)
        
        fig.add_trace(go.Scatter(x=df['game_number'], y=df['mmr_before'] + df['mmr_change'], mode='lines', line=dict(color=theme_color1)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['game_number'], y=df['kd_ratio'], mode='lines', line=dict(color=theme_color2)), row=1, col=2)
        fig.add_trace(go.Scatter(x=df['game_number'], y=df['win_rate'], mode='lines', line=dict(color=theme_color1_1)), row=2, col=1)
        fig.add_trace(go.Scatter(x=df['game_number'], y=df['score'], mode='lines', line=dict(color=theme_color1_2)), row=2, col=2)
        
        fig.update_layout(height=800, title_text="Overview", showlegend=False)
        fig.update_xaxes(title_text="Game Number")
        fig.update_yaxes(title_text="Value")

    if graph_type == "performance_overview":
        fig.update_layout(height=700)
    else: fig.update_layout(height=400)

    fig.update_layout(
        margin=dict(l=0,r=0,t=0,b=0),
        template="plotly_dark",
        font=dict(family="Century Gothic", size=14, color="white"),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)')
    fig.update_xaxes(
        title=dict(
            font=dict(size=16),
            standoff=6))
    fig.update_yaxes(
        title=dict(
            font=dict(size=16),
            standoff=6))

    return fig

