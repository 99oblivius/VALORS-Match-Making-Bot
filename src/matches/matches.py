import asyncio
import logging as log
import time
from enum import Enum
import random
from collections import Counter

import nextcord
from nextcord.ext import commands
from utils.models import *
from .match_states import MatchState
from views.match.accept import AcceptView
from views.match.banning import BanView, ChosenBansView
from views.match.map_pick import MapPickView, ChosenMapView
from views.match.side_pick import SidePickView, ChosenSideView
from utils.utils import format_mm_attendance, format_duration

from config import VALORS_THEME2, VALORS_THEME1_2, VALORS_THEME1, HOME_THEME, AWAY_THEME
from .functions import get_preferred_bans, get_preferred_map, get_preferred_side
from .ranked_teams import get_teams


class Match:
    def __init__(self, bot: commands.Bot, guild_id: int, match_id: int, state=MatchState.NOT_STARTED):
        self.bot       = bot
        self.guild_id  = guild_id
        self.match_id  = match_id
        self.state     = state

    async def increment_state(self):
        self.state = MatchState(self.state + 1)
        await self.bot.store.save_match_state(self.match_id, self.state)

    async def load_state(self) -> MatchState:
        return await self.bot.store.load_match_state(self.match_id)

    async def change_state(self, new_state: MatchState):
        self.state = new_state
        await self.bot.store.save_match_state(self.match_id, self.state)

    async def run(self):
        await self.bot.wait_until_ready()
        if self.state > 0: log.info(
            f"[Match] Loaded ongoing match {self.match_id} state:{self.state}")
        
        def check_state(state: MatchState):
            return True if self.state == state else False
        
        self.state  = await self.load_state()
        settings    = await self.bot.store.get_settings(self.guild_id)
        match       = await self.bot.store.get_match(self.match_id)
        users       = await self.bot.store.get_users(self.guild_id)
        players     = await self.bot.store.get_players(self.match_id)
        maps        = await self.bot.store.get_maps(self.guild_id)
        
        guild = self.bot.get_guild(self.guild_id)
        queue_channel = guild.get_channel(settings.mm_queue_channel)

        match_thread  = guild.get_thread(match.match_thread)
        a_thread      = guild.get_thread(match.a_thread)
        b_thread      = guild.get_thread(match.b_thread)

        a_vc          = guild.get_channel(match.a_vc)
        b_vc          = guild.get_channel(match.b_vc)
        
        try:
            if match.match_message: match_message = await match_thread.fetch_message(match.match_message)
        except Exception: pass
        try:
            if match.a_message: a_message = await match_thread.fetch_message(match.a_message)
        except Exception: pass
        try:
            if match.b_message: b_message = await match_thread.fetch_message(match.b_message)
        except Exception: pass

        if check_state(MatchState.NOT_STARTED):
            print("NOT_STARTED")
            await self.increment_state()
        
        if check_state(MatchState.CREATE_MATCH_THREAD):
            match_thread = await queue_channel.create_thread(
                name=f"Match - #{self.match_id}",
                auto_archive_duration=1440,
                invitable=False,
                reason=f"Match - #{self.match_id}")
            await self.bot.store.update(MMBotMatches, id=self.match_id, match_thread=match_thread.id)
            await self.increment_state()
        
        if check_state(MatchState.ACCEPT_PLAYERS):
            add_mention = (f"<@{player.user_id}>" for player in players)
            embed = nextcord.Embed(title=f"Match - #{self.match_id}", color=VALORS_THEME2)
            embed.add_field(name=f"Attendance - {format_duration(settings.mm_accept_period)} to accept", value=format_mm_attendance(players))
            done_event = asyncio.Event()
            await match_thread.send(''.join(add_mention), embed=embed, view=AcceptView(self.bot, done_event))

            try: await asyncio.wait_for(done_event.wait(), timeout=settings.mm_accept_period)
            except asyncio.TimeoutError:
                self.state = MatchState.CLEANUP - 1
                embed = nextcord.Embed(title="Players failed to accept the match", color=VALORS_THEME1_2)
                await match_thread.send(embed=embed)
            await self.increment_state()
        
        if check_state(MatchState.MAKE_TEAMS):
            player_ids = { player.user_id for player in players }
            filtered_users = [user for user in users if user.user_id in player_ids]
            a_players, b_players, a_mmr, b_mmr = get_teams(filtered_users)
            await self.bot.store.set_players_team(
                match_id=self.match_id, 
                user_teams={Team.A: a_players, Team.B: b_players})
            players = await self.bot.store.get_players(self.match_id)
            await self.bot.store.update(MMBotMatches, id=self.match_id, a_mmr=a_mmr, b_mmr=b_mmr)
            await self.increment_state()
        
        if check_state(MatchState.MAKE_TEAM_VC_A):
            player_overwrites = { guild.get_member(player.user_id): nextcord.PermissionOverwrite(connect=True) for player in players if player.team == Team.A }
            player_overwrites.update({
                guild.default_role: nextcord.PermissionOverwrite(view_channel=True, connect=False),
                guild.get_role(settings.mm_staff_role): nextcord.PermissionOverwrite(view_channel=True, connect=True)
            })
            
            a_vc = await queue_channel.category.create_voice_channel(
                name=f"[{self.match_id}] Team A",
                overwrites=player_overwrites,
                reason=f"[{self.match_id}] Team A")
            await self.bot.store.update(MMBotMatches, id=self.match_id, a_vc=a_vc.id)
            await self.increment_state()
        
        if check_state(MatchState.MAKE_TEAM_VC_B):
            player_overwrites = { guild.get_member(player.user_id): nextcord.PermissionOverwrite(connect=True) for player in players if player.team == Team.B }
            player_overwrites.update({
                guild.default_role: nextcord.PermissionOverwrite(view_channel=True, connect=False),
                guild.get_role(settings.mm_staff_role): nextcord.PermissionOverwrite(view_channel=True, connect=True)
            })
            b_vc = await queue_channel.category.create_voice_channel(
                name=f"[{self.match_id}] ] Team B",
                overwrites=player_overwrites,
                reason=f"[{self.match_id}] Team B")
            await self.bot.store.update(MMBotMatches, id=self.match_id, b_vc=b_vc.id)
            await self.increment_state()
        
        if check_state(MatchState.MAKE_TEAM_THREAD_A):
            a_thread = await queue_channel.create_thread(
                name=f"[{self.match_id}] Team A",
                auto_archive_duration=1440,
                invitable=False,
                reason=f"[{self.match_id}] Team A")
            await self.bot.store.update(MMBotMatches, id=self.match_id, a_thread=a_thread.id)
            await self.increment_state()
        
        if check_state(MatchState.MAKE_TEAM_THREAD_B):
            b_thread = await queue_channel.create_thread(
                name=f"[{self.match_id}] Team B",
                auto_archive_duration=1440,
                invitable=False,
                reason=f"[{self.match_id}] Team B")
            await self.bot.store.update(MMBotMatches, id=self.match_id, b_thread=b_thread.id)
            await self.increment_state()
        
        if check_state(MatchState.BANNING_START):
            await match_thread.purge(bulk=True)
            embed = nextcord.Embed(title="Team A ban first", description=f"<#{a_thread.id}>", color=HOME_THEME)
            embed.add_field(name="Team A", 
                value='\n'.join([f"- <@{player.user_id}>" for player in players if player.team == Team.A]))
            embed.add_field(name="Team B", 
                value='\n'.join([f"- <@{player.user_id}>" for player in players if player.team == Team.B]))
            match_message = await match_thread.send(embed=embed)
            await self.bot.store.update(MMBotMatches, id=self.match_id, match_message=match_message.id)
            await self.increment_state()
        
        if check_state(MatchState.A_BANS):
            time_to_ban = 30
            players = await self.bot.store.get_players(self.match_id)
            add_mention = (f"<@{player.user_id}>" for player in players if player.team == Team.A)
            embed = nextcord.Embed(title="Pick your 2 bans", description=format_duration(time_to_ban), color=HOME_THEME)
            view = await BanView.create_showable(self.bot, self.guild_id, match)
            a_message = await a_thread.send(''.join(add_mention), embed=embed, view=view)
            await self.bot.store.update(MMBotMatches, id=self.match_id,  a_message=a_message.id, phase=Phase.A_BAN)
            await asyncio.sleep(time_to_ban)
            await self.bot.store.update(MMBotMatches, id=self.match_id, phase=Phase.NONE)

            bans = await self.bot.store.get_ban_votes(self.match_id, Phase.A_BAN)
            bans = get_preferred_bans([m.map for m in maps], bans, total_bans=2)
            view = ChosenBansView(bans)
            embed = nextcord.Embed(title="You banned", color=HOME_THEME)
            await a_message.edit(embed=embed, view=view)
            embed = nextcord.Embed(title="A banned", color=HOME_THEME)
            await b_thread.send(embed=embed, view=view)
            await self.bot.store.update(MMBotMatches, id=self.match_id, a_bans=bans)
            await self.increment_state()
        
        if check_state(MatchState.BAN_SWAP):
            embed = nextcord.Embed(title="Team B ban second", description=f"<#{b_thread.id}>", color=AWAY_THEME)
            embed.add_field(name="Team A", 
                value='\n'.join([f"- <@{player.user_id}>" for player in players if player.team == Team.A]))
            embed.add_field(name="Team B", 
                value='\n'.join([f"- <@{player.user_id}>" for player in players if player.team == Team.B]))
            await match_message.edit(embed=embed)
            await self.increment_state()
        
        if check_state(MatchState.B_BANS):
            time_to_ban = 30
            players = await self.bot.store.get_players(self.match_id)
            embed = nextcord.Embed(title="Pick your 2 bans", description=format_duration(time_to_ban), color=AWAY_THEME)
            view = await BanView.create_showable(self.bot, self.guild_id, match)
            add_mention = (f"<@{player.user_id}>" for player in players if player.team == Team.B)
            b_message = await b_thread.send(''.join(add_mention), embed=embed, view=view)
            await self.bot.store.update(MMBotMatches, id=self.match_id, phase=Phase.B_BAN, b_message=b_message.id)
            await asyncio.sleep(time_to_ban)
            await self.bot.store.update(MMBotMatches, id=self.match_id, phase=Phase.NONE)
            
            bans = await self.bot.store.get_ban_votes(self.match_id, Phase.B_BAN)
            bans = get_preferred_bans([m.map for m in maps], bans, total_bans=2)
            view = ChosenBansView(bans)
            embed = nextcord.Embed(title="You banned", color=AWAY_THEME)
            await b_message.edit(embed=embed, view=view)
            embed = nextcord.Embed(title="B banned", color=AWAY_THEME)
            await a_thread.send(embed=embed, view=view)
            await self.bot.store.update(MMBotMatches, id=self.match_id, b_bans=bans)
            await self.increment_state()
        
        if check_state(MatchState.A_PICK):
            time_to_pick = 30
            players = await self.bot.store.get_players(self.match_id)
            add_mention = (f"<@{player.user_id}>" for player in players if player.team == Team.A)
            embed = nextcord.Embed(title="Pick your map", description=format_duration(time_to_pick), color=HOME_THEME)
            view = await MapPickView.create_showable(self.bot, self.guild_id, match)
            a_message = await a_thread.send(''.join(add_mention), embed=embed, view=view)
            await self.bot.store.update(MMBotMatches, id=self.match_id,  a_message=a_message.id, phase=Phase.A_PICK)
            await asyncio.sleep(time_to_pick)
            await self.bot.store.update(MMBotMatches, id=self.match_id, phase=Phase.NONE)

            map_votes = await self.bot.store.get_map_votes(self.match_id)
            map_pick = get_preferred_map(maps, map_votes)
            view = ChosenMapView(map_pick.map)
            embed = nextcord.Embed(title="You picked", color=HOME_THEME)
            embed.set_thumbnail(map_pick.media)
            await a_message.edit(embed=embed, view=view)
            embed.title = "A picked"
            await b_thread.send(embed=embed, view=view)
            await self.bot.store.update(MMBotMatches, id=self.match_id, map=map_pick.map)
            await self.increment_state()
        
        if check_state(MatchState.B_PICK):
            time_to_pick = 30
            players = await self.bot.store.get_players(self.match_id)
            add_mention = (f"<@{player.user_id}>" for player in players if player.team == Team.B)
            embed = nextcord.Embed(title="Pick your side", description=format_duration(time_to_pick), color=AWAY_THEME)
            view = await SidePickView.create_showable(self.bot, self.guild_id, match)
            b_message = await b_thread.send(''.join(add_mention), embed=embed, view=view)
            await self.bot.store.update(MMBotMatches, id=self.match_id,  b_message=b_message.id, phase=Phase.B_PICK)
            await asyncio.sleep(time_to_pick)
            await self.bot.store.update(MMBotMatches, id=self.match_id, phase=Phase.NONE)

            side_votes = await self.bot.store.get_side_votes(self.match_id)
            side_pick = get_preferred_side([Side.T, Side.CT], side_votes)
            embed = nextcord.Embed(title="You picked", color=AWAY_THEME)
            await b_message.edit(embed=embed, view=ChosenSideView(side_pick))
            
            a_side = None
            if side_pick == Side.T: a_side = Side.CT
            elif side_pick == Side.CT: a_side = Side.T
            embed = nextcord.Embed(title="You are", color=AWAY_THEME)
            await a_thread.send(embed=embed, view=ChosenSideView(a_side))
            await self.bot.store.update(MMBotMatches, id=self.match_id, b_side=side_pick)
            await self.increment_state()

        if check_state(MatchState.MATCH_SCORES):
            await match_thread.purge(bulk=True)
            match_map = await self.bot.store.get_match_map(self.match_id)
            match_sides = await self.bot.store.get_match_sides(self.match_id)
            embed = nextcord.Embed(title="Match", description="May the best team win!", color=VALORS_THEME1)
            embed.set_image(match_map.media)
            embed.add_field(name=f"Team A - {match_sides[0].name}", 
                value='\n'.join([f"- <@{player.user_id}>" for player in players if player.team == Team.A]))
            embed.add_field(name=f"Team B - {match_sides[1].name}", 
                value='\n'.join([f"- <@{player.user_id}>" for player in players if player.team == Team.B]))
            embed.add_field(name=f"{match_map.map}:", value=None, inline=False)
            match_message = await match_thread.send(embed=embed)
            await self.bot.store.update(MMBotMatches, id=self.match_id, match_message=match_message.id)
            await self.increment_state()
            await asyncio.sleep(15)
        
        if check_state(MatchState.CLEANUP):
            embed = nextcord.Embed(title="The match will terminate in 10 seconds", color=VALORS_THEME1)
            await match_thread.send(embed=embed)
            await asyncio.sleep(10)
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
            except nextcord.HTTPException as e:
                log.warning(f"[Match] a_vc deleting: {repr(e)}")
            # b_vc
            try:
                if b_vc: await b_vc.delete()
            except nextcord.HTTPException:
                log.warning(f"[Match] b_vc deleting: {repr(e)}")
            # complete True
            await self.bot.store.update(MMBotMatches, id=self.match_id, complete=True)
            await self.increment_state()