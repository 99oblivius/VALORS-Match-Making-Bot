import json
from datetime import datetime, timezone

import nextcord
from nextcord.ext import commands

from config import GUILD_ID


class QueueButtonsView(nextcord.ui.View):
    def __init__(self, bot: commands.Bot, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot

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
        periods = json.loads(settings.mm_queue_periods)
        
        # row may never be above 4
        # set_mm_queue_periods() in queues/cog.py must not allow more than 25 minus non-period buttons
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
        slot_id = int(interaction.data['custom_id'].split(':')[-1])
        periods = json.loads(settings.mm_queue_periods)
        periods = list(periods.items())
        await interaction.response.send_message(
            f"{periods[slot_id][0]} {periods[slot_id][1]} clicked!", ephemeral=True)
        
        expiry = int(datetime.now(timezone.utc).timestamp()) + int(periods[slot_id][1])
        await self.bot.store.push('mm_bot_queue_users', 
            user_id=interaction.user.id, 
            mm_queue_channel=interaction.channel.id, 
            queue_expiry=expiry)
    
    async def unready_callback(self, interaction: nextcord.Interaction):
        await interaction.response.send_message(f"{interaction.user.display_name} clicked!", ephemeral=True)
    
    async def queue_callback(self, interaction: nextcord.Interaction):
        await interaction.response.send_message(f"{interaction.user.display_name} clicked!", ephemeral=True)
    
    async def stats_callback(self, interaction: nextcord.Interaction):
        await interaction.response.send_message(f"{interaction.user.display_name} clicked!", ephemeral=True)
    
    async def lfg_callback(self, interaction: nextcord.Interaction):
        await interaction.response.send_message(f"{interaction.user.display_name} clicked!", ephemeral=True)
        