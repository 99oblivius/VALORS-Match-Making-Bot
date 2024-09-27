import nextcord

class PaginationView(nextcord.ui.View):
    def __init__(self, callback, current_page: int, total_pages: int):
        super().__init__(timeout=300)
        self.callback = callback
        self.current_page = current_page
        self.total_pages = total_pages
        self.update_button_states()

    def update_button_states(self):
        self.first_page.disabled = self.current_page == 1
        self.prev_page.disabled = self.current_page == 1
        self.next_page.disabled = self.current_page == self.total_pages
        self.last_page.disabled = self.current_page == self.total_pages

    @nextcord.ui.button(label="<<", style=nextcord.ButtonStyle.grey)
    async def first_page(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        await self.callback(interaction, page=1)

    @nextcord.ui.button(label="<", style=nextcord.ButtonStyle.grey)
    async def prev_page(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        await self.callback(interaction, page=self.current_page - 1)

    @nextcord.ui.button(label=">", style=nextcord.ButtonStyle.grey)
    async def next_page(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        await self.callback(interaction, page=self.current_page + 1)

    @nextcord.ui.button(label=">>", style=nextcord.ButtonStyle.grey)
    async def last_page(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        await self.callback(interaction, page=self.total_pages)