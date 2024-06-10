import json

import nextcord
from nextcord.ext import commands


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
        try:
            embed = nextcord.Embed.from_dict(json.loads(embed_str)['embeds'][0])
            await interaction.channel.send(embed=embed)
            await interaction.response.send_message(f"Done!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(
                f"Failed... ```{repr(e)}```\nCopy paste from [embedbuilder](<https://glitchii.github.io/embedbuilder/>)", ephemeral=True)


def setup(bot):
    bot.add_cog(ModCommands(bot))