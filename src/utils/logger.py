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

import sys
import inspect
from datetime import datetime
from pprint import pprint


class VariableLog:
    variables_to_value = {}

    @classmethod
    def debug(cls, value, message: str=""):
        if Logger.get_level() > Logger.DEBUG: return
        
        frame = inspect.currentframe().f_back
        variable_name = None
        for name, val in frame.f_locals.items():
            if val is value:
                variable_name = name
                break
        
        if variable_name is None:
            Logger.debug(f"{message}{' ' if message else ''}Value => {value}")
            return

        if variable_name not in cls.variables_to_value or cls.variables_to_value[variable_name] != value:
            cls.variables_to_value[variable_name] = value
            Logger.debug(f"{message}{' ' if message else ''}{variable_name} => {value}")


class Logger:
    _log_level = 2

    DEBUG = 1
    INFO = 2
    WARNING = 3
    ERROR = 4
    CRITICAL = 5
    
    _COLORS = {
        'DEBUG': '\033[94m',    # Blue
        'INFO': '\033[92m',     # Green
        'WARNING': '\033[93m',  # Yellow
        'ERROR': '\033[91m',    # Red
        'CRITICAL': '\033[95m', # Magenta
        'RESET': '\033[0m',     # Reset color
        'BLACK': '\033[30;44m', # Black
        'GRAY': '\033[0;90m',   # Bold gray
        'PURPLE': '\033[0;35m'  # Purple
    }

    @staticmethod
    def _get_timestamp():
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    @staticmethod
    def _get_caller_class():
        current_frame = inspect.currentframe()
        try:
            for _ in range(3):  # Skip Logger frames
                if current_frame is not None:
                    current_frame = current_frame.f_back
            
            if current_frame is not None:
                frame_info = inspect.getframeinfo(current_frame)
                module = inspect.getmodule(current_frame)
                if module:
                    for name, obj in module.__dict__.items():
                        if inspect.isclass(obj):
                            for attr, value in obj.__dict__.items():
                                if getattr(value, '__code__', None) is current_frame.f_code:
                                    return obj.__name__
                return frame_info.function
        finally:
            del current_frame  # Avoid reference cycles

        return ''

    @classmethod
    def _log(cls, level, message):
        timestamp = cls._get_timestamp()
        caller_class = cls._get_caller_class()
        color = cls._COLORS.get(level, cls._COLORS['RESET'])
        reset = cls._COLORS['RESET']
        black = cls._COLORS['BLACK']
        gray = cls._COLORS['GRAY']
        purple = cls._COLORS['PURPLE']
        print(f"{gray}[{black}{timestamp}{gray}][{purple}{caller_class}{gray}] {color}|{level}| {reset}{message}{reset}", file=sys.stderr)
    
    @classmethod
    def get_level(cls):
        return cls._log_level

    @classmethod
    def set_level(cls, level: int):
        cls._log_level = level
    
    @classmethod
    def pretty(cls, obj):
        if cls._log_level > cls.DEBUG:
            return
        pprint(obj)

    @classmethod
    def debug(cls, message):
        if cls._log_level > cls.DEBUG:
            return
        cls._log('DEBUG', message)

    @classmethod
    def info(cls, message):
        if cls._log_level > cls.INFO:
            return
        cls._log('INFO', message)

    @classmethod
    def warning(cls, message):
        if cls._log_level > cls.WARNING:
            return
        cls._log('WARNING', message)

    @classmethod
    def error(cls, message):
        if cls._log_level > cls.ERROR:
            return
        cls._log('ERROR', message)

    @classmethod
    def critical(cls, message):
        if cls._log_level > cls.CRITICAL:
            return
        cls._log('CRITICAL', message)