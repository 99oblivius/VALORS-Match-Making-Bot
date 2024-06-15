from sqlalchemy import (
    Column, 
    BigInteger, 
    Integer, 
    String, 
    Boolean,
    SmallInteger, 
    Text, 
    TIMESTAMP, 
    ForeignKey, 
    ForeignKeyConstraint,
    func
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

class BotSettings(Base):
    __tablename__ = 'bot_settings'

    guild_id            = Column(BigInteger, primary_key=True, nullable=False)
    staff_channel       = Column(BigInteger)
    log_channel         = Column(BigInteger)
    
    mm_buttons_channel  = Column(BigInteger)
    mm_buttons_message  = Column(BigInteger)
    mm_buttons_periods  = Column(Text)
    mm_accept_period    = Column(SmallInteger, nullable=False, default=180)

    mm_queue_channel    = Column(BigInteger)
    mm_queue_reminder   = Column(Integer, nullable=False, default=180)
    mm_log_channel      = Column(BigInteger)
    mm_lfg_role         = Column(BigInteger)
    mm_staff_role       = Column(BigInteger)

    region_channel      = Column(BigInteger)
    region_message      = Column(BigInteger)

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
    mmr           = Column(Integer, nullable=False, default=800000)
    games         = Column(Integer, default=0)
    wins          = Column(Integer, default=0)
    loss          = Column(Integer, default=0)
    team_a        = Column(Integer, default=0)
    registered    = Column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(['guild_id', 'region'], ['bot_regions.guild_id', 'bot_regions.label']),
    )


##############
# MM Matches #
##############
class MMBotMatches(Base):
    __tablename__ = 'mm_bot_matches'

    id               = Column(Integer, primary_key=True)
    queue_channel    = Column(BigInteger, nullable=False)
    match_thread     = Column(BigInteger)
    a_thread         = Column(BigInteger)
    b_thread         = Column(BigInteger)
    a_vc             = Column(BigInteger)
    b_vc             = Column(BigInteger)
    map              = Column(String(32))
    a_score          = Column(SmallInteger)
    b_score          = Column(SmallInteger)
    start_timestamp  = Column(TIMESTAMP(timezone=True), server_default=func.now())
    end_timestamp    = Column(TIMESTAMP(timezone=True))
    complete         = Column(Boolean, nullable=False, default=False)
    state            = Column(SmallInteger, nullable=False, default=0)

class MMBotMatchBans(Base):
    __tablename__ = 'mm_bot_match_bans'

    guild_id  = Column(BigInteger, primary_key=True, nullable=False)
    user_id   = Column(BigInteger, primary_key=True, nullable=False)
    match_id  = Column(Integer, ForeignKey('mm_bot_matches.id'), primary_key=True, nullable=False)
    map       = Column(String(32), nullable=False)
    phase     = Column(SmallInteger, default=0)

    __table_args__ = (
        ForeignKeyConstraint(['guild_id', 'user_id'], ['mm_bot_users.guild_id', 'mm_bot_users.user_id']),
    )

class MMBotMatchUsers(Base):
    __tablename__ = 'mm_bot_match_users'

    guild_id  = Column(BigInteger, primary_key=True, nullable=False)
    user_id   = Column(BigInteger, primary_key=True, nullable=False)
    match_id  = Column(Integer, primary_key=True, nullable=False)
    accepted  = Column(Boolean, nullable=False, default=False)
    team      = Column(String(1), nullable=True)

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
