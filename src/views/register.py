from typing import List
import asyncio

import nextcord
from nextcord.ext import commands

from config import GUILD_ID, VALORS_THEME2, VALORS_THEME1_2
from utils.utils import generate_auth_url

from utils.models import (
    BotRegions,
    MMBotUsers,
    Platform,
    MMBotUserSummaryStats
)


class MMHideView(nextcord.ui.View):
    def __init__(self, verified_role: nextcord.Role):
        super().__init__(timeout=60)
        self.verified_role = verified_role
        self.hide_msg = None

    @nextcord.ui.button(label="Hide MM", style=nextcord.ButtonStyle.red)
    async def hide_mm(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        await interaction.response.send_message("You have hidden Match Making.", ephemeral=True)
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
            label="PlayStation", 
            style=nextcord.ButtonStyle.link,
            url=urls[1],
            disabled=True)
        self.add_item(button)

        self.add_item(RegionSelect(bot, regions))


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
            label="Join", 
            style=nextcord.ButtonStyle.blurple, 
            custom_id=f"{GUILD_ID}:register_button")
        button.callback = self.register_callback
        self.add_item(button)
    
    async def verify_callback(self, interaction: nextcord.Interaction):
        regions = await self.bot.store.get_regions(interaction.guild.id)
        if not regions or len(regions) < 1:
            return await interaction.response.send_message(
                "No regions\nSet regions with </settings regions:1249942181180084235>", ephemeral=True)
        
        try:
            embed = nextcord.Embed(
                title="Region & Verification", 
                description="- Where do you play from?\n- What platform(s) do you play on?", 
                color=VALORS_THEME2)
            
            urls = [generate_auth_url(self.bot.cache, interaction.guild.id, interaction.user.id, platform.value) for platform in Platform]
            view = VerifyView(self.bot, urls, regions)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
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
        
        settings = await self.bot.store.get_settings(interaction.guild.id)
        verified_role = interaction.guild.get_role(settings.mm_verified_role)
        if not verified_role:
            return await interaction.response.send_message("Failed to find verified role.", ephemeral=True)
        if verified_role in interaction.user.roles:
            embed = nextcord.Embed(title="Hide Match Making?", color=VALORS_THEME1_2)
            embed.set_footer(text="You will be removed from queue")
            view = MMHideView(verified_role)
            msg = await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            view.hide_msg = msg
            return
        await interaction.user.add_roles(verified_role)
        message = f"Join a match in <#{settings.mm_queue_channel}>\nInteract with others in <#{settings.mm_text_channel}>"
        embed = nextcord.Embed(
            title="Welcome to Match Making!", 
            description=message,
            color=VALORS_THEME2)
        await interaction.response.send_message(embed=embed, ephemeral=True)
