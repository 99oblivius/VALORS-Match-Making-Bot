import pickle

from datetime import timedelta, datetime, timezone
from typing import TYPE_CHECKING, cast
if TYPE_CHECKING:
    from main import Bot

import nextcord

from utils.models import TicketStatus, TicketTranscripts


class TicketPanelView(nextcord.ui.View):
    def __init__(self, bot: "Bot", ticket_id: int=-1, *args, **kwargs):
        super().__init__(timeout=None, *args, **kwargs)
        self.bot = bot
        self.embed = nextcord.Embed(
            description=f"## Ticket #{ticket_id}\n\n**A staff member will be with you shortly**",
            color=14242732)
    
    @nextcord.ui.button(emoji="➕", style=nextcord.ButtonStyle.red, custom_id="ticketpanel:add", row=0)
    async def add_user(self, _: nextcord.ui.Button, interaction: nextcord.Interaction):
        if not (interaction.guild and isinstance(interaction.channel, nextcord.TextChannel) and isinstance(interaction.user, nextcord.Member)): return
        
        settings = await self.bot.settings_cache(interaction.guild.id)
        staff_channel = interaction.guild.get_channel(cast(int, settings.staff_channel))
        if not staff_channel or not staff_channel.permissions_for(interaction.user).view_channel:
            return await interaction.response.send_message(embed=nextcord.Embed(description="Staff only", color=0xc0c001), ephemeral=True)

        embed = nextcord.Embed(description="### Add users to Ticket", color=0x00f000)
        view = nextcord.ui.View()
        
        add_users = nextcord.ui.UserSelect(max_values=25, custom_id="ticket:add_users")
        
        async def add_users_callback(interaction: nextcord.Interaction):
            if not isinstance(interaction.channel, nextcord.TextChannel): return
            overwrites = interaction.channel.overwrites
            overwrites.update({ user: nextcord.PermissionOverwrite(view_channel=True, send_messages=True) for user in add_users.values })
            await interaction.channel.edit(overwrites=overwrites)
            usernames = '\n'.join((user.display_name for user in add_users.values))
            await interaction.response.send_message(f"The following users were successfully added:```\n{usernames}```", ephemeral=True)
            view.stop()
        
        add_users.callback = add_users_callback
        view.add_item(add_users)
        
        message = await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        await view.wait()
        try: await message.delete()
        except nextcord.HTTPException: pass
    
    @nextcord.ui.button(emoji="➖", style=nextcord.ButtonStyle.red, custom_id="ticketpanel:remove", row=0)
    async def remove_user(self, _: nextcord.ui.Button, interaction: nextcord.Interaction):
        if not (interaction.guild and isinstance(interaction.channel, nextcord.TextChannel) and isinstance(interaction.user, nextcord.Member)): return
        
        settings = await self.bot.settings_cache(interaction.guild.id)
        staff_channel = interaction.guild.get_channel(cast(int, settings.staff_channel))
        if not staff_channel or not staff_channel.permissions_for(interaction.user).view_channel:
            return await interaction.response.send_message(embed=nextcord.Embed(description="Staff only", color=0xc0c001), ephemeral=True)
        
        embed = nextcord.Embed(description="### Remove users from Ticket", color=0xf00000)
        view = nextcord.ui.View()
        
        overwrites = interaction.channel.overwrites
        options = [
            nextcord.SelectOption(label=user.display_name, value=str(user.id), description=user.name)
            for user in overwrites.keys() if not isinstance(user, nextcord.Role)
        ][:25]
        if not options:
            return await interaction.response.send_message("There is no one to remove", ephemeral=True)
        
        remove_users = nextcord.ui.StringSelect(options=options, min_values=1, max_values=len(options), custom_id="ticket:remove_users")
        
        async def remove_users_callback(interaction: nextcord.Interaction):
            if not (interaction.guild and interaction.user and isinstance(interaction.channel, nextcord.TextChannel)): return
            
            
            overwrites = interaction.channel.overwrites
            members = [member for user_id in remove_users.values if (member := interaction.guild.get_member(int(user_id)))]
            for member in members: del overwrites[member]
            
            await interaction.channel.edit(overwrites=overwrites)
            usernames = '\n'.join((member.display_name for member in members))
            await interaction.response.send_message(f"The following users were successfully removed:```\n{usernames}```", ephemeral=True)
            view.stop()
        
        remove_users.callback = remove_users_callback
        view.add_item(remove_users)
        
        message = await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        await view.wait()
        try: await message.delete()
        except nextcord.HTTPException: pass
    
    @nextcord.ui.button(emoji="☃️", style=nextcord.ButtonStyle.blurple, custom_id="ticketpanel:freeze", row=0)
    async def freeze(self, _: nextcord.ui.Button, interaction: nextcord.Interaction):
        if not (interaction.guild and isinstance(interaction.channel, nextcord.TextChannel) and isinstance(interaction.user, nextcord.Member)): return
        
        settings = await self.bot.settings_cache(interaction.guild.id)
        staff_channel = interaction.guild.get_channel(cast(int, settings.staff_channel))
        if not staff_channel or not staff_channel.permissions_for(interaction.user).view_channel:
            return await interaction.response.send_message(embed=nextcord.Embed(description="Staff only", color=0xc0c001), ephemeral=True)
        
        ticket = await self.bot.store.get_ticket_by_channel(interaction.channel.id)
        overwrites = interaction.channel.overwrites
        
        user = interaction.guild.get_member(ticket.user_id)
        if not user: return await interaction.response.send_message("Error no user found", ephemeral=True)
        overwrite = overwrites.get(user, None)
        if not overwrite: return await interaction.response.send_message("Error no user overwrite found", ephemeral=True)
        
        if overwrite.send_messages:
            overwrites[user].send_messages = False
            await interaction.response.send_message(
                embed=nextcord.Embed(description="Ticket frozen", color=0xa0a0ff), ephemeral=True)
        else:
            overwrites[user].send_messages = True
            await interaction.response.send_message(
                embed=nextcord.Embed(description="Ticket unfrozen", color=0xa0a0ff), ephemeral=True)
        
        await interaction.channel.edit(overwrites=overwrites)
    
    @nextcord.ui.button(emoji="📜", style=nextcord.ButtonStyle.grey, custom_id="ticketpanel:history", row=0)
    async def history(self, _: nextcord.ui.Button, interaction: nextcord.Interaction):
        if not (interaction.guild and isinstance(interaction.channel, nextcord.TextChannel) and isinstance(interaction.user, nextcord.Member)): return
        settings = await self.bot.settings_cache(interaction.guild.id)
        staff_channel = interaction.guild.get_channel(cast(int, settings.staff_channel))
        if not staff_channel or not staff_channel.permissions_for(interaction.user).view_channel:
            return await interaction.response.send_message(embed=nextcord.Embed(description="Staff only", color=0xc0c001), ephemeral=True)

        await interaction.response.send_message("Work in progress~", ephemeral=True)
    
    @nextcord.ui.button(label="Ping staff", emoji="🔔", style=nextcord.ButtonStyle.green, custom_id="ticketpanel:ping", row=1)
    async def ping_staff(self, _: nextcord.ui.Button, interaction: nextcord.Interaction):
        if not (interaction.guild and interaction.user and isinstance(interaction.channel, nextcord.TextChannel)): return
        
        ticket = await self.bot.store.get_ticket_by_channel(interaction.channel.id)
        
        next_ping = ticket.last_ping + timedelta(hours=1)
        now = datetime.now(timezone.utc)
        if ticket.last_ping and next_ping > now:
            return await interaction.response.send_message(
                embed=nextcord.Embed(description=f"### You will be able to ping the staff <t:{int(next_ping.timestamp())}:R>", color=0xaaaa00), ephemeral=True)
        
        settings = await self.bot.settings_cache(interaction.guild.id)
        channel = interaction.guild.get_channel(cast(int, settings.staff_channel))
        if not channel: return await interaction.response.send_message("No staff channel set", ephemeral=True)
        await channel.send(embed=nextcord.Embed(description=f"{interaction.user.mention} is looking for assistance in {interaction.channel.mention}"))
        await interaction.response.send_message(embed=nextcord.Embed(description="### Staff were notified!", color=0xaaaa00), ephemeral=True)
        await self.bot.store.update_ticket(ticket.id, last_ping=now)
    
    @nextcord.ui.button(label="Close", emoji="📛", style=nextcord.ButtonStyle.green, custom_id="ticketpanel:close", row=1)
    async def close(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        if not (interaction.guild and isinstance(interaction.channel, nextcord.TextChannel)): return
        ticket = await self.bot.store.get_ticket_by_channel(interaction.channel.id)
        
        yes_button = nextcord.ui.Button(label="Yes", style=nextcord.ButtonStyle.red)
        no_button = nextcord.ui.Button(label="No", style=nextcord.ButtonStyle.grey)
        msg: nextcord.PartialInteractionMessage | None = None
        original_msg = interaction.message
        
        async def delete_confirm(interaction: nextcord.Interaction):
            if not (interaction.guild and interaction.user and isinstance(interaction.channel, nextcord.TextChannel)): return
            
            settings = await self.bot.settings_cache(interaction.guild.id)
            channel = interaction.guild.get_channel(cast(int, settings.staff_channel))
            if not channel: await interaction.response.send_message("No staff channel set", ephemeral=True); return
            await channel.send(
                embed=nextcord.Embed(description=f"{ticket.username}'s `{interaction.channel.name}` was closed by {interaction.user.mention}", color=0xff0000))
            
            await interaction.channel.send(embed=nextcord.Embed(description="Archiving..."))
            all_messages = [message async for message in interaction.channel.history(limit=None)]
            
            channel_data = {
                'channel': {
                    'id': channel.id,
                    'name': channel.name,
                    'guild_id': channel.guild.id,
                },
                'messages': all_messages
            }
            
            serialized_data = pickle.dumps(channel_data)
            
            archive = TicketTranscripts(
                ticket_id=ticket.id,
                guild_id=channel.guild.id,
                archived_at=datetime.now(timezone.utc),
                data=serialized_data)
            await self.bot.store.save_transcript(archive)
            
            await interaction.channel.delete()
        async def delete_cancel(interaction: nextcord.Interaction):
            try: await msg.delete()
            except nextcord.HTTPException: pass
        
        async def close_confirm(interaction: nextcord.Interaction):
            if not (interaction.guild and interaction.user and isinstance(interaction.channel, nextcord.TextChannel)): return
            
            overwrites = interaction.channel.overwrites
            user = interaction.guild.get_member(ticket.user_id)
            if user and user in overwrites: del overwrites[user]
            
            await interaction.channel.edit(overwrites=overwrites)
            await self.bot.store.update_ticket(ticket.id, status=TicketStatus.CLOSED)
            await interaction.response.send_message(
                embed=nextcord.Embed(description=f"The ticket was closed. Only staff still have access to it.", color=0xffaa00))
            button.emoji = "🗑️"
            await original_msg.edit(view=self)
            try: await msg.delete()
            except nextcord.HTTPException: pass
        async def close_cancel(interaction: nextcord.Interaction):
            try: await msg.delete()
            except nextcord.HTTPException: pass
        
        if button.emoji and button.emoji.name == "🗑️":
            embed = nextcord.Embed(
                title="Delete Confirmation",
                description="Are you sure you want to delete this ticket?",
                color=0xff0000)
            
            yes_button.callback = delete_confirm
            no_button.callback = delete_cancel
        else:
            embed = nextcord.Embed(
                title="Close Confirmation",
                description="Are you sure you want to close this ticket?\n-# It won't be deleted yet",
                color=0xffaa00)
            yes_button.callback = close_confirm
            no_button.callback = close_cancel

        view = nextcord.ui.View()
        view.add_item(yes_button)
        view.add_item(no_button)
        
        msg = await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

