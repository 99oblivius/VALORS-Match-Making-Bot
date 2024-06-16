import nextcord

from utils.models import *
from utils.formatters import format_mm_attendence

class AcceptView(nextcord.ui.View):
    def __init__(self, bot, done, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.timeout = None
        self.done = done
    
    @nextcord.ui.Button(
        label="Accept", 
        emoji="✅", 
        style=nextcord.ButtonStyle.green, 
        custom_id="mm_thread_accept_button")
    async def AcceptButton(self, button: nextcord.ui.Button, interaction: nextcord.Integration):
        match = await self.bot.store.get_thread_match(interaction.channel.id)
        players = await self.bot.store.get_players(match.id)
        accepted_users = [p.user_id for p in players if p.accepted]
        if interaction.user.id in accepted_users:
            return await interaction.response.send_message(
                "You have already accepted the match.\nBut thank you for making sure :)", ephemeral=True)
        
        await self.bot.store.upsert(MMBotMatchUsers, match_id=match.id, user_id=interaction.user.id, accepted=True)
        interaction.message.embeds[0].fields[0].value = format_mm_attendence([p.id for p in players], accepted_users)
        await interaction.edit(embed=interaction.message.embeds[0])
        await interaction.response.send_message(
            "You accepted the match!", ephemeral=True)
        
        accepted_players = await self.bot.store.get_accepted_players(self.match_id)
        if accepted_players and len(accepted_players) == 10:
            self.done.is_done = True
