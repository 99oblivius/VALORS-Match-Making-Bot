# VALORS Match Making Bot - Discord based match making automation and management service
# Copyright (C) 2024 99oblivius, <projects@oblivius.dev>
#
# This file is part of VALORS Match Making Bot.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

from enum import Enum

from sqlalchemy import (
   ARRAY,
   TIMESTAMP,
   BigInteger,
   Boolean,
   Column,
   Enum as sq_Enum,
   Float,
   ForeignKey,
   ForeignKeyConstraint,
   Integer,
   SmallInteger,
   String,
   Text,
   UniqueConstraint,
   func,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Phase(Enum):
    NONE = 0
    A_BAN = 1
    B_BAN = 2
    A_PICK = 3
    B_PICK = 4


class Team(Enum):
    A = 0
    B = 1


class Side(Enum):
    CT = 0
    T = 1


class Platform(Enum):
    STEAM = "steam"


class UserPlatformMappings(Base):
    __tablename__ = 'user_platform_mappings'

    id           = Column(Integer, primary_key=True)
    guild_id     = Column(BigInteger, nullable=False)
    user_id      = Column(BigInteger, nullable=False)
    platform     = Column(sq_Enum(Platform), nullable=False)
    platform_id  = Column(String(64), unique=True, nullable=False)
    created_at   = Column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('guild_id', 'user_id', 'platform', name='unique_guild_user_platform'),
    )

class RconServers(Base):
    def __eq__(self, other):
        if isinstance(other, str):
            return f'{self.host}:{self.port}' == other
        return f'{self.host}:{self.port}' == f'{other.host}:{other.port}'
    
    __tablename__ = 'rcon_servers'

    id          = Column(Integer, primary_key=True, nullable=False)
    host        = Column(String(45), nullable=False)
    port        = Column(Integer, nullable=False)
    password    = Column(Text, nullable=False)
    region      = Column(String(32), nullable=False)
    being_used  = Column(Boolean, nullable=False, default=False)
    timestamp   = Column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('host', 'port', name='unique_host_port'),
    )

class BotSettings(Base):
    __tablename__ = 'bot_settings'

    guild_id           = Column(BigInteger, primary_key=True, nullable=False)
    staff_channel      = Column(BigInteger)
    log_channel        = Column(BigInteger)
    
    mm_queue_channel   = Column(BigInteger)
    mm_queue_message   = Column(BigInteger)
    mm_queue_periods   = Column(Text)
    mm_accept_period   = Column(SmallInteger, nullable=False, default=180)
    mm_maps_range      = Column(SmallInteger, nullable=False, default=10)
    mm_maps_phase      = Column(SmallInteger, nullable=False, default=0)

    mm_text_channel    = Column(BigInteger)
    mm_queue_reminder  = Column(Integer, nullable=False, default=180)
    mm_voice_channel   = Column(BigInteger)
    mm_log_channel     = Column(BigInteger)
    mm_verified_role   = Column(BigInteger)
    mm_lfg_role        = Column(BigInteger)
    mm_staff_role      = Column(BigInteger)

    register_channel     = Column(BigInteger)
    register_message     = Column(BigInteger)
    leaderboard_channel  = Column(BigInteger)
    leaderboard_message  = Column(BigInteger)

class BotRegions(Base):
    __tablename__ = 'bot_regions'

    guild_id  = Column(BigInteger, ForeignKey('bot_settings.guild_id'), primary_key=True, nullable=False)
    label     = Column(String(32), primary_key=True, nullable=False)
    emoji     = Column(String(32))
    index     = Column(SmallInteger, default=0)

class MMBotRanks(Base):
    __tablename__ = 'mm_bot_ranks'

    id             = Column(Integer, primary_key=True)
    guild_id       = Column(BigInteger, ForeignKey('bot_settings.guild_id'), nullable=False)
    mmr_threshold  = Column(Integer, nullable=False)
    role_id        = Column(BigInteger, nullable=False)
    timestamp      = Column(TIMESTAMP(timezone=True), server_default=func.now())

class MMBotQueueUsers(Base):
    __tablename__ = 'mm_bot_queue_users'

    id             = Column(Integer, primary_key=True)
    guild_id       = Column(BigInteger, nullable=False)
    user_id        = Column(BigInteger, nullable=False)
    queue_channel  = Column(BigInteger, nullable=False)
    queue_expiry   = Column(Integer)
    in_queue       = Column(Boolean, nullable=False, default=True)
    timestamp      = Column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(['guild_id', 'user_id'], ['mm_bot_users.guild_id', 'mm_bot_users.user_id']),
    )

class MMBotUsers(Base):
    __tablename__ = 'mm_bot_users'

    guild_id      = Column(BigInteger, primary_key=True, nullable=False)
    user_id       = Column(BigInteger, primary_key=True, nullable=False)
    display_name  = Column(String(32))
    region        = Column(String(32))
    registered    = Column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(['guild_id', 'region'], ['bot_regions.guild_id', 'bot_regions.label']),
    )

    summary_stats = relationship("MMBotUserSummaryStats", uselist=False, back_populates="user")

class MMBotUserNotifications(Base):
    __tablename__ = 'mm_bot_user_notifications'

    guild_id     = Column(BigInteger, primary_key=True, nullable=False)
    user_id      = Column(BigInteger, primary_key=True, nullable=False)
    queue_count  = Column(Integer, nullable=False)
    expiry       = Column(Integer, nullable=True)
    one_time     = Column(Boolean, nullable=False, default=False)

    __table_args__ = (
        ForeignKeyConstraint(['guild_id', 'user_id'], ['mm_bot_users.guild_id', 'mm_bot_users.user_id']),
    )

class MMBotBlockedUsers(Base):
    __tablename__ = 'mm_bot_blocked_users'

    id          = Column(Integer, primary_key=True)
    guild_id    = Column(BigInteger, nullable=False)
    user_id     = Column(BigInteger, nullable=False)
    blocked_by  = Column(BigInteger, nullable=False)
    reason      = Column(Text)
    expiration  = Column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(['guild_id', 'user_id'], ['mm_bot_users.guild_id', 'mm_bot_users.user_id']),
    )

class MMBotUserMatchStats(Base):
    __tablename__ = 'mm_bot_user_match_stats'

    id             = Column(Integer, primary_key=True)
    guild_id       = Column(BigInteger, nullable=False)
    user_id        = Column(BigInteger, nullable=False)
    match_id       = Column(Integer, nullable=False)
    mmr_before     = Column(Float)
    mmr_change     = Column(Float)
    games          = Column(Integer)
    win            = Column(Boolean)
    ct_start       = Column(Boolean)
    score          = Column(Integer)
    kills          = Column(Integer)
    deaths         = Column(Integer)
    assists        = Column(Integer)
    ping           = Column(Integer)
    rounds_played  = Column(Integer, default=0)
    abandoned      = Column(Boolean, default=False)
    timestamp      = Column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(['guild_id', 'user_id'], ['mm_bot_users.guild_id', 'mm_bot_users.user_id']),
        UniqueConstraint('guild_id', 'user_id', 'match_id', name='unique_guild_user_match'),
    )

class MMBotUserSummaryStats(Base):
    __tablename__ = 'mm_bot_user_summary_stats'

    guild_id        = Column(BigInteger, primary_key=True, nullable=False)
    user_id         = Column(BigInteger, primary_key=True, nullable=False)
    mmr             = Column(Float, default=900)
    games           = Column(Integer, default=0)
    wins            = Column(Integer, default=0)
    losses          = Column(Integer, default=0)
    ct_starts       = Column(Integer, default=0)
    top_score       = Column(Integer, default=0)
    top_kills       = Column(Integer, default=0)
    top_assists     = Column(Integer, default=0)
    total_score     = Column(Integer, default=0)
    total_kills     = Column(Integer, default=0)
    total_deaths    = Column(Integer, default=0)
    total_assists   = Column(Integer, default=0)

    __table_args__ = (
        ForeignKeyConstraint(['guild_id', 'user_id'], ['mm_bot_users.guild_id', 'mm_bot_users.user_id']),
    )
    
    user = relationship("MMBotUsers", back_populates="summary_stats")

class MMBotUserAbandons(Base):
    __tablename__ = 'mm_bot_user_abandons'

    id         = Column(Integer, primary_key=True, nullable=False)
    guild_id   = Column(BigInteger, nullable=False)
    user_id    = Column(BigInteger, nullable=False)
    match_id   = Column(Integer, ForeignKey('mm_bot_matches.id'), nullable=False)
    ignored    = Column(Boolean, nullable=False, default=False)
    timestamp  = Column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(['guild_id', 'user_id'], ['mm_bot_users.guild_id', 'mm_bot_users.user_id']),
    )

class MMBotMaps(Base):
    __tablename__ = 'mm_bot_maps'

    guild_id     = Column(BigInteger, ForeignKey('bot_settings.guild_id'), primary_key=True, nullable=False)
    map          = Column(String(32), primary_key=True, nullable=False)
    resource_id  = Column(String(32))
    media        = Column(Text, nullable=True)
    active       = Column(Boolean, nullable=False, default=True)
    order        = Column(SmallInteger)

class MMBotMods(Base):
    __tablename__ = 'mm_bot_mods'

    guild_id     = Column(BigInteger, ForeignKey('bot_settings.guild_id'), primary_key=True, nullable=False)
    mod          = Column(String(32), primary_key=True, nullable=False)
    resource_id  = Column(String(32))


##############
# MM Matches #
##############
class MMBotMatches(Base):
    __tablename__ = 'mm_bot_matches'

    id               = Column(Integer, primary_key=True)
    queue_channel    = Column(BigInteger, nullable=False)
    match_thread     = Column(BigInteger)
    match_message    = Column(BigInteger)
    maps_range       = Column(BigInteger, nullable=False, default=10)
    maps_phase       = Column(BigInteger, nullable=False, default=0)
    phase            = Column(sq_Enum(Phase), nullable=False, default=Phase.NONE)
    log_message      = Column(BigInteger)
    a_thread         = Column(BigInteger)
    b_thread         = Column(BigInteger)
    a_vc             = Column(BigInteger)
    b_vc             = Column(BigInteger)
    a_message        = Column(BigInteger)
    b_message        = Column(BigInteger)
    a_bans           = Column(ARRAY(String(32)))
    b_bans           = Column(ARRAY(String(32)))
    a_mmr            = Column(Float)
    b_mmr            = Column(Float)
    map              = Column(String(32))
    a_score          = Column(SmallInteger)
    b_score          = Column(SmallInteger)
    start_timestamp  = Column(TIMESTAMP(timezone=True), server_default=func.now())
    end_timestamp    = Column(TIMESTAMP(timezone=True))
    complete         = Column(Boolean, nullable=False, default=False)
    state            = Column(SmallInteger, nullable=False, default=1)
    b_side           = Column(sq_Enum(Side))
    serveraddr       = Column(String(51))

class MMBotUserBans(Base):
    __tablename__ = 'mm_bot_user_bans'

    id         = Column(Integer, primary_key=True)
    guild_id   = Column(BigInteger, nullable=False)
    user_id    = Column(BigInteger, nullable=False)
    match_id   = Column(Integer, ForeignKey('mm_bot_matches.id'), nullable=False)
    map        = Column(String(32), nullable=False)
    phase      = Column(sq_Enum(Phase), default=Phase.NONE)
    timestamp  = Column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(['guild_id', 'user_id'], ['mm_bot_users.guild_id', 'mm_bot_users.user_id']),
    )

class MMBotUserMapPicks(Base):

    __tablename__ = 'mm_bot_user_map_picks'

    id         = Column(Integer, primary_key=True)
    guild_id   = Column(BigInteger, nullable=False)
    user_id    = Column(BigInteger, nullable=False)
    match_id   = Column(Integer, ForeignKey('mm_bot_matches.id'), nullable=False)
    map        = Column(String(32), nullable=False)
    timestamp  = Column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('user_id', 'match_id', name='unique_user_match_map'),
        ForeignKeyConstraint(['guild_id', 'user_id'], ['mm_bot_users.guild_id', 'mm_bot_users.user_id']),
    )

class MMBotUserSidePicks(Base):
    __tablename__ = 'mm_bot_user_side_picks'

    id         = Column(Integer, primary_key=True)
    guild_id   = Column(BigInteger, nullable=False)
    user_id    = Column(BigInteger, nullable=False)
    match_id   = Column(Integer, ForeignKey('mm_bot_matches.id'), nullable=False)
    side       = Column(sq_Enum(Side), nullable=False)
    timestamp  = Column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('user_id', 'match_id', name='unique_user_match_side'),
        ForeignKeyConstraint(['guild_id', 'user_id'], ['mm_bot_users.guild_id', 'mm_bot_users.user_id']),
    )

class MMBotMatchPlayers(Base):
    __tablename__ = 'mm_bot_match_players'

    guild_id  = Column(BigInteger, primary_key=True, nullable=False)
    user_id   = Column(BigInteger, primary_key=True, nullable=False)
    match_id  = Column(Integer, primary_key=True, nullable=False)
    accepted  = Column(Boolean, nullable=False, default=False)
    team      = Column(sq_Enum(Team), nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(['guild_id', 'user_id'], ['mm_bot_users.guild_id', 'mm_bot_users.user_id']),
        ForeignKeyConstraint(['match_id'], ['mm_bot_matches.id']),
    )

    user_platform_mappings = relationship("UserPlatformMappings",
        primaryjoin="and_(MMBotMatchPlayers.guild_id == foreign(UserPlatformMappings.guild_id), MMBotMatchPlayers.user_id == foreign(UserPlatformMappings.user_id))")

