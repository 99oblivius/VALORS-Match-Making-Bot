from enum import IntEnum, auto

class MatchState(IntEnum):
    NOT_STARTED = auto()
    CREATE_MATCH_THREAD = auto()
    ACCEPT_PLAYERS = auto()
    ACCEPT_WAIT = auto()

    def __str__(self):
        return self.name
