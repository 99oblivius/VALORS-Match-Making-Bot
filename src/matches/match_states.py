from enum import IntEnum, auto

class MatchState(IntEnum):
    def __str__(self):
        return self.name
    
    NOT_STARTED             = auto()
    CREATE_MATCH_THREAD     = auto()
    ACCEPT_PLAYERS          = auto()

    MAKE_TEAMS              = auto()

    MAKE_TEAM_THREAD_A      = auto()
    MAKE_THREAD_MESSAGE_A   = auto()

    MAKE_TEAM_THREAD_B      = auto()
    MAKE_THREAD_MESSAGE_B   = auto()
    
    MAKE_TEAM_VC_A          = auto()
    MAKE_TEAM_VC_B          = auto()

    BANNING_START           = auto()
    ADD_TEAM_A              = auto()
    A_BANS                  = auto()

    BAN_SWAP                = auto()
    ADD_TEAM_B              = auto()
    B_BANS                  = auto()
    

    CLEANUP                 = auto()
