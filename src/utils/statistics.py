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
from datetime import datetime, timezone
import pytz
from concurrent.futures import ThreadPoolExecutor

import nextcord
from nextcord import Embed, Guild, User, Member, TextChannel, Interaction
import pandas as pd
import numpy as np
from scipy.fft import fft, ifft
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from config import VALORS_THEME1, VALORS_THEME1_1, VALORS_THEME1_2, VALORS_THEME2, REGION_TIMEZONES
from utils.models import MMBotRanks, MMBotUserMatchStats, BotSettings
from utils.utils import get_rank_color, get_rank_role, replace_wide_chars_with_space

async def create_graph_async(loop, graph_type, match_stats, ranks=None, preferences=None, play_periods=None, user_region=None):
    with ThreadPoolExecutor() as pool:
        return await loop.run_in_executor(
            pool,
            create_graph,
            graph_type,
            match_stats,
            ranks,
            preferences,
            play_periods,
            user_region)

def create_graph(graph_type: str, 
                 match_stats: List[MMBotUserMatchStats], 
                 ranks: List[Dict[nextcord.Role, MMBotRanks]] | None=None, 
                 preferences: Dict[str, Dict[str, int]] | None=None,
                 play_periods: List[Tuple[datetime, datetime]] | None=None,
                 user_region: str | None=None) -> go.Figure:
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
        def circular_gaussian_smooth_inplace(minutes_array, sigma):
            n = len(minutes_array)
            x = np.arange(n)
            kernel = np.exp(-0.5 * ((x - n/2)**2) / sigma**2)
            kernel = np.roll(kernel, n//2)
            fft_minutes = fft(minutes_array)
            fft_minutes *= kernel
            minutes_array[:] = np.real(ifft(fft_minutes))

        def normalize_inplace(arr):
            min_val = np.min(arr)
            max_val = np.max(arr)
            arr -= min_val
            arr /= (max_val - min_val)

        def value_to_color(value):
            if value < 0.33:
                r = value * 3
                return f'rgb({int(r*255)},0,0)'
            elif value < 0.66:
                r = 1
                g = (value - 0.33) * 3
                return f'rgb(255,{int(g*255)},0)'
            else:
                r = 1
                g = 1
                b = (value - 0.66) * 3
                return f'rgb(255,255,{int(b*255)})'
        
        def minutes_to_bucket(dt):
            return dt.hour * 60 + dt.minute
        
        def get_region_offset(user_region):
            if user_region not in REGION_TIMEZONES:
                return 0
            
            tz = pytz.timezone(REGION_TIMEZONES[user_region])
            now = datetime.now(pytz.UTC)
            now_local = now.astimezone(tz)
            offset = now_local.utcoffset()
            return offset.total_seconds() / 3600
        
        offset_hours = get_region_offset(user_region)
        
        minutes_in_day = np.zeros(24*60, dtype=float)

        for start, end in play_periods:
            start_minute = minutes_to_bucket(start)
            end_minute = minutes_to_bucket(end)
            
            if end_minute < start_minute:
                minutes_in_day[start_minute:] += 1
                minutes_in_day[:end_minute+1] += 1
            else:
                minutes_in_day[start_minute:end_minute+1] += 1

        circular_gaussian_smooth_inplace(minutes_in_day, 15)
        normalize_inplace(minutes_in_day)

        num_points = len(minutes_in_day)
        theta = np.linspace(0, 2*np.pi, num_points, endpoint=False)
        r_inner, r_outer = 0.5, 1.0

        theta = (theta - (offset_hours * np.pi / 12)) % (2*np.pi)

        x_inner = r_inner * np.cos(theta)
        y_inner = r_inner * np.sin(theta)
        x_outer = r_outer * np.cos(theta)
        y_outer = r_outer * np.sin(theta)

        colors = np.array([value_to_color(v) for v in minutes_in_day])

        fig = go.Figure()

        for i in range(num_points):
            fig.add_trace(
                go.Scatter(
                    x=[x_inner[i], x_outer[i]],
                    y=[y_inner[i], y_outer[i]],
                    mode='lines',
                    line=dict(color=colors[i], width=1),
                    hoverinfo='none',
                    showlegend=False))

        for hour in range(24):
            angle = (hour - 6 - offset_hours) * (2*np.pi/24)
            x, y = r_outer * 1.1 * np.cos(-angle), r_outer * 1.1 * np.sin(-angle)
            adjusted_hour = int((hour - offset_hours) % 24)
            fig.add_annotation(
                x=x, y=y,
                text=f"{adjusted_hour % 12 or 12} {'AM' if adjusted_hour < 12 else 'PM'}",
                showarrow=False,
                font=dict(size=10))
        
        total_games = len(match_stats)
        timezone_info = REGION_TIMEZONES.get(user_region, "/UTC").split('/')[-1]
        fig.add_annotation(
            x=0, y=0,
            text=f"Total Games: {total_games}<br>Timezone: {timezone_info}",
            showarrow=False,
            font=dict(size=12),
            align="center",
            bordercolor="white",
            borderwidth=2,
            borderpad=4,
            bgcolor="rgba(0,0,0,0.5)",
            opacity=0.8
        )
        
        fig.update_layout(
            showlegend=False,
            xaxis=dict(visible=False, range=[-1.2, 1.2]),
            yaxis=dict(visible=False, range=[-1.2, 1.2]),
            width=600,
            height=600,
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=0, r=0, t=0, b=0))
        fig.update_yaxes(scaleanchor="x", scaleratio=1)
    
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
        if guild.get_member(player['user_id']):
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
        recent_matches_str = "\n".join([f"{'W' if match.win else 'L'} | K: {match.kills:>2} | D: {match.deaths:>2} | A: {match.assists:>2} | MMR: {f'{match.mmr_change:+.2f}' if match.mmr_change else "In-game"}" for match in recent_matches])
        embed.add_field(name="Recent Matches", value=f"```{recent_matches_str}```", inline=False)
    else:
        embed.add_field(name="Recent Matches", value="No recent matches found", inline=False)
    
    return embed

async def create_leaderboard_embed(guild: Guild, leaderboard_data: List[Dict[str, Any]], ranks: List[MMBotRanks], start_rank: int) -> Tuple[Embed, int]:
    valid_scores = [player['avg_score'] for player in leaderboard_data if guild.get_member(player['user_id'])]
    avg_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0
    
    embed = Embed()
    if start_rank == 1:
        embed.title = "Match Making Leaderboard"
        embed.set_footer(text="K/D/A and Score are mean averages")

    field_content = ""
    players_added = 0

    previous_positions = { player['user_id']: i + 1 for i, player in enumerate(sorted(leaderboard_data, key=lambda x: x['previous_mmr'] or 0, reverse=True)) }

    for ranking_position in range(start_rank, start_rank + 50):
        if ranking_position > len(leaderboard_data):
            break

        player = leaderboard_data[ranking_position - 1]
        member = guild.get_member(player['user_id'])
        if member is None:
            continue

        players_added += 1

        previous_position = previous_positions.get(player['user_id'], None)
        if previous_position is None:
            rank_change = "\u001b[35m·"
        else:
            position_change = previous_position - ranking_position
            if position_change > 0:
                rank_change = f"\u001b[32m↑"
            elif position_change < 0:
                rank_change = f"\u001b[31m↓"
            else:
                rank_change = f"\u001b[36m|"

        name = member.display_name[:11] + '…' if len(member.display_name) > 12 else member.display_name
        name = replace_wide_chars_with_space(name)
        name = name.ljust(12)
        mmr = f"{floor(player['mmr'])}".rjust(4)
        games = f"{player['games']}".rjust(3)
        win_rate = floor(player['win_rate']*100)
        k = floor(player['avg_kills'])
        d = floor(player['avg_deaths'])
        a = floor(player['avg_assists'])
        score = floor(player['avg_score'])
        
        rank_color = get_rank_color(guild, float(mmr), ranks)
        win_rate_color = "\u001b[32m" if win_rate > 60 else "\u001b[31m" if win_rate < 40 else "\u001b[0m"
        score_color = "\u001b[32m" if score > avg_score else "\u001b[31m"
        
        kda = f"{k}/{d}/{a}".rjust(8)
        kda_formatted = kda.replace(str(d), f"\u001b[31m{d}\u001b[0m", 1) if k < d else kda

        row = f"{ranking_position:3} {rank_change}\u001b[0m {name} | {rank_color}{mmr}\u001b[0m | {games} | {win_rate_color}{win_rate:3}%\u001b[0m | {kda_formatted} | {score_color}{score:2}\u001b[0m\n"
        
        if players_added % 5 == 1:
            if players_added == 1:
                header = "  R | Player       |  MMR |   G |  W%  |   K/D/A  | S  "
                field_content = f"```ansi\n\u001b[1m{header}\u001b[0m\n{'─' * len(header)}\n{row}"
            else:
                embed.add_field(name="\u200b", value=field_content + "```", inline=False)
                field_content = f"```ansi\n{row}"
        else:
            field_content += row

    if field_content:
        embed.add_field(name="\u200b", value=field_content + "```", inline=False)

    return embed, ranking_position + 1

async def update_leaderboard(store, guild: Guild):
    settings = await store.get_settings(guild.id)
    channel = guild.get_channel(settings.leaderboard_channel)
    if not isinstance(channel, TextChannel):
        return

    data = await store.get_leaderboard_with_previous_mmr(guild.id)
    ranks = await store.get_ranks(guild.id)

    # Remove players who have left the server
    data = [player for player in data if guild.get_member(player['user_id'])]

    total_players = len(data)

    header_embed = Embed(title="Match Making Leaderboard")
    header_embed.add_field(name="Total Players", value=str(total_players), inline=True)
    header_embed.set_footer(text="K/D/A and Score are mean averages")

    try:
        header_message = await channel.fetch_message(settings.leaderboard_message)
        await header_message.edit(content=None, embed=header_embed)
    except:
        header_message = await channel.send(embed=header_embed)
        await store.update(BotSettings, 
            guild_id=guild.id, 
            leaderboard_channel=channel.id, 
            leaderboard_message=header_message.id)

    existing_messages = []
    async for message in channel.history(after=header_message, limit=None):
        if message.author == guild.me:
            existing_messages.append(message)
        else:
            await message.delete()
    existing_messages.sort(key=lambda m: m.created_at)

    start_rank = 1
    for i in range((len(data) - 1) // 50 + 1):
        embed, next_start_rank = await create_leaderboard_embed(guild, data, ranks, start_rank)
        if i < len(existing_messages):
            try:
                await existing_messages[i].edit(embed=embed)
            except:
                await channel.send(embed=embed)
        else:
            await channel.send(embed=embed)
        start_rank = next_start_rank

    for message in existing_messages[((len(data) - 1) // 50 + 1):]:
        try:
            await message.delete()
        except:
            pass