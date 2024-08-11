import nextcord
from nextcord.ext import commands
from nextcord import Interaction, SlashOption
from typing import List, Dict
from config import GUILD_ID
from fuzzywuzzy import process

class HelpCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.all_commands = {}

    @nextcord.slash_command(name="help", description="Display information about available commands", guild_ids=[GUILD_ID])
    async def help(self, interaction: Interaction, 
                   command: str = SlashOption(required=False, description="Specific command to get help for", autocomplete=True)):
        await interaction.response.defer(ephemeral=True)

        if not self.all_commands:
            self.all_commands = await self.bot.command_cache.get_all_commands(interaction.guild_id)

        if command:
            await self.show_command_help(interaction, command)
        else:
            await self.show_all_commands(interaction)

    @help.on_autocomplete("command")
    async def autocomplete_command(self, interaction: Interaction, command: str):
        if not self.all_commands:
            self.all_commands = await self.bot.command_cache.get_all_commands(interaction.guild_id)

        all_command_names = self.get_all_command_names(self.all_commands)
        
        if not command:
            return all_command_names[:25]
        
        matches = process.extract(command, all_command_names, limit=25)
        return [match[0] for match in matches]

    def get_all_command_names(self, commands: List[Dict], prefix: str = "") -> List[str]:
        names = []
        for cmd in commands:
            full_name = f"{prefix}{cmd['name']}"
            names.append(full_name)
            if 'options' in cmd:
                for option in cmd['options']:
                    if option['type'] == 1 or option['type'] == 2:  # Subcommand or subcommand group
                        names.extend(self.get_all_command_names([option], f"{full_name} "))
        return names

    async def show_command_help(self, interaction: Interaction, command_name: str):
        command = self.find_command(self.all_commands, command_name.split())
        
        if not command:
            await interaction.followup.send(f"Command '{command_name}' not found.", ephemeral=True)
            return

        embed = nextcord.Embed(title=f"Help: /{command_name}", color=0x3498db)
        embed.add_field(name="Description", value=command['description'], inline=False)
        
        if command.get('options'):
            options_text = self.format_options(command['options'])
            if options_text:
                embed.add_field(name="Options", value=options_text, inline=False)

        permissions = self.get_required_permissions(command)
        if permissions:
            embed.add_field(name="Required Permissions", value=", ".join(permissions), inline=False)

        await interaction.followup.send(embed=embed)

    def find_command(self, commands: List[Dict], command_parts: List[str]) -> Dict:
        for cmd in commands:
            if cmd['name'] == command_parts[0]:
                if len(command_parts) == 1:
                    return cmd
                if 'options' in cmd:
                    return self.find_command(cmd['options'], command_parts[1:])
        return None

    def format_options(self, options: List[Dict], indent: str = "") -> str:
        text = ""
        for opt in options:
            if opt['type'] in [1, 2]:  # Subcommand or subcommand group
                text += f"{indent}• **{opt['name']}**: {opt['description']}\n"
                if 'options' in opt:
                    text += self.format_options(opt['options'], indent + "  ")
            else:
                text += f"{indent}• **{opt['name']}**: {opt['description']}\n"
        return text

    def get_required_permissions(self, command: Dict) -> List[str]:
        permissions = []
        if command.get('default_member_permissions'):
            perm_int = int(command['default_member_permissions'])
            if perm_int & 0x0000000008 == 0x0000000008:
                permissions.append("Administrator")
            # Add more permission checks as needed
        return permissions

    def group_commands(self, commands: List[Dict]) -> Dict[str, List[Dict]]:
        groups = {
            "\u2800": [], 
            "Statistics": [],
            "Administration": [],
            "Settings": [],
            "Other": []
        }

        for cmd in commands:
            if cmd['name'] in ['stats', 'graph', 'advanced_stats', 'advanced_graph']:
                groups["Statistics"].append(cmd)
            elif cmd['name'].startswith('settings') or cmd['name'] in ['add_server', 'remove_server'] or cmd['name'].startswith(('mm', 'queue', 'match')):
                groups["Settings"].append(cmd)
            elif self.get_required_permissions(cmd):
                groups["Administration"].append(cmd)
            else:
                groups["Other"].append(cmd)

        return { k: v for k, v in groups.items() if v }

    async def show_all_commands(self, interaction: Interaction):
        command_groups = self.group_commands(self.all_commands)

        embeds = []
        for group, commands in command_groups.items():
            embed = nextcord.Embed(title=f"{group} Commands", color=0x3498db)
            for cmd in commands:
                permissions = self.get_required_permissions(cmd)
                value = f"{cmd['description']}\n"
                if permissions:
                    value += f"Required permissions: {', '.join(permissions)}\n"
                value += f"Use `/help {cmd['name']}` for more details"
                embed.add_field(name=f"/{cmd['name']}", value=value.strip(), inline=False)
            embeds.append(embed)

        total_pages = len(embeds)
        current_page = 0

        async def update_message(interaction: Interaction):
            embed = embeds[current_page]
            embed.set_footer(text=f"Page {current_page + 1}/{total_pages}")
            await interaction.response.edit_message(embed=embed, view=view)

        async def previous_page(interaction: Interaction):
            nonlocal current_page
            if current_page > 0:
                current_page -= 1
                await update_message(interaction)

        async def next_page(interaction: Interaction):
            nonlocal current_page
            if current_page < total_pages - 1:
                current_page += 1
                await update_message(interaction)

        view = nextcord.ui.View()
        view.add_item(nextcord.ui.Button(label="Previous", style=nextcord.ButtonStyle.gray, custom_id="previous"))
        view.add_item(nextcord.ui.Button(label="Next", style=nextcord.ButtonStyle.gray, custom_id="next"))

        view.children[0].callback = previous_page
        view.children[1].callback = next_page

        initial_embed = embeds[0]
        initial_embed.set_footer(text=f"Page 1/{total_pages}")
        await interaction.followup.send(embed=initial_embed, view=view)

def setup(bot):
    bot.add_cog(HelpCommand(bot))