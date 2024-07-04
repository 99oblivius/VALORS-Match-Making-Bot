import sys
import inspect
from datetime import datetime
from pprint import pprint


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
        'BLACK': '\033[0;100m',  # Black
        'GRAY': '\033[0;90m',   # Bold gray
        'PURPLE': '\033[0;35m'  # Purple
    }

    @staticmethod
    def _get_timestamp():
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    @staticmethod
    def _get_caller_class():
        stack = inspect.stack()
        for frame_info in stack[2:]:  # Start from two frames up
            frame = frame_info[0]
            if 'self' in frame.f_locals:
                class_name = frame.f_locals['self'].__class__.__name__
                if class_name != 'ColorLogger':
                    return class_name
            elif 'cls' in frame.f_locals:
                class_name = frame.f_locals['cls'].__name__
                if class_name != 'ColorLogger':
                    return class_name
            code = frame.f_code
            if code.co_name != '<module>':  # Skip module-level calls
                for var in frame.f_locals.values():
                    if inspect.isclass(var) and code.co_name in var.__dict__:
                        class_name = var.__name__
                        if class_name != 'ColorLogger':
                            return class_name
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
        print(f"{gray}[{black}{timestamp}{gray}][{purple}{caller_class}{gray}]{color}{level} {reset}{message}{reset}", file=sys.stderr)
    
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