from enum import IntEnum, auto

class MatchState(IntEnum):
    def __str__(self):
        return self.name
    
    NOT_STARTED             = auto()
    CREATE_MATCH_THREAD     = auto()
    ACCEPT_PLAYERS          = auto()

    MAKE_TEAMS              = auto()
    
    MAKE_TEAM_VC_A          = auto()
    MAKE_TEAM_VC_B          = auto()
    MAKE_TEAM_THREAD_A      = auto()
    MAKE_TEAM_THREAD_B      = auto()

    BANNING_START           = auto()
    A_BANS                  = auto()

    BAN_SWAP                = auto()
    B_BANS                  = auto()

    A_PICK                  = auto()
    B_PICK                  = auto()

    MATCH_STARTING          = auto()
    MATCH_FIND_SERVER       = auto()
    MATCH_WAIT_FOR_PLAYERS  = auto()
    MATCH_START_SND         = auto()
    MATCH_WAIT_FOR_END      = auto()
    MATCH_CLEANUP           = auto()
    MATCH_SCORES            = auto()

    CLEANUP                 = auto()
    FINISHED                = auto()