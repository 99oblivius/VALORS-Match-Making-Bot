# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # 
# VALORS Match Making Bot is a discord based match making automation and management service #
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # 
# 
# Copyright (C) 2024  Julian von Virag, <projects@oblivius.dev>
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

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

    MATCH_STARTING          = auto()
    LOG_PICKS               = auto()
    
    MATCH_FIND_SERVER       = auto()
    MATCH_WAIT_FOR_PLAYERS  = auto()
    MATCH_START_SND         = auto()

    LOG_MATCH_HAPPENING     = auto()

    MATCH_WAIT_FOR_END      = auto()
    MATCH_CLEANUP           = auto()

    CLEANUP                 = auto()
    LOG_END                 = auto()
    FINISHED                = auto()