import sys
import inspect
from datetime import datetime

class ColorLogger:
    COLORS = {
        'DEBUG': '\033[94m',    # Blue
        'INFO': '\033[92m',     # Green
        'WARNING': '\033[93m',  # Yellow
        'ERROR': '\033[91m',    # Red
        'CRITICAL': '\033[95m', # Magenta
        'RESET': '\033[0m',     # Reset color
        'BLACK': '\033[0;90m',  # Black
        'GRAY': '\033[1;93m',   # Bold gray
        'PURPLE': '\033[0;35m'  # Purple
    }

    @staticmethod
    def _get_timestamp():
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    @staticmethod
    def _get_caller_class():
        stack = inspect.stack()
        frame = stack[2]  # The frame of the method that called our logger
        try:
            class_name = frame[0].f_locals['self'].__class__.__name__
        except KeyError:
            class_name = ''
        return f"[{class_name}]" if class_name else ''

    @classmethod
    def _log(cls, level, message):
        timestamp = cls._get_timestamp()
        caller_class = cls._get_caller_class()
        color = cls.COLORS.get(level, cls.COLORS['RESET'])
        reset = cls.COLORS['RESET']
        black = cls.COLORS['BLACK']
        purple = cls.COLORS['PURPLE']
        gray = cls.COLORS['GRAY']
        print(f"{purple}[{timestamp}{purple}] {black}[{gray}{caller_class}{black}] {color}{level}{reset}: {message}{reset}", file=sys.stderr)

    @classmethod
    def debug(cls, message):
        cls._log('DEBUG', message)

    @classmethod
    def info(cls, message):
        cls._log('INFO', message)

    @classmethod
    def warning(cls, message):
        cls._log('WARNING', message)

    @classmethod
    def error(cls, message):
        cls._log('ERROR', message)

    @classmethod
    def critical(cls, message):
        cls._log('CRITICAL', message)