import asyncio
import nextcord

from utils.models import *
from utils.logger import Logger as log

from matches import cleanup_match, get_match


class AbandonView(nextcord.ui.View):
    def __init__(self, bot, match=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.timeout = None
        self.match = match
    
    @nextcord.ui.button(
        label="Yes", 
        emoji="✔️", 
        style=nextcord.ButtonStyle.red, 
        custom_id="mm_accept_abandon_button")
    async def abandon(self, button: nextcord.ui.Button, interaction: nextcord.Integration):
        loop = asyncio.get_event_loop()
        match_instance = get_match(self.match.id)
        if match_instance.current_round is None or match_instance.current_round <= 6:
            if not await cleanup_match(loop, self.match.id):
                log.debug(f"{interaction.user.display_name} had an issue abandoning match {self.match.id}")
                return await interaction.response.send_message("Something went wrong. Try again...", ephemeral=True)
            log.debug(f"{interaction.user.display_name} abandoned match {self.match.id}")
            await self.bot.store.add_match_abandons(interaction.guild.id, self.match.id, [interaction.user.id])
            await interaction.guild.get_thread(self.match.match_thread).send("@here Match Abandoned")
            await interaction.response.send_message(
                f"Match abandoned", ephemeral=True)
            
            settings = await self.bot.store.get_settings(interaction.guild.id)
            log_channel = interaction.guild.get_channel(settings.mm_log_channel)
            log_message = await log_channel.fetch_message(self.match.log_message)
            embed = log_message.embeds[0]
            embed.description = f"Match abandoned by {interaction.user.mention}"
            await log_message.edit(embed=embed)
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
