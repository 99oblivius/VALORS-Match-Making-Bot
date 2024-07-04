from enum import IntEnum, auto

class MatchState(IntEnum):
    def __str__(self):
        return self.name
    
    NOT_STARTED             = auto()
    CREATE_MATCH_THREAD     = auto()
    ACCEPT_PLAYERS          = auto()

    MAKE_TEAMS              = auto()
    LOG_MATCH               = auto()
    
    MAKE_TEAM_VC_A          = auto()
    MAKE_TEAM_VC_B          = auto()
    MAKE_TEAM_THREAD_A      = auto()
    MAKE_TEAM_THREAD_B      = auto()

    BANNING_START           = auto()
    A_BANS                  = auto()

    BAN_SWAP                = auto()
    B_BANS                  = auto()

    LOG_BANS                = auto()

    PICKING_START           = auto()
    A_PICK                  = auto()
    PICK_SWAP               = auto()
    B_PICK                  = auto()

    LOG_PICKS               = auto()

    MATCH_STARTING          = auto()
    MATCH_FIND_SERVER       = auto()
    MATCH_WAIT_FOR_PLAYERS  = auto()
    MATCH_START_SND         = auto()

    LOG_MATCH_HAPPENING     = auto()

    MATCH_WAIT_FOR_END      = auto()
    MATCH_CLEANUP           = auto()

    CLEANUP                 = auto()
    LOG_END                 = auto()
    FINISHED                = auto()