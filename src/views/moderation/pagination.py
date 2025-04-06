import nextcord

class PaginationView(nextcord.ui.View):
    def __init__(self, callback, current_page: int, total_pages: int):
        super().__init__(timeout=300)
        self.callback = callback
        self.current_page = current_page
        self.total_pages = total_pages
        self.update_button_states()
    
    async def is_staff(self, interaction: nextcord.Interaction) -> bool:
        settings = await self.bot.settings_cache(interaction.guild.id)
        staff_role = interaction.guild.get_role(settings.mm_staff_role)
        if staff_role in interaction.user.roles:
            return True
        await interaction.response.send_message("Reserved for staff", ephemeral=True)
        return False


    def update_button_states(self):
        self.first_page.disabled = self.current_page == 1
        self.prev_page.disabled = self.current_page == 1
        self.next_page.disabled = self.current_page == self.total_pages
        self.last_page.disabled = self.current_page == self.total_pages

    @nextcord.ui.button(label="<<", style=nextcord.ButtonStyle.grey)
    async def first_page(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        if not self.is_staff(interaction): return
        await self.callback(interaction, page=1)

    @nextcord.ui.button(label="<", style=nextcord.ButtonStyle.grey)
    async def prev_page(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        if not self.is_staff(interaction): return
        await self.callback(interaction, page=self.current_page - 1)

    @nextcord.ui.button(label=">", style=nextcord.ButtonStyle.grey)
    async def next_page(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        if not self.is_staff(interaction): return
        await self.callback(interaction, page=self.current_page + 1)

    @nextcord.ui.button(label=">>", style=nextcord.ButtonStyle.grey)
    async def last_page(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        if not self.is_staff(interaction): return
        await self.callback(interaction, page=self.total_pages)