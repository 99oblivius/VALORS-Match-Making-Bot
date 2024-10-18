# VALORS Match Making Bot - Discord based match making automation and management service
# Copyright (C) 2024 99oblivius, <projects@oblivius.dev>
#
# This file is part of VALORS Match Making Bot.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import json

import nextcord
from nextcord.ext import commands
from config import GUILD_ID
from utils.utils import log_moderation
from utils.models import MMBotUsers


class ModCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @nextcord.slash_command(
        name="purge", 
        description="Purge messages", 
        default_member_permissions=nextcord.Permissions(manage_messages=True))
    async def purge(self, interaction: nextcord.Interaction, 
        count: int=nextcord.SlashOption(
            default=1, min_value=1, max_value=100, 
            description="How many messages to delete", required=True)
    ):
        await interaction.channel.purge(limit=count, bulk=True)
        await interaction.response.send_message(f"{count} messages purged", ephemeral=True)
    
    @nextcord.slash_command(
        name="embed", 
        description="Create an embed message from a JSON string.", 
        default_member_permissions=nextcord.Permissions(manage_messages=True))
    async def embed(self, interaction: nextcord.Interaction, 
        embed_str: str=nextcord.SlashOption(
            name="json", 
            description="We strongly recommend you use https://glitchii.github.io/embedbuilder/ to generate it.", 
            required=True)
    ):
        content = None
        embeds = []
        try:
            data = json.loads(embed_str)
            content = data['content']
            for e in data['embeds']:
                embeds.append(nextcord.Embed.from_dict(e))
                
            await interaction.channel.send(content=content, embeds=embeds)
            await interaction.response.send_message(f"Done!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(
                f"Failed... ```{repr(e)}```\nCopy paste from [embedbuilder](<https://glitchii.github.io/embedbuilder/>)", ephemeral=True)

    @nextcord.slash_command(name="role_message", description="Set a user's special stats message (only eligible for players who have reached Mythic!)", guild_ids=[GUILD_ID])
    async def role_message(self, interaction: nextcord.Interaction,
        user: nextcord.User | nextcord.Member = nextcord.SlashOption(description="Which user"),
        message: str = nextcord.SlashOption(description="The message to display", max_length=512)
    ):
        await self.bot.store.update(MMBotUsers, guild_id=interaction.guild.id, user_id=user.id, role_message=message)
        await interaction.response.send_message(f"{user.mention}'s role message was set to:\n{message}", ephemeral=True)            
        settings = await self.bot.store.get_settings(interaction.guild.id)
        await log_moderation(interaction, settings.log_channel, f"Role Status Set", f"{user.mention}'s role message changed to:\n```\n{message}```")


def setup(bot):
    bot.add_cog(ModCommands(bot))