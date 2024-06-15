from enum import IntEnum, auto

class MatchState(IntEnum):
    NOT_STARTED = auto()
    CREATE_MATCH_THREAD = auto()
    ACCEPT_PLAYERS = auto()
    ACCEPT_WAIT = auto()
    MAKE_TEAM_THREAD_A = auto()
    MAKE_TEAM_THREAD_B = auto()
    MAKE_TEAM_VC_A = auto()
    MAKE_TEAM_VC_B = auto()

    CLEANUP = auto()

    def __str__(self):
        return self.name
