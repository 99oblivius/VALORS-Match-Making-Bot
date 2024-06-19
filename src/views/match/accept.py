import nextcord

from utils.models import *
from utils.utils import format_mm_attendance

from config import MATCH_PLAYER_COUNT

class AcceptView(nextcord.ui.View):
    def __init__(self, bot, done_event=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.timeout = None
        self.done_event = done_event
    
    @nextcord.ui.button(
        label="Accept", 
        emoji="✅", 
        style=nextcord.ButtonStyle.green, 
        custom_id="mm_thread_accept_button")
    async def accept_button(self, button: nextcord.ui.Button, interaction: nextcord.Integration):
        match = await self.bot.store.get_thread_match(interaction.channel.id)
        players = await self.bot.store.get_players(match.id)
        if interaction.user.id in [p.user_id for p in players if p.accepted]:
            return await interaction.response.send_message(
                "You have already accepted the match.\nBut thank you for making sure :)", ephemeral=True)
        
        await self.bot.store.update(MMBotMatchUsers, 
            guild_id=interaction.guild.id, match_id=match.id, user_id=interaction.user.id, accepted=True)
        players = await self.bot.store.get_players(match.id)
        
        embed = interaction.message.embeds[0]
        embed.set_field_at(0, name="Attendance", value=format_mm_attendance(players))
        await interaction.message.edit(embed=embed)
        await interaction.response.send_message(
            "You accepted the match!", ephemeral=True)
        
        accepted_players = await self.bot.store.get_accepted_players(match.id)
        if accepted_players == MATCH_PLAYER_COUNT:
            self.done_event.set()
