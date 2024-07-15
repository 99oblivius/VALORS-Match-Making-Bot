# VALORS Match Making Bot - Discord based match making automation and management service
# Copyright (C) 2024 99oblivius, <projects@oblivius.dev>
#
# This file is part of VALORS Match Making Bot.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

from typing import Dict, List, Any, Tuple
from math import floor
from datetime import datetime, timedelta

import nextcord
from nextcord import Embed, Guild, User, Member
import pandas as pd
import numpy as np
from scipy import stats
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from config import VALORS_THEME1, VALORS_THEME1_1, VALORS_THEME1_2, VALORS_THEME2
from utils.models import MMBotRanks, MMBotUserMatchStats
from utils.utils import get_rank_color, get_rank_role


def create_graph(graph_type: str, 
                 match_stats: List[MMBotUserMatchStats], 
                 ranks: List[Dict[nextcord.Role, MMBotRanks]] | None=None, 
                 preferences: Dict[str, Dict[str, int]] | None=None,
                 play_periods: List[Tuple[datetime, datetime]] | None=None) -> go.Figure:
    df = pd.DataFrame([vars(stat) for stat in match_stats])
    df['game_number'] = range(1, len(df) + 1)
    df['cumulative_wins'] = df['win'].cumsum()
    df['win_rate'] = df['cumulative_wins'] / df['game_number']
    df['kd_ratio'] = df['kills'] / df['deaths'].replace(0, 1)

    theme_color1 = f'#{hex(VALORS_THEME1)[2:]}'
    theme_color1_1 = f'#{hex(VALORS_THEME1_1)[2:]}'
    theme_color1_2 = f'#{hex(VALORS_THEME1_2)[2:]}'
    theme_color2 = f'#{hex(VALORS_THEME2)[2:]}'

    if graph_type == "activity_hours":
        hours = []
        for start, end in play_periods:
            duration = (end - start).total_seconds() / 3600
            mid_hour = (start.hour + start.minute / 60 + duration / 2) % 24
            hours.append(mid_hour)

        # Create circular KDE
        theta = np.linspace(0, 2*np.pi, 360)
        r = np.linspace(0.2, 1, 100)
        theta_grid, r_grid = np.meshgrid(theta, r)

        x = r_grid * np.cos(theta_grid)
        y = r_grid * np.sin(theta_grid)

        values = np.array([(np.cos(h*2*np.pi/24), np.sin(h*2*np.pi/24)) for h in hours])
        kernel = stats.gaussian_kde(values.T)
        intensity = kernel(np.vstack([x.ravel(), y.ravel()])).reshape(x.shape)

        # Normalize intensity
        intensity = (intensity - intensity.min()) / (intensity.max() - intensity.min())

        # Create the plot
        fig = go.Figure()

        # Add heatmap trace
        fig.add_trace(go.Barpolar(
            r=r,
            theta=np.degrees(theta),
            customdata=intensity.T,
            hovertemplate='Time: %{theta:.1f}°<br>Intensity: %{customdata:.2f}<extra></extra>',
            marker=dict(
                color=intensity.T,
                colorscale='Viridis',
                showscale=False
            ),
            name=''
        ))

        # Customize layout
        fig.update_layout(
            polar=dict(
                radialaxis=dict(visible=False, range=[0, 1]),
                angularaxis=dict(
                    tickvals=[0, 90, 180, 270],
                    ticktext=['0:00', '6:00', '12:00', '18:00'],
                    direction='clockwise',
                    rotation=90,
                )
            ),
            showlegend=False,
            title=dict(
                text='User Activity Density Map',
                font=dict(size=20)
            ),
            height=600,
            width=600,
        )
    
    elif graph_type == "pick_preferences":
        categories = ['Bans', 'Picks', 'Sides']
        data = []
        
        all_maps = set(preferences['bans'].keys()) | set(preferences['picks'].keys())
        for map_name in all_maps:
            data.append(go.Bar(
                name=map_name,
                x=categories[:2],
                y=[preferences['bans'].get(map_name, 0), preferences['picks'].get(map_name, 0)],
                text=[preferences['bans'].get(map_name, 0), preferences['picks'].get(map_name, 0)],
                textposition='auto'
            ))
        
        for side in preferences['sides']:
            data.append(go.Bar(
                name=side.name,
                x=[categories[2]],
                y=[preferences['sides'][side]],
                text=[preferences['sides'][side]],
                textposition='auto'
            ))
        
        fig = go.Figure(data=data)
        fig.update_layout(
            title="Pick Preferences",
            yaxis_title="Count",
            barmode='group',
            height=600,
            legend_title="Maps/Sides")
    
    elif graph_type == "mmr_game":
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
        
        fig.update_yaxes(title_text="MMR", row=1, col=1)
        fig.update_yaxes(title_text="K/D Ratio", row=1, col=2, side="right")
        fig.update_yaxes(title_text="Win Rate", row=2, col=1)
        fig.update_yaxes(title_text="Score", row=2, col=2, side="right")

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

def create_stats_embed(guild: Guild, user: User | Member, leaderboard_data, summary_data, avg_stats, recent_matches, ranks) -> Embed:
    ranked_players = 0
    ranked_position = None
    for player in leaderboard_data:
        if player['games'] > 0 and guild.get_member(player['user_id']):
            ranked_players += 1
        if player['user_id'] == user.id:
            ranked_position = ranked_players
    embed = Embed(title=f"[{ranked_position}/{ranked_players}] Stats for {user.display_name}", description=f"Currently in {get_rank_role(guild, ranks, summary_data.mmr).mention}", color=VALORS_THEME1)
    embed.set_thumbnail(url=user.avatar.url if user.avatar else user.default_avatar.url)

    embed.add_field(name="MMR", value=f"{summary_data.mmr:.2f}", inline=True)
    embed.add_field(name="Total Games", value=summary_data.games, inline=True)
    embed.add_field(name="Win Rate", value=f"{(summary_data.wins / summary_data.games * 100):.2f}%" if summary_data.games > 0 else "N/A", inline=True)
    embed.add_field(name="Total Kills", value=summary_data.total_kills, inline=True)
    embed.add_field(name="Total Deaths", value=summary_data.total_deaths, inline=True)
    embed.add_field(name="Total Assists", value=summary_data.total_assists, inline=True)
    embed.add_field(name="K/D Ratio", value=f"{(summary_data.total_kills / summary_data.total_deaths):.2f}" if summary_data.total_deaths > 0 else "N/A", inline=True)
    embed.add_field(name="Total Score", value=summary_data.total_score, inline=True)

    if avg_stats:
        embed.add_field(name="\u200b", value="Average Performance (Last 10 Games)", inline=False)
        embed.add_field(name="Kills", value=f"{f'{avg_stats['avg_kills']:.2f}' if avg_stats.get('avg_kills', None) else 'N/A'}", inline=True)
        embed.add_field(name="Deaths", value=f"{f'{avg_stats['avg_deaths']:.2f}' if avg_stats.get('avg_deaths', None) else 'N/A'}", inline=True)
        embed.add_field(name="Assists", value=f"{f'{avg_stats['avg_assists']:.2f}' if avg_stats.get('avg_assists', None) else 'N/A'}", inline=True)
        embed.add_field(name="Score", value=f"{f'{avg_stats['avg_score']:.2f}' if avg_stats.get('avg_score', None) else 'N/A'}", inline=True)
        embed.add_field(name="MMR Gain", value=f"{f'{avg_stats['avg_mmr_change']:.2f}' if avg_stats.get('avg_mmr_change', None) else 'N/A'}", inline=True)
    else:
        embed.add_field(name="Recent Performance", value="No recent matches found", inline=False)

    if recent_matches:
        recent_matches_str = "\n".join([f"{'W' if match.win else 'L'} | K: {match.kills} | D: {match.deaths} | A: {match.assists} | MMR: {f'{match.mmr_change:+.2f}' if match.mmr_change else "In-game"}" for match in recent_matches])
        embed.add_field(name="Recent Matches", value=f"```{recent_matches_str}```", inline=False)
    else:
        embed.add_field(name="Recent Matches", value="No recent matches found", inline=False)
    
    return embed

def create_leaderboard_embed(guild: Guild, leaderboard_data: List[Dict[str, Any]], last_mmr: Dict[int, int], ranks: List[MMBotRanks]) -> Embed:
    field_count = 0

    valid_scores = [player['avg_score'] for player in leaderboard_data if player['games'] > 0 and guild.get_member(player['user_id'])]
    avg_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0
    embed = Embed(title="Match Making Leaderboard", description=f"{len(valid_scores)} ranking players\nK/D/A and Score are mean averages")

    ranked_mmr = ((n, user_id) for n, (user_id, _) in enumerate(sorted(last_mmr.items(), key=lambda x: x[1], reverse=True), 1))
    previous_positions = { user_id: n for n, user_id in ranked_mmr if guild.get_member(user_id) }

    ranking_position = 0
    for player in leaderboard_data:
        if field_count > 25: break
        if player['games'] == 0: continue

        member = guild.get_member(player['user_id'])
        if member is None: continue
        
        ranking_position += 1

        previous_position = previous_positions.get(player['user_id'], None)
        if previous_position is None:               rank_change = "\u001b[35m·"
        elif ranking_position < previous_position:  rank_change = "\u001b[32m↑"
        elif ranking_position > previous_position:  rank_change = "\u001b[31m↓"
        else:                                       rank_change = "\u001b[36m|"

        name = member.display_name[:11] + '…' if len(member.display_name) > 12 else member.display_name
        name = name.ljust(12)
        mmr = f"{floor(player['mmr'])}".rjust(4)
        games = f"{player['games']}".rjust(3)
        win_rate = floor(player['win_rate']*100)
        k = floor(player['avg_kills'])
        d = floor(player['avg_deaths'])
        a = floor(player['avg_assists'])
        score = floor(player['avg_score'])
        
        # Color coding
        rank_color = get_rank_color(guild, float(mmr), ranks)
        win_rate_color = "\u001b[32m" if win_rate > 60 else "\u001b[31m" if win_rate < 40 else "\u001b[0m"
        score_color = "\u001b[32m" if score > avg_score else "\u001b[31m"
        
        kda = f"{k}/{d}/{a}".rjust(8)
        if k < d:
            kda_formatted = kda.replace(str(d), f"\u001b[31m{d}\u001b[0m", 1)
        else:
            kda_formatted = kda

        row = f"{ranking_position:3} {rank_change}\u001b[0m {name} | {rank_color}{mmr}\u001b[0m | {games} | {win_rate_color}{win_rate:3}%\u001b[0m | {kda_formatted} | {score_color}{score:2}\u001b[0m\n"
        
        if ranking_position % 5 == 1:
            if ranking_position == 1:
                header = "  R | Player       |  MMR |   G |  W%  |   K/D/A  | S  "
                field_content = f"```ansi\n\u001b[1m{header}\u001b[0m\n{'─' * len(header)}\n{row}"
            else:
                field_content += "```"
                embed.add_field(name="\u200b", value=field_content, inline=False)
                field_content = f"```ansi\n{row}"
            field_count += 1
        else:
            field_content += row
    if field_content:
        field_content += "```"
        embed.add_field(name="\u200b", value=field_content, inline=False)
    
    return embed