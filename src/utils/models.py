from enum import Enum
from sqlalchemy import (
    Column, 
    BigInteger, 
    Integer, 
    String, 
    Boolean,
    SmallInteger, 
    Text, 
    TIMESTAMP, 
    ARRAY, 
    Enum as sq_Enum,
    ForeignKey, 
    ForeignKeyConstraint,
    UniqueConstraint,
    func
)
from sqlalchemy.ext.declarative import declarative_base

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
    T = 0
    CT = 1


class Platform(Enum):
    STEAM = "steam"
    PLAYSTATION = "playstation"


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

class BotRegions(Base):
    __tablename__ = 'bot_regions'

    guild_id  = Column(BigInteger, ForeignKey('bot_settings.guild_id'), primary_key=True, nullable=False)
    label     = Column(String(32), primary_key=True, nullable=False)
    emoji     = Column(String(32))
    index     = Column(SmallInteger, default=0)

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
    mmr           = Column(Integer, nullable=False, default=800)
    games         = Column(Integer, default=0)
    wins          = Column(Integer, default=0)
    loss          = Column(Integer, default=0)
    team_a        = Column(Integer, default=0)
    registered    = Column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(['guild_id', 'region'], ['bot_regions.guild_id', 'bot_regions.label']),
    )

class MMBotMaps(Base):
    __tablename__ = 'mm_bot_maps'

    guild_id  = Column(BigInteger, ForeignKey('bot_settings.guild_id'), primary_key=True, nullable=False)
    map       = Column(String(32), primary_key=True, nullable=False)
    media     = Column(Text, nullable=True)
    active    = Column(Boolean, nullable=False, default=True)
    order     = Column(SmallInteger)


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
    a_thread         = Column(BigInteger)
    b_thread         = Column(BigInteger)
    a_vc             = Column(BigInteger)
    b_vc             = Column(BigInteger)
    a_message        = Column(BigInteger)
    b_message        = Column(BigInteger)
    a_bans           = Column(ARRAY(String(32)))
    b_bans           = Column(ARRAY(String(32)))
    a_mmr            = Column(Integer)
    b_mmr            = Column(Integer)
    map              = Column(String(32))
    a_score          = Column(SmallInteger)
    b_score          = Column(SmallInteger)
    start_timestamp  = Column(TIMESTAMP(timezone=True), server_default=func.now())
    end_timestamp    = Column(TIMESTAMP(timezone=True))
    complete         = Column(Boolean, nullable=False, default=False)
    state            = Column(SmallInteger, nullable=False, default=1)
    b_side           = Column(sq_Enum(Side))

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

class MMBotMatchUsers(Base):
    __tablename__ = 'mm_bot_match_users'

    guild_id  = Column(BigInteger, primary_key=True, nullable=False)
    user_id   = Column(BigInteger, primary_key=True, nullable=False)
    match_id  = Column(Integer, primary_key=True, nullable=False)
    accepted  = Column(Boolean, nullable=False, default=False)
    team      = Column(sq_Enum(Team), nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(['guild_id', 'user_id'], ['mm_bot_users.guild_id', 'mm_bot_users.user_id']),
        ForeignKeyConstraint(['match_id'], ['mm_bot_matches.id']),
    )


##############
# MM HISTORY #
##############
class MMBotMMRHistory(Base):
    __tablename__ = 'mm_bot_mmr_history'

    id         = Column(Integer, primary_key=True)
    guild_id   = Column(BigInteger, nullable=False)
    user_id    = Column(BigInteger, nullable=False)
    mmr        = Column(Integer, nullable=False)
    mmr_delta  = Column(Integer, nullable=False)
    timestamp  = Column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(['guild_id', 'user_id'], ['mm_bot_users.guild_id', 'mm_bot_users.user_id']),
    )
