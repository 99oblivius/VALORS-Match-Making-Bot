import json
import logging as log
from io import BytesIO
import asyncio
from datetime import datetime
import pytz

import nextcord
from nextcord.ext import commands, tasks

from config import *
from views.queue.buttons import QueueButtonsView
from utils.models import BotSettings
from utils.utils import format_duration
from matches import load_ongoing_matches, cleanup_match

from views.match.accept import AcceptView
from views.match.banning import BanView
from views.match.map_pick import MapPickView
from views.match.side_pick import SidePickView

class Queues(commands.Cog):

    @tasks.loop(seconds=60)
    async def rotate_map_pool(self):
        now = datetime.now(pytz.timezone('US/Eastern'))
        if now.minute == 00 and now.hour == 00:
            settings = await self.bot.store.get_settings(GUILD_ID)
            maps = await self.bot.store.get_maps(GUILD_ID)
            new_phase = (settings.mm_maps_phase - 1) % len(maps)
            await self.bot.store.upsert(BotSettings, guild_id=GUILD_ID, mm_maps_phase=new_phase)

    @rotate_map_pool.before_loop
    async def wait_rotate_map_pool(self):
        await self.bot.wait_until_ready()

    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(QueueButtonsView.create_dummy_persistent(self.bot))
        self.bot.add_view(AcceptView(self.bot))
        self.bot.add_view(BanView.create_dummy_persistent(self.bot))
        self.bot.add_view(MapPickView.create_dummy_persistent(self.bot))
        self.bot.add_view(SidePickView.create_dummy_persistent(self.bot))
        self.rotate_map_pool.start()

        await self.bot.queue_manager.fetch_and_initialize_users()
        log.info("[Queues] Cog started")

        matches = await self.bot.store.get_ongoing_matches()
        loop = asyncio.get_event_loop()
        load_ongoing_matches(loop, self.bot, GUILD_ID, matches)

    #####################
    # MM SLASH COMMANDS #
    #####################
    @nextcord.slash_command(name="mm", description="Match making commands", guild_ids=[GUILD_ID])
    async def match_making(self, interaction: nextcord.Interaction):
        pass    

    @match_making.subcommand(name="cancel", description="Cancel a match")
    async def mm_cancel(self, interaction: nextcord.Interaction, match_id: int=nextcord.SlashOption(default=-1, required=False)):
        settings = await self.bot.store.get_settings(interaction.guild.id)
        staff_role = interaction.guild.get_role(settings.staff_role)
        if staff_role and not staff_role in interaction.user.roles:
            msg = await interaction.response.send_message("Missing permissions", ephemeral=True)
            await asyncio.sleep(1)
            await msg.delete()
        if match_id == -1:
            match = await self.bot.store.get_thread_match(interaction.channel.id)
            if match: match_id = match.id
        
        loop = asyncio.get_event_loop()
        if not await cleanup_match(loop, match_id):
                return await interaction.response.send_message(f"Match id `{match_id}` failed to cleanup", ephemeral=True)
        await interaction.response.send_message(f"Match id {match_id} cleaned up successfully", ephemeral=True)

    ########################
    # QUEUE SLASH COMMANDS #
    ########################
    @nextcord.slash_command(name="queue", description="Queue settings", guild_ids=[GUILD_ID])
    async def queue(self, interaction: nextcord.Interaction):
        pass

    ##############################
    # QUEUE SETTINGS SUBCOMMANDS #
    ##############################
    @queue.subcommand(name="settings", description="Queue settings")
    async def queue_settings(self, interaction: nextcord.Interaction):
        pass
    
    @queue_settings.subcommand(name="set_logs", description="Set which channel receives queue logs")
    async def set_logs(self, interaction: nextcord.Interaction):
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, mm_log_channel=interaction.channel.id)
        await interaction.response.send_message("Queue log channel set", ephemeral=True)

    @queue_settings.subcommand(name="accept_period", description="Set match accept period")
    async def set_mm_accept_period(self, interaction: nextcord.Interaction, 
        seconds: int=nextcord.SlashOption(min_value=0, max_value=1800)):
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, mm_accept_period=seconds)
        await interaction.response.send_message(f"Accept period set to `{format_duration(seconds)}`", ephemeral=True)
    
    @set_mm_accept_period.on_autocomplete("seconds")
    async def autocomplete_accept_period(self, interaction: nextcord.Interaction, seconds):
        settings = await self.bot.store.get_settings(interaction.guild.id)
        if not seconds or not settings.mm_queue_periods:
            return await interaction.response.send_autocomplete(choices=[180])
        await interaction.response.send_autocomplete(choices=[seconds, settings.mm_accept_period])

    @queue_settings.subcommand(name="lfg_role", description="Set lfg role")
    async def set_mm_lfg(self, interaction: nextcord.Interaction, lfg: nextcord.Role):
        if not isinstance(lfg, nextcord.Role):
            return await interaction.response.send_message("This is not a role", ephemeral=True)
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, mm_lfg_role=lfg.id)
        await interaction.response.send_message(f"LookingForGame role set to {lfg.mention}", ephemeral=True)

    @queue_settings.subcommand(name="verified_role", description="Set verified role")
    async def set_mm_verified(self, interaction: nextcord.Interaction, verified: nextcord.Role):
        if not isinstance(verified, nextcord.Role):
            return await interaction.response.send_message("This is not a role", ephemeral=True)
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, mm_verified_role=verified.id)
        await interaction.response.send_message(f"Verified role set to {verified.mention}", ephemeral=True)

    @queue_settings.subcommand(name="staff_role", description="Set match making staff role")
    async def set_mm_staff(self, interaction: nextcord.Interaction, staff: nextcord.Role):
        if not isinstance(staff, nextcord.Role):
            return await interaction.response.send_message("This is not a role", ephemeral=True)
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, mm_staff_role=staff.id)
        await interaction.response.send_message(f"Match making staff role set to {staff.mention}", ephemeral=True)

    @queue_settings.subcommand(name="map_options", description="Set how many maps are revealed for pick and bans")
    async def set_maps_range(self, interaction: nextcord.Interaction, size: int=nextcord.SlashOption(min_value=3, max_value=10)):
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, mm_maps_range=size)
        await interaction.response.send_message(f"Match making set to {size} maps range", ephemeral=True)

    async def send_queue_buttons(self, interaction: nextcord.Interaction) -> nextcord.Message:
        embed = nextcord.Embed(title="Ready up!", color=VALORS_THEME2)
        view = await QueueButtonsView.create_showable(self.bot)
        return await interaction.channel.send(embed=embed, view=view)

    @queue_settings.subcommand(name="set_queue", description="Set queue buttons")
    async def set_queue_buttons(self, interaction: nextcord.Interaction):
        settings = await self.bot.store.get_settings(interaction.guild.id)
        if settings and settings.mm_queue_channel and settings.mm_queue_message:
            channel = interaction.guild.get_channel(settings.mm_queue_channel)
            try: msg = await channel.fetch_message(settings.mm_queue_message)
            except nextcord.errors.NotFound: pass
            else: await msg.delete()
        
        if not settings or not settings.mm_queue_periods:
            return await interaction.response.send_message(
                "Failed...\nSet queue periods with </queue settings set_queue_periods:1249109243114557461>", ephemeral=True)

        msg = await self.send_queue_buttons(interaction)
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, mm_queue_message=msg.id, mm_queue_channel=interaction.channel.id)
        await interaction.response.send_message(f"Queue channel set!", ephemeral=True)
    
    @queue_settings.subcommand(name="set_reminder", description="Set queue reminder time in seconds")
    async def set_queue_reminder(self, interaction: nextcord.Interaction, 
            reminder_time: int=nextcord.SlashOption(
                min_value=5, 
                max_value=3600, 
                required=True)):
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, mm_queue_reminder=reminder_time)
        await interaction.response.send_message(f"Queue reminder set to {format_duration(reminder_time)}", ephemeral=True)
    
    @queue_settings.subcommand(name="set_queue_periods", description="Set queue ready periods")
    async def set_queue_periods(self, interaction: nextcord.Interaction, 
        periods: nextcord.Attachment=nextcord.SlashOption(description="JSON file for queue periods")):
        try:
            file = await periods.read()
            periods_json = json.loads(file)
        except Exception as e:
            log.error(f"[Queues] Error loading json file: {repr(e)}")
            return await interaction.response.send_message(
                "The file you provided did not contain a valid JSON string\ne.g. `{\"Short\":5,\"Default\":15}`", ephemeral=True)

        if len(periods_json) > 15:  # Discord limits to 5 buttons on 5 rows (last 2 for other menu)
            return await interaction.response.send_message("Failed.\nToo many periods", ephemeral=True)
        
        periods_str = json.dumps(periods_json, separators=[',', ':'])
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, mm_queue_periods=periods_str)
        await interaction.response.send_message(
            f"Queue periods set to `{periods_str}`\nUse </queue settings set_register:1249942181180084235> to update", ephemeral=True)

    @queue_settings.subcommand(name="get_queue_periods", description="Get the current queue ready periods")
    async def get_queue_periods(self, interaction: nextcord.Interaction):
        settings = await self.bot.store.get_settings(interaction.guild.id)
        if not settings.mm_queue_periods:
            return await interaction.response.send_message("No queue periods set.", ephemeral=True)
        
        periods_json = settings.mm_queue_periods
        periods_dict = json.loads(periods_json)
        
        json_str = json.dumps(periods_dict, indent=4)
        json_bytes = json_str.encode('utf-8')
        json_file = BytesIO(json_bytes)
        json_file.seek(0)
        await interaction.response.send_message(
            "Here are the current queue periods:\n_edit and upload with_ </queue settings set_queue_periods:1249109243114557461>", file=nextcord.File(json_file, filename="queue_periods.json"), ephemeral=True)
    
    @queue_settings.subcommand(name="set_text", description="Set general queueing channel")
    async def set_text_channel(self, interaction: nextcord.Interaction):
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, mm_text_channel=interaction.channel.id)
        await interaction.response.send_message("Text channel set successfully", ephemeral=True)
    
    @queue_settings.subcommand(name="set_voice", description="Set queueing voice channel")
    async def set_voice_channel(self, interaction: nextcord.Interaction, voice_channel: nextcord.VoiceChannel):
        if not isinstance(voice_channel, nextcord.VoiceChannel):
            return await interaction.response.send_message("The channel you selected is not a Voice Channel", ephemeral=True)
        
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, mm_voice_channel=voice_channel.id)
        await interaction.response.send_message("Voice channel set successfully", ephemeral=True)
    
    @queue_settings.subcommand(name="set_maps", description="Choose what maps go into the match making pool")
    async def set_map_pool(self, interaction: nextcord.Interaction, 
        maps: nextcord.Attachment=nextcord.SlashOption(description="Json string for map name and image url (ordered)")):
        try:
            file = await maps.read()
            m = json.loads(file)
        except Exception:
            return await interaction.response.send_message(
                "The file you provided did not contain a valid json string\ne.g. `{\"Dust 2\": \"https://image.img\",}`", ephemeral=True)
        
        settings = await self.bot.store.get_settings(interaction.guild.id)
        await self.bot.store.upsert(BotSettings, guild_id=interaction.guild.id, mm_maps_range=min(settings.mm_maps_range, len(m)), mm_maps_phase=0)
        await self.bot.store.set_maps(guild_id=interaction.guild.id, maps=[(k, v) for k, v in m.items()])
        await interaction.response.send_message(
            f"Maps successfully set to `{', '.join([k for k in m.keys()])}`", ephemeral=True)
    
    @queue_settings.subcommand(name="get_maps", description="Get the current map pool with their media")
    async def get_map_pool(self, interaction: nextcord.Interaction):
        maps = await self.bot.store.get_maps(guild_id=interaction.guild.id)
        map_dict = {m.map: m.media for m in maps}
        
        json_str = json.dumps(map_dict, indent=4)
        json_bytes = json_str.encode('utf-8')
        json_file = BytesIO(json_bytes)
        json_file.seek(0)
        file = nextcord.File(json_file, filename="map_pool.json")
        
        await interaction.response.send_message(
            "Here is the current map pool:\n_edit and upload with_ </queue settings set_maps:1249109243114557461>", file=file, ephemeral=True)


def setup(bot):
    bot.add_cog(Queues(bot))
