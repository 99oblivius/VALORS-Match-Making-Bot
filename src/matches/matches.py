import asyncio
import logging as log
import time
from enum import Enum
import random
from collections import Counter

import nextcord
from utils.models import *
from .match_states import MatchState
from views.match.accept import AcceptView
from views.match.banning import BanView, PicksView
from utils.utils import format_mm_attendence

from config import VALORS_THEME2, VALORS_THEME1_2, VALORS_THEME1, HOME_THEME, AWAY_THEME
from .functions import get_preferred_bans

class Done:
    def __init__(self):
        self.is_done = False


class Team(Enum):
    A = 0
    B = 1


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
        
        guild = self.bot.get_guild(self.guild_id)
        match_thread  = guild.get_channel(match.match_thread)
        a_thread      = guild.get_thread(match.a_thread)
        b_thread      = guild.get_thread(match.b_thread)
        a_vc          = guild.get_thread(match.a_vc)
        b_vc          = guild.get_thread(match.b_vc)
        
        try: match_message = await match_thread.fetch_message(match.match_message)
        except nextcord.NotFound: pass
        try: a_message = await match_thread.fetch_message(match.a_message)
        except nextcord.NotFound: pass
        try: b_message = await match_thread.fetch_message(match.b_message)
        except nextcord.NotFound: pass
        
        if check_state(MatchState.CREATE_MATCH_THREAD):
            match_thread = await settings.queue_channel.create_thread(
                name=f"Match - #{self.match_id}",
                auto_archive_duration=1440,
                invitable=False,
                reason=f"Match - #{self.match_id}")
            await self.bot.store.upsert(MMBotMatches, id=self.match_id, match_thread=match_thread.id)
            await self.increment_state()
        
        if check_state(MatchState.ACCEPT_PLAYERS):
            done = Done()
            add_mention = []
            for player in players:
                add_mention.append(f"<@{player.user_id}>")
            add_mention = "".join(add_mention)

            embed = nextcord.Embed(title=f"Match - #{self.match_id}", color=VALORS_THEME2)
            embed.add_field(name="Attendence", value=format_mm_attendence([p.id for p in player]))
            await match_thread.send(add_mention, embed=embed, view=AcceptView(self.bot, done))

            patience = settings.mm_accept_period
            start_time = time.time()
            while not done.is_done:
                await asyncio.sleep(0)
                if time.time() - start_time > patience:
                    self.state = MatchState.CLEANUP - 1
                    embed = nextcord.Embed(title="Players failed to accept the match", color=VALORS_THEME1_2)
                    await match_thread.send(embed=embed)
                    break
            await self.increment_state()
        
        if check_state(MatchState.MAKE_TEAMS):
            a_players = ...
            b_players = ...
            await self.bot.store.set_players_team(
                match_id=self.match_id, 
                a_player_ids=a_players, 
                b_player_ids=b_players, 
                a_team='A',
                b_team='B')
            await self.increment_state()
        
        if check_state(MatchState.MAKE_TEAM_THREAD_A):
            a_thread = await settings.queue_channel.create_thread(
                name=f"[{self.match_id}] Team A",
                auto_archive_duration=1440,
                invitable=False,
                reason=f"[{self.match_id}] Team A")
            await self.bot.store.upsert(MMBotMatches, id=self.match_id, a_thread=a_thread.id)
            await self.increment_state()
        
        if check_state(MatchState.MAKE_THREAD_MESSAGE_A):
            embed = nextcord.Embed(
                title="Team A", 
                description=f"Things are still happening in <#{match.match_thread}>", 
                color=HOME_THEME)
            a_message = await a_thread.send(embed=embed)
        
        if check_state(MatchState.MAKE_TEAM_THREAD_B):
            b_thread = await settings.queue_channel.create_thread(
                name=f"[{self.match_id}] Team B",
                auto_archive_duration=1440,
                invitable=False,
                reason=f"[{self.match_id}] Team B")
            await self.bot.store.upsert(MMBotMatches, id=self.match_id, b_thread=b_thread.id)
            await self.increment_state()
        
        if check_state(MatchState.MAKE_THREAD_MESSAGE_B):
            embed = nextcord.Embed(
                title="Team B", 
                description=f"Things are still happening in <#{match.match_thread}>", 
                color=AWAY_THEME)
            b_message = await b_thread.send(embed=embed)
        
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
        
        if check_state(MatchState.BANNING_START):
            await match_thread.purge(bulk=True)
            embed = nextcord.Embed(title="Team A ban first", description=f"<#{match.a_thread}>", color=HOME_THEME)
            match_message = await match_thread.send(embed=embed)
            await self.bot.store.upsert(MMBotMatches, id=self.match_id, match_message=match_message.id)
        
        if check_state(MatchState.ADD_TEAM_A):
            msg = await a_thread.send(''.join(f"<@{player}>" for player in a_players))
            await msg.delete()
            await self.increment_state()
        
        if check_state(MatchState.A_BANS):
            embed = nextcord.Embed(title="Pick your 2 bans", color=HOME_THEME)
            await a_message.edit(embed=embed, view=BanView.create_showable(self.bot, self.match_id))
            await asyncio.sleep(30)

            maps = self.bot.store.get_maps(self.guild_id, )
            bans = self.bot.store.get_bans(self.match_id, Team.A)
            bans = get_preferred_bans(maps, bans, total_bans=2)
            embed = nextcord.Embed(title="You banned", color=HOME_THEME)
            await a_message.edit(embed=embed, view=PicksView(bans))
            await self.bot.store.upsert(MMBotMatches, id=self.match_id, a_bans=bans)
            await self.increment_state()
        
        if check_state(MatchState.BAN_SWAP):
            embed = nextcord.Embed(title="Team B ban second", description=f"<#{match.b_thread}>", color=AWAY_THEME)
            await match_message.edit(embed=embed)
            await self.increment_state()
        
        if check_state(MatchState.ADD_TEAM_B):
            await b_thread.send(''.join(f"<@{player}>" for player in b_players))
            await self.increment_state()
        
        if check_state(MatchState.B_BANS):
            embed = nextcord.Embed(title="Pick your 2 bans", color=AWAY_THEME)
            await b_message.edit(embed=embed, view=BanView.create_showable(self.bot, self.match_id))
            await asyncio.sleep(30)
            
            maps = self.bot.store.get_maps(self.guild_id)
            bans = self.bot.store.get_bans(self.match_id, Team.B)
            bans = get_preferred_bans(maps, bans, total_bans=2)
            embed = nextcord.Embed(title="You banned", color=AWAY_THEME)
            await b_message.edit(embed=embed, view=PicksView(bans))
            await self.bot.store.upsert(MMBotMatches, match_id=self.match_id, b_bans=bans)
            await self.increment_state()
        
        if check_state(MatchState.CLEANUP):
            embed = nextcord.Embed(title="The match will end in 10 seconds", color=VALORS_THEME1)
            await asyncio.sleep(10)
            await match_thread.send(embed=embed)
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
            await self.increment_state()