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

import json
import re
from datetime import datetime, timedelta, timezone
from io import BytesIO
import asyncio

import nextcord
from nextcord.ext import commands

from config import *
from utils.logger import Logger as log
from utils.models import BotSettings
from utils.statistics import create_graph_async, create_stats_embed
from utils.utils import format_duration, create_queue_embed
from views.queue.buttons import QueueButtonsView


class Advanced(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_ready(self):
        log.info("Cog started")

    @nextcord.slash_command(name="advanced_stats", description="List your recent performance", guild_ids=[GUILD_ID])
    async def stats(self, interaction: nextcord.Interaction, 
        user: nextcord.User | None = nextcord.SlashOption(required=False)
    ):
        settings = await self.bot.store.get_settings(interaction.guild.id)
        if user is None:
            user = interaction.user

        summary_stats = await self.bot.store.get_user_summary_stats(interaction.guild.id, user.id)
        if not summary_stats:
            return await interaction.response.send_message(f"No stats found for {user.mention}.", ephemeral=True)

        recent_matches = await self.bot.store.get_recent_match_stats(interaction.guild.id, user.id, 10)
        avg_stats = await self.bot.store.get_avg_stats_last_n_games(interaction.guild.id, user.id, 10)
        leaderboard = await self.bot.store.get_leaderboard(interaction.guild.id, limit=100)
        ranks = await self.bot.store.get_ranks(interaction.guild.id)
        embed = create_stats_embed(interaction.guild, user, leaderboard, summary_stats, avg_stats, recent_matches, ranks)

        await interaction.response.send_message(
            embed=embed, ephemeral=interaction.channel.id != settings.mm_text_channel)

    @nextcord.slash_command(name="advanced_graph", description="View advanced graphs", guild_ids=[GUILD_ID])
    async def advanced_graph(self, interaction: nextcord.Interaction,
        user: nextcord.User = nextcord.SlashOption(
            required=False, 
            description="User to view graph for"),
        graph_type: str = nextcord.SlashOption(
            name="type",
            description="Type of graph to display",
            choices={
                "MMR": "mmr_game",
                "Kills": "kills_game",
                "K/D": "kd_game",
                "Win rate over time": "winrate_time",
                "Score": "score_game",
                "Performance Overview": "performance_overview",
                "Activity Hours": "activity_hours",
                "Pick Preferences": "pick_preferences"
            },
            default="mmr_game",
            required=False),
        period: str = nextcord.SlashOption(
            name="period",
            description="Time period (format: 0y0m0d0h or Ng for last N games)",
            required=False,
            default="50g")
    ):
        settings = await self.bot.store.get_settings(interaction.guild.id)
        ephemeral = interaction.channel.id != settings.mm_text_channel
        await interaction.response.defer(ephemeral=ephemeral)
        user = user or interaction.user

        # Parse the period
        if period.endswith('g'):
            game_limit = int(period[:-1])
            match_stats = await self.bot.store.get_last_n_match_stats(interaction.guild.id, user.id, game_limit)
        else:
            period_match = re.match(r"(?:(\d+)y)?(?:(\d+)m)?(?:(\d+)d)?(?:(\d+)h)?", period)
            if not period_match:
                return await interaction.followup.send("Invalid period format. Use 0y0m0d0h (e.g., 1y6m for 1 year and 6 months) or Ng (e.g., 50g for last 50 games).", ephemeral=True)

            years, months, days, hours = map(lambda x: int(x) if x else 0, period_match.groups())
            start_date = datetime.now() - timedelta(days=years*365 + months*30 + days, hours=hours)
            end_date = datetime.now()
            match_stats = await self.bot.store.get_match_stats_in_period(interaction.guild.id, user.id, start_date, end_date)

        if not match_stats:
            return await interaction.followup.send(f"No data found for {user.mention} in the specified period `{period}`.", ephemeral=True)

        ranks = None
        if graph_type == "mmr_game":
            ranks = await self.bot.store.get_ranks(interaction.guild.id)
            ranks = { interaction.guild.get_role(rank.role_id): rank for rank in ranks }
        
        preferences = None
        if graph_type == "pick_preferences":
            preferences = await self.bot.store.get_user_pick_preferences(interaction.guild.id, user.id)
        
        region = None
        play_periods = None
        if graph_type == "activity_hours":
            region = (await self.bot.store.get_user(interaction.guild.id, user.id)).region
            play_periods = await self.bot.store.get_player_play_periods(interaction.guild.id, user.id)
        fig = await create_graph_async(asyncio.get_event_loop(), graph_type, match_stats, ranks, preferences, play_periods, region)
        
        # Save the plot to a BytesIO object
        img_bytes = BytesIO()
        fig.write_image(img_bytes, format="png", scale=2)
        img_bytes.seek(0)

        # Create a Discord file from the BytesIO object
        file = nextcord.File(img_bytes, filename="graph.png")
        settings = await self.bot.store.get_settings(interaction.guild.id)
        await interaction.followup.send(f"Graph for {user.mention}", file=file, ephemeral=ephemeral)


def setup(bot):
    bot.add_cog(Advanced(bot))
