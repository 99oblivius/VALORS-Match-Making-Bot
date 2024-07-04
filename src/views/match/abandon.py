import asyncio
import nextcord

from utils.models import *
from utils.logger import Logger as log

from matches import cleanup_match


class AbandonView(nextcord.ui.View):
    def __init__(self, bot, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.timeout = None
    
    @nextcord.ui.button(
        label="Yes", 
        emoji="✔️", 
        style=nextcord.ButtonStyle.red, 
        custom_id="mm_accept_abandon_button")
    async def abandon(self, button: nextcord.ui.Button, interaction: nextcord.Integration):
        match = await self.bot.store.get_thread_match(interaction.channel.id)
        loop = asyncio.get_event_loop()
        if match.current_round is None or match.current_round <= 6:
            if not await cleanup_match(loop, match.id):
                log.debug(f"{interaction.user.display_name} had an issue abandoning match {match.id}")
                return await interaction.response.send_message("Something went wrong. Try again...", ephemeral=True)
            log.debug(f"{interaction.user.display_name} abandoned match {match.id}")
            await self.bot.store.add_abandon(interaction.guild.id, interaction.user.id)
            await interaction.guild.get_thread(match.match_thread).send("@here Match Abandoned")
            await interaction.response.send_message(
                f"Match successfully abandoned", ephemeral=True)
        else:
            await interaction.response.send_message("You are not allowed to abandon a match past 6 rounds.", ephemeral=True)
    
    @nextcord.ui.button(
        label="No", 
        emoji="❌", 
        style=nextcord.ButtonStyle.grey,
        custom_id="mm_cancel_abandon_button")
    async def cancel_abandon(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        try: await self.hide_msg.delete()
        except: pass
        await interaction.response.pong()
