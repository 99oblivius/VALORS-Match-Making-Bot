import json
from typing import List
from datetime import datetime, timezone
import asyncio

import nextcord
from nextcord.ext import commands

from config import GUILD_ID, VALOR_YELLOW, VALOR_RED3

from utils.models import (
    BotRegions,
    MMBotUsers,
)

class RegionSelect(nextcord.ui.Select):
    def __init__(self, bot: commands.Bot, regions: List[BotRegions]):
        self.bot = bot
        options = [
            nextcord.SelectOption(
                label=region.label,
                emoji=region.emoji if region.emoji else None
            ) for region in regions
        ]
        super().__init__(
            custom_id=f"{GUILD_ID}:regions_select",
            placeholder=f"{len(regions)} region{'s'if len(regions)!=1 else''} to choose from",
            min_values=1,
            max_values=1,
            options=options)
    
    async def callback(self, interaction: nextcord.Interaction):
        await self.bot.store.upsert(MMBotUsers, 
            guild_id=interaction.guild.id, 
            user_id=interaction.user.id, 
            region=self.values[0])
        embed = nextcord.Embed(
            title="Regions", 
            description=f"You have successfully selected `{self.values[0]}`", 
            color=VALOR_YELLOW)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class RegionSelectView(nextcord.ui.View):
    def __init__(self, bot: commands.Bot, regions: List[BotRegions]=[], *args, **kwargs):
        super().__init__(timeout=None, *args, **kwargs)
        self.bot = bot
        self.add_item(RegionSelect(bot, regions))