from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from main import Bot

import nextcord

from .tickets import TicketCreationView


class TicketsView(nextcord.ui.View):
    def __init__(self, bot: "Bot", *args, **kwargs):
        super().__init__(timeout=None, *args, **kwargs)
        self.bot = bot
    
    @nextcord.ui.button(
        label="Ticket", 
        emoji="🏷️", 
        style=nextcord.ButtonStyle.blurple, 
        custom_id="support:panel")
    async def tickets(self, _: nextcord.ui.Button, interaction: nextcord.Interaction):
        view = TicketCreationView(self.bot)
        message = await interaction.response.send_message(
            embed=nextcord.Embed(
                description="You are about to create a support ticket.\nMake sure you read the **Support** guide before creating a ticket.\nThank you in advance for taking the time.", color=0x20ff20), 
            view=view, ephemeral=True)
        view.msg = message
