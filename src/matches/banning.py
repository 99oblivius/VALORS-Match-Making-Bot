import nextcord

class BanView(nextcord.ui.View):
    def __init__(self, bot, done, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timeout = None
        self.bot = bot
        self.done = done