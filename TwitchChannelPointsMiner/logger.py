import logging
import os
import platform
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import emoji
from colorama import Fore, init

from TwitchChannelPointsMiner.utils import remove_emoji


class GlobalFormatter(logging.Formatter):
    def __init__(self, *, fmt, datefmt=None, print_emoji=True, print_colored=False):
        self.print_emoji = print_emoji
        self.print_colored = print_colored
        logging.Formatter.__init__(self, fmt=fmt, datefmt=datefmt)

    def format(self, record):
        record.emoji_is_present = (
            record.emoji_is_present if hasattr(record, "emoji_is_present") else False
        )
        if (
            hasattr(record, "emoji")
            and self.print_emoji is True
            and record.emoji_is_present is False
        ):
            record.msg = emoji.emojize(
                f"{record.emoji}  {record.msg.strip()}", use_aliases=True
            )
            record.emoji_is_present = True

        if self.print_emoji is False:
            if "\u2192" in record.msg:
                record.msg = record.msg.replace("\u2192", "-->")

            # With the update of Stream class, the Stream Title may contain emoji
            # Full remove using a method from utils.
            record.msg = remove_emoji(record.msg)

        if self.print_colored and hasattr(record, "color"):
            record.msg = f"{record.color}{record.msg}"

        return super().format(record)


# Fore: BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE, RESET.
class ColorPalette(object):
    STREAMER_ONLINE = Fore.RESET
    STREAMER_OFFLINE = Fore.RESET

    GAIN_FOR_RAID = Fore.RESET
    GAIN_FOR_CLAIM = Fore.RESET
    GAIN_FOR_WATCH = Fore.RESET
    GAIN_FOR_WATCH_STREAK = Fore.RESET

    BET_WIN = Fore.GREEN
    BET_LOSE = Fore.RED
    BET_REFUND = Fore.RESET
    BET_FILTERS = Fore.RESET
    BET_GENERAL = Fore.RESET
    BET_FAILED = Fore.RESET
    BET_START = Fore.RESET

    def __init__(self, **kwargs):
        for k in kwargs:
            if k.upper() in dir(self) and getattr(self, k.upper()) is not None:
                if kwargs[k] in [
                    Fore.BLACK,
                    Fore.RED,
                    Fore.GREEN,
                    Fore.YELLOW,
                    Fore.BLUE,
                    Fore.MAGENTA,
                    Fore.CYAN,
                    Fore.WHITE,
                    Fore.RESET,
                ]:
                    setattr(self, k.upper(), kwargs[k])
                elif kwargs[k].upper() in [
                    "BLACK",
                    "RED",
                    "GREEN",
                    "YELLOW",
                    "BLUE",
                    "MAGENTA",
                    "CYAN",
                    "WHITE",
                    "RESET",
                ]:
                    setattr(self, k.upper(), getattr(Fore, kwargs[k].upper()))

    def get(self, key):
        color = getattr(self, key.upper()) if key.upper() in dir(self) else None
        return Fore.RESET if color is None else color


class LoggerSettings:
    def __init__(
        self,
        save: bool = True,
        less: bool = False,
        console_level: int = logging.INFO,
        file_level: int = logging.DEBUG,
        emoji: bool = platform.system() != "Windows",
        colored: bool = False,
        color_palette: ColorPalette = ColorPalette(),
    ):
        self.save = save
        self.less = less
        self.console_level = console_level
        self.file_level = file_level
        self.emoji = emoji
        self.colored = colored
        self.color_palette = color_palette


def configure_loggers(username, settings):
    if settings.colored is True:
        init(autoreset=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(settings.console_level)
    console_handler.setFormatter(
        GlobalFormatter(
            fmt=(
                "%(asctime)s - %(levelname)s - [%(funcName)s]: %(message)s"
                if settings.less is False
                else "%(asctime)s - %(message)s"
            ),
            datefmt=(
                "%d/%m/%y %H:%M:%S" if settings.less is False else "%d/%m %H:%M:%S"
            ),
            print_emoji=settings.emoji,
            print_colored=settings.colored,
        )
    )

    if settings.save is True:
        logs_path = os.path.join(Path().absolute(), "logs")
        Path(logs_path).mkdir(parents=True, exist_ok=True)
        logs_file = os.path.join(
            logs_path,
            f"{username}.log",
        )
        file_handler = TimedRotatingFileHandler(
            logs_file,
            when="D",
            interval=1,
            backupCount=7,
            encoding="utf-8",
            delay=False,
        )
        file_handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s - %(levelname)s - %(name)s - [%(funcName)s]: %(message)s",
                datefmt="%d/%m/%y %H:%M:%S",
            )
        )
        file_handler.setLevel(settings.file_level)

        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)
        return logs_file
    else:
        root_logger.addHandler(console_handler)
        return None
