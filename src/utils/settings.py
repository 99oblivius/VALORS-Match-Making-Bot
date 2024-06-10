class BotSettings:
    mm_buttons_channel: int = None
    mm_queue_channel: int = None
    mm_queue_message: int = None
    mm_queue_periods: str = None

    def __init__(self, data: list):
        if not data: return
        self.mm_buttons_channel = data[1]
        self.mm_queue_channel = data[2]
        self.mm_queue_message = data[3]
        self.mm_queue_periods = data[4]
    
    def __str__(self):
        return f"<BotSettings: {', '.join(f'{key}={value}' for key, value in vars(self).items())}>"
