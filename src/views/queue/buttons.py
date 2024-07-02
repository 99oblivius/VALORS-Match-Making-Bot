import json
from datetime import datetime, timezone
import asyncio
from typing import Dict

import nextcord
from nextcord.ext import commands

from matches import make_match
from config import GUILD_ID, VALORS_THEME1, MATCH_PLAYER_COUNT, VALORS_THEME1_2, LFG_PING_DELAY
from utils.utils import format_duration, abandon_cooldown


class QueueButtonsView(nextcord.ui.View):
    def __init__(self, bot: commands.Bot, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.ready_lock: Dict[asyncio.Lock] = {}

    @classmethod
    def create_dummy_persistent(cls, bot: commands.Bot):
        instance = cls(bot, timeout=None)
        for slot_id in range(15):
            button = nextcord.ui.Button(label="dummy button", custom_id=f"mm_queue_button:ready:{slot_id}")
            button.callback = instance.ready_callback
            instance.add_item(button)
        
        button = nextcord.ui.Button(label="Unready", custom_id=f"mm_queue_button:unready")
        button.callback = instance.unready_callback
        instance.add_item(button)
    
        button = nextcord.ui.Button(label="Stats", custom_id=f"mm_queue_button:stats")
        button.callback = instance.stats_callback
        instance.add_item(button)
    
        button = nextcord.ui.Button(label="lfg", custom_id=f"mm_queue_button:lfg")
        button.callback = instance.lfg_callback
        instance.add_item(button)
    
        button = nextcord.ui.Button(label="Toggle lfg", custom_id=f"mm_queue_button:toggle_lfg")
        button.callback = instance.toggle_lfg_callback
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
                custom_id=f"mm_queue_button:ready:{n}")
            if (n+1) % 5 == 0:
                row += 1
            instance.add_item(button)
        
        button = nextcord.ui.Button(
            label="Unready", 
            style=nextcord.ButtonStyle.red, 
            custom_id=f"mm_queue_button:unready")
        instance.add_item(button)

        row += 1
    
        button = nextcord.ui.Button(
            label="Stats", 
            row=row,
            style=nextcord.ButtonStyle.blurple, 
            custom_id=f"mm_queue_button:stats")
        instance.add_item(button)
    
        button = nextcord.ui.Button(
            label="lfg", 
            row=row,
            style=nextcord.ButtonStyle.blurple, 
            custom_id=f"mm_queue_button:lfg")
        instance.add_item(button)

        button = nextcord.ui.Button(
            label="Toggle lfg", 
            row=row,
            style=nextcord.ButtonStyle.grey, 
            custom_id=f"mm_queue_button:toggle_lfg")
        instance.add_item(button)

        return instance

    async def update_queue_message(self, interaction: nextcord.Interaction):
        queue_users = await self.bot.store.get_queue_users(interaction.channel.id)
        embed = nextcord.Embed(title="Queue", color=VALORS_THEME1)
        message_lines = []
        for n, item in enumerate(queue_users, 1):
            message_lines.append(f"{n}. <@{item.user_id}> `expires `<t:{item.queue_expiry}:R>")
        embed.add_field(name=f"{len(queue_users)} in queue", value=f"{'\n'.join(message_lines)}\u2800")
        await interaction.edit(embeds=[interaction.message.embeds[0], embed])

    async def ready_callback(self, interaction: nextcord.Interaction):
        lock_id = f'{interaction.channel.id}'
        if lock_id not in self.ready_lock:
            self.ready_lock[lock_id] = asyncio.Lock()
        
        settings = await self.bot.store.get_settings(interaction.guild.id)
        user_platforms = await self.bot.store.get_user_platforms(interaction.guild.id, interaction.user.id)
        if not user_platforms:
            return await interaction.response.send_message(
                "Verify with at least one platform.", ephemeral=True)
        
        in_queue = False
        if not settings: return await interaction.response.send_message(
            "Settings not found.", ephemeral=True)
        
        user = await self.bot.store.get_user(interaction.guild.id, interaction.user.id)
        if not user: return await interaction.response.send_message(
            "You are not registered.", ephemeral=True)
        if not user.region: return await interaction.response.send_message(
            "You must select your region.", ephemeral=True)
        
        in_match = await self.bot.store.is_user_in_match(interaction.user.id)
        if in_match:
            msg = await interaction.response.send_message(
            "Your current match has not ended yet.", ephemeral=True)
            await asyncio.sleep(1.5)
            return await msg.delete()
        previous_abandons, last_abandon = await self.bot.store.get_abandon_count_last_period(interaction.guild.id, interaction.user.id)
        cooldown = abandon_cooldown(previous_abandons, last_abandon)
        if cooldown > 0:
            embed = nextcord.Embed(
                title="You are on cooldown due to abandoning a match",
                description=f"You can queue again in `{format_duration(cooldown)}`",
                color=VALORS_THEME1_2)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        slot_id = int(interaction.data['custom_id'].split(':')[-1])
        periods = list(json.loads(settings.mm_queue_periods).items())
        expiry = int(datetime.now(timezone.utc).timestamp()) + 60 * int(periods[slot_id][1])
        
        async with self.ready_lock[f'{interaction.channel.id}']:
            queue_users = await self.bot.store.get_queue_users(interaction.channel.id)
            total_in_queue = len(queue_users)
            if total_in_queue + 1 > MATCH_PLAYER_COUNT:
                return await interaction.response.send_message("Someone else just got in.\nBetter luck next time", ephemeral=True)
            self.bot.queue_manager.add_user(interaction.user.id, expiry)
            in_queue = await self.bot.store.upsert_queue_user(
                user_id=interaction.user.id, 
                guild_id=interaction.guild.id, 
                queue_channel=interaction.channel.id, 
                queue_expiry=expiry)
            if not in_queue: total_in_queue += 1
            
            if total_in_queue == MATCH_PLAYER_COUNT:
                self.bot.queue_manager.remove_user(interaction.user.id)
                for user in queue_users: self.bot.queue_manager.remove_user(user.user_id)
                self.bot.new_activity_value = 0

                match_id = await self.bot.store.unqueue_add_match_users(settings, interaction.channel.id)
                loop = asyncio.get_event_loop()
                make_match(loop, self.bot, interaction.guild.id, match_id)
            self.bot.new_activity_value = total_in_queue
        
        await self.update_queue_message(interaction)
        await asyncio.sleep(5)
        await msg.delete()
    
    async def unready_callback(self, interaction: nextcord.Interaction):
        if not await self.bot.store.in_queue(interaction.guild.id, interaction.user.id):
            return await interaction.response.send_message("You are not queued up",ephemeral=True)
        self.bot.queue_manager.remove_user(interaction.user.id)
        await self.bot.store.unqueue_user(interaction.channel.id, interaction.user.id)
        self.bot.new_activity_value -= 1
        await self.update_queue_message(interaction)
        await asyncio.sleep(5)
        await msg.delete()
    
    async def stats_callback(self, interaction: nextcord.Interaction):
        await interaction.response.send_message(f"{interaction.user.display_name} clicked!", ephemeral=True)
    
    async def lfg_callback(self, interaction: nextcord.Interaction):
        settings = await self.bot.store.get_settings(interaction.guild.id)
        if not settings.mm_lfg_role:
            return await interaction.response.send_message("lfg_role not set. Set it with </queue settings lfg_role:1257503334533828618>", ephemeral=True)
        
        channel = interaction.guild.get_channel(settings.mm_text_channel)
        if not channel:
            return await interaction.response.send_message("Queue channel not set. Set it with </queue settings set_queue:1257503334533828618>", ephemeral=True)
        
        if interaction.guild.id in self.bot.last_lfg_ping:
            if (int(datetime.now(timezone.utc).timestamp()) - LFG_PING_DELAY) < self.bot.last_lfg_ping[interaction.guild.id]:
                return await interaction.response.send_message(
f"""A ping was already sent <t:{self.bot.last_lfg_ping[interaction.guild.id]}:R>.
Try again <t:{self.bot.last_lfg_ping[interaction.guild.id] + LFG_PING_DELAY}:R>""", ephemeral=True)
        
        self.bot.last_lfg_ping[interaction.guild.id] = int(datetime.now(timezone.utc).timestamp())
        await channel.send(f"All <@&{settings.mm_lfg_role}> members are being summoned!")
        embed = nextcord.Embed(title="LookingForGame members pinged!", color=VALORS_THEME1)
        msg = await interaction.response.send_message(embed=embed, ephemeral=True)
        await asyncio.sleep(5)
        await msg.delete()

    async def toggle_lfg_callback(self, interaction: nextcord.Interaction):
        settings = await self.bot.store.get_settings(interaction.guild.id)
        if not settings.mm_lfg_role:
            return await interaction.response.send_message("lfg_role not set. Set it with </queue settings lfg_role:1257503334533828618>", ephemeral=True)
    
        lfg_role = interaction.guild.get_role(settings.mm_lfg_role)
        if not lfg_role:
            return await interaction.response.send_message("LFG Role is missing. Reach out to staff", ephemeral=True)
        
        if lfg_role in interaction.user.roles:
            await interaction.user.remove_roles(lfg_role)
            return await interaction.response.send_message(f"\- You removed {lfg_role.mention} from yourself", ephemeral=True)
        await interaction.user.add_roles(lfg_role)
        await interaction.response.send_message(f"+ You added {lfg_role.mention} to yourself", ephemeral=True)
