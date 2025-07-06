from typing import TYPE_CHECKING, cast
if TYPE_CHECKING:
    from main import Bot

import nextcord

from .ticket_panel import TicketPanelView


class TicketCreationView(nextcord.ui.View):
    def __init__(self, bot: "Bot", *args, **kwargs):
        super().__init__(timeout=300, auto_defer=True, *args, **kwargs)
        self.bot = bot
        self.msg: nextcord.PartialInteractionMessage | None = None
    
    @nextcord.ui.button(
        label="Create", 
        emoji="🏷️", 
        style=nextcord.ButtonStyle.green)
    async def create(self, _: nextcord.ui.Button, interaction: nextcord.Interaction):
        if interaction.guild and (isinstance(interaction.channel, nextcord.TextChannel)) and (user := interaction.user):
            ticket_id = await self.bot.store.create_ticket(
                guild_id=interaction.guild.id,
                user_id=user.id,
                username=user.name)
            if ticket_id is None:
                return await interaction.response.send_message(
                    "Something went wrong with ticket creation.\nTry again...", ephemeral=True)
                
            name = user.name.replace('.', '')
            username = name[:7] + '…' if len(name) > 8 else name
            channel = await interaction.guild.create_text_channel(
                name=f"ticket-#{ticket_id}",
                category=interaction.channel.category,
                overwrites=interaction.channel.category.overwrites | {
                    interaction.guild.default_role: nextcord.PermissionOverwrite(view_channel=False),
                    user: nextcord.PermissionOverwrite(view_channel=True, send_messages=True)
                },
                reason=f"Ticket #{ticket_id}")
            await channel.move(end=True)
            
            await self.bot.store.update_ticket(ticket_id, channel_id=channel.id)
            
            view = TicketPanelView(self.bot, ticket_id)
            await channel.send(embed=view.embed, view=view)
        else:
            await interaction.response.send_message("Ticket creation failed. Please reach out to staff individually to fix this.", ephemeral=True)
        if self.msg: await self.msg.delete()
    
    @nextcord.ui.button(
        label="Cancel", 
        style=nextcord.ButtonStyle.red)
    async def cancel(self, _: nextcord.ui.Button, interaction: nextcord.Interaction):
        if self.msg: await self.msg.delete()
