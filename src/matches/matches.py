import asyncio
import logging as log
import time

import nextcord
from utils.models import *
from .match_states import MatchState
from .accept import AcceptView
from utils.formatters import format_mm_attendence

from config import VALORS_THEME2, VALORS_THEME1_2

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
        players = await self.bot.store.get_players(self.match_id)
        
        match_thread  = self.bot.get_guild(self.guild_id).get_channel(match.match_thread) if match.match_thread else None
        a_thread      = ...
        b_thread      = ...
        a_vc          = ...
        b_vc          = ...
        
        if check_state(MatchState.CREATE_MATCH_THREAD):
            match_thread = await settings.queue_channel.create_thread(
                name=f"Match - #{self.match_id}",
                auto_archive_duration=1440,
                invitable=False,
                reason=f"Match - #{self.match_id}")
            await self.bot.store.upsert(MMBotMatches, id=self.match_id, match_thread=match_thread.id)
            await self.increment_state()
        
        if check_state(MatchState.ACCEPT_PLAYERS):
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
            patience = settings.mm_accept_period
            t_start = time.time()
            while accepted_players < 10:
                sleep_time = 1 - (time.time() - t_start)
                t_start = time.time()
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                print(f"Slept {sleep_time}")
                
                accepted_players = await self.bot.store.get_accepted_players(self.match_id)
                patience -= 1
                if patience < 0:
                    self.state = MatchState.CLEANUP - 1
                    embed = nextcord.Embed(title="Players failed to accept the match", color=VALORS_THEME1_2)
                    await match_thread.send(embed=embed)
                    break
            await self.increment_state()
        
        if check_state(MatchState.MAKE_TEAM_THREAD_A):
            a_thread = await settings.queue_channel.create_thread(
                name=f"[{self.match_id}] Team A",
                auto_archive_duration=1440,
                invitable=False,
                reason=f"[{self.match_id}] Team A")
            await self.bot.store.upsert(MMBotMatches, id=self.match_id, a_thread=a_thread.id)
            await self.increment_state()
        
        if check_state(MatchState.MAKE_TEAM_THREAD_B):
            b_thread = await settings.queue_channel.create_thread(
                name=f"[{self.match_id}] Team B",
                auto_archive_duration=1440,
                invitable=False,
                reason=f"[{self.match_id}] Team B")
            await self.bot.store.upsert(MMBotMatches, id=self.match_id, b_thread=b_thread.id)
            await self.increment_state()
                
        if check_state(MatchState.MAKE_TEAM_VC_A):
            guild = self.bot.get_guild(self.guild_id)
            player_overwrites = { self.bot.get_user(player): nextcord.PermissionOverwrite(connect=True) for player in players }
            player_overwrites.update({
                guild.default_role: nextcord.PermissionOverwrite(view_channel=True, connect=False),
                guild.get_role(settings.mm_staff_role): nextcord.PermissionOverwrite(view_channel=True, connect=True)
            })
            
            a_thread = await settings.queue_channel.category.create_voice_channel(
                name=f"[{self.match_id}] Team A",
                overwrites=player_overwrites,
                reason=f"[{self.match_id}] Team A")
            await self.bot.store.upsert(MMBotMatches, id=self.match_id, a_vc=a_thread.id)
            await self.increment_state()
        
        if check_state(MatchState.MAKE_TEAM_VC_B):
            guild = self.bot.get_guild(self.guild_id)
            player_overwrites = { self.bot.get_user(player): nextcord.PermissionOverwrite(connect=True) for player in players }
            player_overwrites.update({
                guild.default_role: nextcord.PermissionOverwrite(view_channel=True, connect=False),
                guild.get_role(settings.mm_staff_role): nextcord.PermissionOverwrite(view_channel=True, connect=True)
            })
            
            b_thread = await settings.queue_channel.category.create_voice_channel(
                name=f"[{self.match_id}] ] Team B",
                overwrites=player_overwrites,
                reason=f"[{self.match_id}] Team B")
            await self.bot.store.upsert(MMBotMatches, id=self.match_id, b_vc=b_thread.id)
            await self.increment_state()
        
        if check_state(MatchState.CLEANUP):
            # match_thread
            try:
                if match_thread: await match_thread.delete()
            except nextcord.HTTPException: pass
            # a_thread
            try:
                if a_thread: await a_thread.delete()
            except nextcord.HTTPException: pass
            # b_thread
            try:
                if b_thread: await b_thread.delete()
            except nextcord.HTTPException: pass
            # move users back
            guild = self.bot.get_guild(self.guild_id)
            voice_channel = guild.get_channel(settings.mm_voice_channel)
            for player in players:
                member = guild.get_member(player.user_id)
                if member and member.voice and member.voice.channel in [a_vc, b_vc]:
                    await asyncio.sleep(0.1)
                    try: await member.move_to(voice_channel)
                    except nextcord.HTTPException: pass
            # a_vc
            try:
                if a_vc: await a_vc.delete()
            except nextcord.HTTPException: pass
            # b_vc
            try:
                if b_vc: await b_vc.delete()
            except nextcord.HTTPException: pass
            # complete True
            await self.bot.store.upsert(MMBotMatches, id=self.match_id, complete=True)