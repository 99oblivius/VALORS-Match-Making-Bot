import json
from datetime import datetime, timezone
import asyncio

import nextcord
from nextcord.ext import commands

from config import GUILD_ID, VALOR_YELLOW, VALOR_RED3

from utils.models import (
    MMBotQueueUsers,
    MMBotMatchUsers
)


class QueueButtonsView(nextcord.ui.View):
    def __init__(self, bot: commands.Bot, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.queue_count = 0
        self.critical_queue_lock = asyncio.Lock()

    @classmethod
    def create_dummy_persistent(cls, bot: commands.Bot):
        instance = cls(bot, timeout=None)
        for slot_id in range(15):
            button = nextcord.ui.Button(label="dummy button", custom_id=f"{GUILD_ID}:mm_queue_button:ready:{slot_id}")
            button.callback = instance.ready_callback
            instance.add_item(button)
        
        button = nextcord.ui.Button(label="Unready", custom_id=f"{GUILD_ID}:mm_queue_button:unready")
        button.callback = instance.unready_callback
        instance.add_item(button)

        button = nextcord.ui.Button(label="Queue", custom_id=f"{GUILD_ID}:mm_queue_button:queue")
        button.callback = instance.queue_callback
        instance.add_item(button)
    
        button = nextcord.ui.Button(label="Stats", custom_id=f"{GUILD_ID}:mm_queue_button:stats")
        button.callback = instance.stats_callback
        instance.add_item(button)
    
        button = nextcord.ui.Button(label="lfg", custom_id=f"{GUILD_ID}:mm_queue_button:lfg")
        button.callback = instance.lfg_callback
        instance.add_item(button)

        return instance
    
    @classmethod
    async def create_showable(cls, bot: commands.Bot):
        instance = cls(bot, timeout=None)
        instance.stop()
        settings = await bot.store.get_settings(GUILD_ID)
        periods = json.loads(settings.mm_buttons_periods)
        
        # row may never be above 4
        # set_mm_buttons_periods() in queues/cog.py must not allow more than 25 minus non-period buttons
        row = 0
        for n, label in enumerate(periods.keys()):
            button = nextcord.ui.Button(
                label=f"{label}", 
                row=row,
                style=nextcord.ButtonStyle.green, 
                custom_id=f"{GUILD_ID}:mm_queue_button:ready:{n}")
            if (n+1) % 5 == 0:
                row += 1
            instance.add_item(button)
        
        button = nextcord.ui.Button(
            label="Unready", 
            style=nextcord.ButtonStyle.red, 
            custom_id=f"{GUILD_ID}:mm_queue_button:unready")
        instance.add_item(button)

        row += 1
        button = nextcord.ui.Button(
            label="Queue", 
            row=row,
            style=nextcord.ButtonStyle.blurple, 
            custom_id=f"{GUILD_ID}:mm_queue_button:queue")
        instance.add_item(button)
    
        button = nextcord.ui.Button(
            label="Stats", 
            row=row,
            style=nextcord.ButtonStyle.blurple, 
            custom_id=f"{GUILD_ID}:mm_queue_button:stats")
        instance.add_item(button)
    
        button = nextcord.ui.Button(
            label="lfg", 
            row=row,
            style=nextcord.ButtonStyle.blurple, 
            custom_id=f"{GUILD_ID}:mm_queue_button:lfg")
        instance.add_item(button)

        return instance

    async def ready_callback(self, interaction: nextcord.Interaction):
        settings = await self.bot.store.get_settings(interaction.guild.id)
        if not settings:
            await interaction.response.send_message("Settings not found.", ephemeral=True)
            return
        
        slot_id = int(interaction.data['custom_id'].split(':')[-1])
        periods = list(json.loads(settings.mm_buttons_periods).items())
        expiry = int(datetime.now(timezone.utc).timestamp()) + 60 * int(periods[slot_id][1])
        
        async with self.critical_queue_lock:
            queue_users = await self.bot.store.get_queue_users(interaction.channel.id)
            if len(queue_users) > 9:
                return await interaction.response.send_message("Someone else just got in.\nBest luck next time", ephemeral=True)
            # await self.bot.store.push(MMBotQueueUsers, user_id=interaction.user.id, queue_channel=interaction.channel.id, queue_expiry=expiry)
            # if len(queue_users) > 9:
            #     await self.bot.store.push(MMBotMatchUsers, user_id=)
            #     Match(interaction.channel.id)
        
        embed = nextcord.Embed(title="You joined the queue!", color=VALOR_YELLOW)
        embed.add_field(name=f"{len(queue_users)+1} in queue", value=f"for `{periods[slot_id][1]}` minutes until <t:{expiry}:t>")
        msg = await interaction.response.send_message(embed=embed, ephemeral=True)
        await asyncio.sleep(5)
        await msg.delete()
    
    async def unready_callback(self, interaction: nextcord.Interaction):
        await self.bot.store.remove(MMBotQueueUsers, user_id=interaction.user.id, queue_channel=interaction.channel.id)
        embed = nextcord.Embed(title="You have left queue", color=VALOR_RED3)
        msg = await interaction.response.send_message(embed=embed, ephemeral=True)
        await asyncio.sleep(5)
        await msg.delete()
    
    async def queue_callback(self, interaction: nextcord.Interaction):
        queue_users = await self.bot.store.get_queue_users(interaction.channel.id)
        embed = nextcord.Embed(title="Queue", color=VALOR_YELLOW)
        message_lines = []
        for n, item in enumerate(queue_users, 1):
            message_lines.append(f"{n}. <@{item.user_id}> `expires `<t:{item.queue_expiry}:R>")
        embed.add_field(name=f"{len(queue_users)} in queue", value=f"{'\n'.join(message_lines)}\u2800")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def stats_callback(self, interaction: nextcord.Interaction):
        await interaction.response.send_message(f"{interaction.user.display_name} clicked!", ephemeral=True)
    
    async def lfg_callback(self, interaction: nextcord.Interaction):
        settings = await self.bot.store.get_settings(interaction.guild.id)
        if not settings.mm_lfg_role:
            return await interaction.response.send_message("mm_lfg_role not set. Set it with </queue settings mm_lfg_role:1249109243114557461>", ephemeral=True)
        
        channel = interaction.guild.get_channel(settings.mm_queue_channel)
        if not channel:
            return await interaction.response.send_message("Queue channel not set. Set it with </queue settings set_queue:1249109243114557461>", ephemeral=True)
        
        await channel.send(f"All <@&{settings.mm_lfg_role}> members are being summoned!")
        embed = nextcord.Embed(title="LookingForGame members pinged!", color=VALOR_YELLOW)
        msg = await interaction.response.send_message(embed=embed, ephemeral=True)
        await asyncio.sleep(5)
        await msg.delete()

        