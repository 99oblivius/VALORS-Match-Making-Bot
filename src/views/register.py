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

import asyncio
from typing import List, TYPE_CHECKING
if TYPE_CHECKING:
    from main import Bot

import nextcord
from nextcord.ext import commands

from config import GUILD_ID, VALORS_THEME1_2, VALORS_THEME2
from utils.logger import Logger as log
from utils.models import (
    BotRegions,
    MMBotUsers,
    MMBotUserSummaryStats,
    Platform,
)
from utils.utils import generate_auth_url


class MMHideView(nextcord.ui.View):
    def __init__(self, bot: "Bot", verified_role: nextcord.Role):
        super().__init__(timeout=60)
        self.verified_role = verified_role
        self.bot = bot
        self.hide_msg = None

    @nextcord.ui.button(label="Hide MM", style=nextcord.ButtonStyle.red)
    async def hide_mm(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        await interaction.response.send_message("You have hidden Match Making.", ephemeral=True)
        log.info(f"{interaction.user.display_name} hid MM")
        try: await self.hide_msg.delete()
        except: pass
        await interaction.user.remove_roles(self.verified_role)
        self.bot.queue_manager.remove_user(interaction.user.id)
        await self.bot.store.unqueue_user(interaction.channel.id, interaction.user.id)

    @nextcord.ui.button(label="Cancel", style=nextcord.ButtonStyle.grey)
    async def do_not_hide_mm(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        try: await self.hide_msg.delete()
        except: pass
        await interaction.response.pong()


class RegionSelect(nextcord.ui.Select):
    def __init__(self, bot: "Bot", regions: List[BotRegions]):
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
        await self.bot.store.upsert(MMBotUserSummaryStats, 
            guild_id=interaction.guild.id, 
            user_id=interaction.user.id)
        embed = nextcord.Embed(
            title="Regions", 
            description=f"You have successfully selected `{self.values[0]}`", 
            color=VALORS_THEME2)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class VerifyView(nextcord.ui.View):
    def __init__(self, bot: commands.Bot, urls: List[str], regions: List[BotRegions]=[], *args, **kwargs):
        super().__init__(timeout=300, *args, **kwargs)

        button = nextcord.ui.Button(
            label="Steam", 
            style=nextcord.ButtonStyle.link,
            url=urls[0])
        self.add_item(button)

        button = nextcord.ui.Button(
            label="Manually Register", 
            style=nextcord.ButtonStyle.green)
        button.callback = self.guide_to_manually_register
        self.add_item(button)

        self.add_item(RegionSelect(bot, regions))
    
    async def guide_to_manually_register(self, interaction: nextcord.Interaction):
        embed = nextcord.Embed(
            title="How to manually register",
            description="""
Please open a ticket with staff in <#1231700573087334400>, state that you wish to register for match making, and provide your identifier.
In the case of Steam, you may follow this guide to find it [How can I find my SteamID?](<https://help.steampowered.com/en/faqs/view/2816-BE67-5B69-0FEC>)""",
            color=VALORS_THEME2)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class RegistryButtonView(nextcord.ui.View):
    def __init__(self, bot: commands.Bot, *args, **kwargs):
        super().__init__(timeout=None, *args, **kwargs)
        self.bot = bot

        button = nextcord.ui.Button(
            label="Register", 
            emoji="📋",
            style=nextcord.ButtonStyle.green, 
            custom_id=f"{GUILD_ID}:verify_button")
        button.callback = self.verify_callback
        self.add_item(button)

        button = nextcord.ui.Button(
            label="Join/Leave", 
            style=nextcord.ButtonStyle.blurple, 
            custom_id=f"{GUILD_ID}:register_button")
        button.callback = self.register_callback
        self.add_item(button)
    
    async def verify_callback(self, interaction: nextcord.Interaction):
        regions = await self.bot.store.get_regions(interaction.guild.id)
        if not regions or len(regions) < 1:
            return await interaction.response.send_message(
                f"No regions\nSet regions with {await self.bot.command_cache.get_command_mention(interaction.guild.id, 'settings regions')}", ephemeral=True)
        
        try:
            embed = nextcord.Embed(
                title="Region & Verification", 
                description="- Where do you play from?\n- What platform(s) do you play on?", 
                color=VALORS_THEME2)
            
            urls = [generate_auth_url(self.bot.cache, interaction.guild.id, interaction.user.id, platform.value) for platform in Platform]
            view = VerifyView(self.bot, urls, regions)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            log.debug(f"{interaction.user.display_name} pressed register")
        except Exception:
            await interaction.response.send_message("Something went wrong with the region select.", ephemeral=True)

    async def register_callback(self, interaction: nextcord.Interaction):
        user = await self.bot.store.get_user(interaction.guild.id, interaction.user.id)
        user_platforms = await self.bot.store.get_user_platforms(interaction.guild.id, interaction.user.id)
        if not user or (user and not user.region):
            msg = await interaction.response.send_message(
                "You need to select a region first.", ephemeral=True)
            await asyncio.sleep(1.5)
            await msg.delete()
            return
        
        if not user_platforms:
            msg = await interaction.response.send_message(
                "Verify with at least one platform.", ephemeral=True)
            await asyncio.sleep(1.5)
            await msg.delete()
            return
        
        settings = await self.bot.settings_cache(interaction.guild.id)
        verified_role = interaction.guild.get_role(settings.mm_verified_role)
        if not verified_role:
            return await interaction.response.send_message("Failed to find verified role.", ephemeral=True)
        if verified_role in interaction.user.roles:
            embed = nextcord.Embed(title="Hide Match Making?", color=VALORS_THEME1_2)
            embed.set_footer(text="You will be removed from queue")
            view = MMHideView(self.bot, verified_role)
            msg = await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            view.hide_msg = msg
            return
        await interaction.user.add_roles(verified_role)
        log.info(f"{interaction.user.display_name} joined MM")
        message = f"Join a match in <#{settings.mm_queue_channel}>\nInteract with others in <#{settings.mm_text_channel}>"
        embed = nextcord.Embed(
            title="Welcome to Pavlov Match Making!", 
            description=message,
            color=VALORS_THEME2)
        await interaction.response.send_message(embed=embed, ephemeral=True)