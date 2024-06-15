import json
from datetime import datetime, timezone
import asyncio

import nextcord
from nextcord.ext import commands

from matches import make_match
from config import GUILD_ID, VALORS_THEME1
from utils.formatters import format_duration


class QueueButtonsView(nextcord.ui.View):
    def __init__(self, bot: commands.Bot, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.ready_lock: dict = {}

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
        lock_id = f'{interaction.channel.id}'
        if lock_id not in self.ready_lock:
            self.ready_lock[lock_id] = asyncio.Lock()
        
        settings = await self.bot.store.get_settings(interaction.guild.id)
        user = await self.bot.store.get_user(interaction.guild.id, interaction.user.id)
        in_match = await self.bot.store.is_user_in_match(interaction.user.id)
        in_queue = False
        if not settings: return await interaction.response.send_message(
            "Settings not found.", ephemeral=True)
        if not user: return await interaction.response.send_message(
            "You are not registered.", ephemeral=True)
        if not user.region: return await interaction.response.send_message(
            "You must select your region.", ephemeral=True)
        if in_match: return await interaction.response.send_message(
            "Your current match has not ended yet.", ephemeral=True)
        
        slot_id = int(interaction.data['custom_id'].split(':')[-1])
        periods = list(json.loads(settings.mm_queue_periods).items())
        expiry = int(datetime.now(timezone.utc).timestamp()) + 60 * int(periods[slot_id][1])
        
        async with self.ready_lock[f'{interaction.channel.id}']:
            queue_users = await self.bot.store.get_queue_users(interaction.channel.id)
            if len(queue_users) > 9:
                return await interaction.response.send_message("Someone else just got in.\nBetter luck next time", ephemeral=True)
            self.bot.queue_manager.add_user(interaction.user.id, expiry)
            in_queue = await self.bot.store.upsert_queue_user(
                user_id=interaction.user.id, 
                guild_id=interaction.guild.id, 
                queue_channel=interaction.channel.id, 
                queue_expiry=expiry)
            
            if len(queue_users) + 1 == 10:
                match_id = await self.bot.store.unqueue_add_match(interaction.channel.id)
                make_match(self.bot, interaction.guild.id, match_id)

        
        if in_queue: title = "You updated your queue time!"
        else: title = "You joined the queue!"
        embed = nextcord.Embed(title=title, color=VALORS_THEME1)
        embed.add_field(name=f"{len(queue_users)+1} in queue", value=f"for `{format_duration(60 * periods[slot_id][1])}` until <t:{expiry}:t>")
        msg = await interaction.response.send_message(embed=embed, ephemeral=True)
        await asyncio.sleep(5)
        await msg.delete()
    
    async def unready_callback(self, interaction: nextcord.Interaction):
        if not await self.bot.store.in_queue(interaction.guild.id, interaction.user.id):
            return await interaction.response.send_message("You are not queued up",ephemeral=True)
        self.bot.queue_manager.remove_user(interaction.user.id)
        await self.bot.store.unqueue_user(interaction.channel.id, interaction.user.id)
        embed = nextcord.Embed(title="You have left queue", color=VALORS_THEME1)
        msg = await interaction.response.send_message(embed=embed, ephemeral=True)
        await asyncio.sleep(5)
        await msg.delete()
    
    async def queue_callback(self, interaction: nextcord.Interaction):
        queue_users = await self.bot.store.get_queue_users(interaction.channel.id)
        embed = nextcord.Embed(title="Queue", color=VALORS_THEME1)
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
        
        channel = interaction.guild.get_channel(settings.mm_text_channel)
        if not channel:
            return await interaction.response.send_message("Queue channel not set. Set it with </queue settings set_queue:1249109243114557461>", ephemeral=True)
        
        await channel.send(f"All <@&{settings.mm_lfg_role}> members are being summoned!")
        embed = nextcord.Embed(title="LookingForGame members pinged!", color=VALORS_THEME1)
        msg = await interaction.response.send_message(embed=embed, ephemeral=True)
        await asyncio.sleep(5)
        await msg.delete()

        