from sqlalchemy import Column, BigInteger, Integer, String, SmallInteger, Text, TIMESTAMP, ForeignKey
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class BotSettings(Base):
    __tablename__ = 'bot_settings'

    guild_id            = Column(BigInteger, primary_key=True, nullable=False)
    mm_buttons_channel  = Column(BigInteger)
    mm_queue_channel    = Column(BigInteger)
    mm_queue_message    = Column(BigInteger)
    mm_queue_periods    = Column(Text)
    mm_log_channel      = Column(BigInteger)
    staff_channel       = Column(BigInteger)
    log_channel         = Column(BigInteger)

class MMBotQueueUsers(Base):
    __tablename__ = 'mm_bot_queue_users'

    user_id        = Column(BigInteger, primary_key=True, nullable=False)
    queue_channel  = Column(BigInteger, primary_key=True, nullable=False)
    queue_expiry   = Column(Integer)

class MMBotUsers(Base):
    __tablename__ = 'mm_bot_users'

    guild_id          = Column(BigInteger, primary_key=True, nullable=False)
    user_id           = Column(BigInteger, primary_key=True, nullable=False)
    display_name      = Column(String(32))
    mmr               = Column(Integer, nullable=False, default=800000)
    games             = Column(Integer, default=0)
    wins              = Column(Integer, default=0)
    loss              = Column(Integer, default=0)
    team_a            = Column(Text)
    joined_timestamp  = Column(TIMESTAMP(timezone=True), default='now()')

class MMBotMatches(Base):
    __tablename__ = 'mm_bot_matches'

    id               = Column(Integer, primary_key=True, autoincrement=True)
    match_thread     = Column(BigInteger)
    a_thread         = Column(BigInteger)
    b_thread         = Column(BigInteger)
    a_vc             = Column(BigInteger)
    b_vc             = Column(BigInteger)
    map              = Column(String(32), nullable=False)
    a_score          = Column(SmallInteger)
    b_score          = Column(SmallInteger)
    start_timestamp  = Column(Integer, nullable=False)
    end_timestamp    = Column(Integer)
    complete         = Column(SmallInteger, default=0)

class MMBotMatchBans(Base):
    __tablename__ = 'mm_bot_match_bans'

    match_id  = Column(Integer, ForeignKey('mm_bot_matches.id'))
    user_id   = Column(BigInteger, ForeignKey('mm_bot_users.user_id'), nullable=False, primary_key=True)
    map       = Column(String(32), nullable=False, primary_key=True)
    phase     = Column(SmallInteger, default=0)

class MMBotMatchUsers(Base):
    __tablename__ = 'mm_bot_match_users'

    user_id   = Column(BigInteger, ForeignKey('mm_bot_users.user_id'), nullable=False, primary_key=True)
    match_id  = Column(BigInteger, ForeignKey('mm_bot_matches.id'), nullable=False, primary_key=True)
    team      = Column(String(1), nullable=False)

class MMBotMMRHistory(Base):
    __tablename__ = 'mm_bot_mmr_history'

    id         = Column(Integer, primary_key=True, autoincrement=True)
    guild_id   = Column(BigInteger, nullable=False)
    user_id    = Column(BigInteger, ForeignKey('mm_bot_users.user_id'), nullable=False)
    mmr        = Column(Integer, nullable=False)
    mmr_delta  = Column(Integer, nullable=False)
    timestamp  = Column(TIMESTAMP(timezone=True), default='now()')
