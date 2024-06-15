import asyncio
import logging as log

import nextcord
from utils.models import *
from .match_states import MatchState
from .accept import AcceptView
from utils.formatters import format_mm_attendence

from config import VALORS_THEME2

class Match:
    def __init__(self, bot, guild_id: int, match_id: int, state: int=0):
        self.bot       = bot
        self.guild_id  = guild_id
        self.match_id  = match_id
        self.state     = state
    
    def start(self):
        asyncio.get_event_loop().run_until_complete(self.run())

    async def increment_state(self):
        self.state += 1
        await self.bot.store.save_match_state(self.match_id, self.state)

    async def load_state(self) -> MatchState:
        return await self.bot.store.load_match_state(self.match_id)

    async def run(self):
        if self.state > 0: log.critical(
            f"[Match] Loaded  ongoing match {self.match_id} state:{self.state}")
        
        def check_state(state: MatchState):
            return True if self.state == state else False
        
        self.state = await self.load_state()
        settings = await self.bot.store.get_settings(self.guild_id)
        match = await self.bot.store.get_match(self.match_id)
        
        
        match_thread = self.bot.get_channel(match.match_thread) if match.match_thread else None
        
        if check_state(MatchState.CREATE_MATCH_THREAD):
            match_thread = await settings.queue_channel.create_thread(
                name=f"Match - #{self.match_id}",
                auto_archive_duration=1440,
                invitable=False,
                reason=f"Match - #{self.match_id}")
            await self.bot.store.upsert(MMBotMatches, id=self.match_id, match_thread=match_thread.id)
            await self.increment_state()
        
        if check_state(MatchState.ACCEPT_PLAYERS):
            players = await self.bot.store.get_players(self.match_id)
            add_mention = []
            for player in players:
                add_mention.append(f"<@{player.user_id}>")
            add_mention = " ".join(add_mention)

            embed = nextcord.Embed(title=f"Match - #{self.match_id}", color=VALORS_THEME2)
            embed.add_field(name="Attendence", value=format_mm_attendence([p.id for p in player]))
            await match_thread.send(add_mention, embed=embed, view=AcceptView(self.bot))
            await self.increment_state()
        
        if check_state(MatchState.ACCEPT_WAIT):
            accepted_players = 0
            while accepted_players < 10:
                asyncio.sleep(1)
                accepted_players = await self.bot.store.get_accepted_players(self.match_id)
            await self.increment_state()
