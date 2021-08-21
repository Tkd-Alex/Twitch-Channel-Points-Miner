import logging
import time
from enum import Enum, auto
from threading import Thread

from irc.bot import SingleServerIRCBot

from TwitchChannelPointsMiner.constants import IRC, IRC_PORT

logger = logging.getLogger(__name__)


class ChatPresence(Enum):
    ALWAYS = auto()
    NEVER = auto()
    ONLINE = auto()
    OFFLINE = auto()

    def __str__(self):
        return self.name


class ClientIRC(SingleServerIRCBot):
    def __init__(self, username, token, channel):
        self.token = token
        self.channel = "#" + channel
        self.__active = False

        super(ClientIRC, self).__init__(
            [(IRC, IRC_PORT, f"oauth:{token}")], username, username
        )

    def on_welcome(self, client, event):
        client.join(self.channel)

    def start(self):
        self.__active = True
        self._connect()
        while self.__active:
            try:
                self.reactor.process_once(timeout=0.2)
                time.sleep(0.01)
            except Exception as e:
                logger.error(
                    f"Exception raised: {e}. Thread is active: {self.__active}"
                )

    def die(self, msg="Bye, cruel world!"):
        self.connection.disconnect(msg)
        self.__active = False

    """
    def on_join(self, connection, event):
        logger.info(f"Event: {event}", extra={"emoji": ":speech_balloon:"})

    def on_pubmsg(self, client, message):
        logger.info(f"Message: {message}", extra={"emoji": ":speech_balloon:"})
    """


class ThreadChat(Thread):
    def __deepcopy__(self, memo):
        return None

    def __init__(self, username, token, channel):
        super(ThreadChat, self).__init__()

        self.username = username
        self.token = token
        self.channel = channel

        self.chat_irc = None

    def run(self):
        self.chat_irc = ClientIRC(self.username, self.token, self.channel)
        logger.info(
            f"Join IRC Chat: {self.channel}", extra={"emoji": ":speech_balloon:"}
        )
        self.chat_irc.start()

    def stop(self):
        if self.chat_irc is not None:
            logger.info(
                f"Leave IRC Chat: {self.channel}", extra={"emoji": ":speech_balloon:"}
            )
            self.chat_irc.die()
