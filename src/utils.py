import asyncio
import functools
import logging
import os
import random
import threading
from contextvars import ContextVar
from typing import Optional, Callable

LOG_FORMAT_ASYNC = '[%(asctime)s][%(levelname)s][%(name)s][CTX %(async_context)s] %(message)s'
LOG_FORMAT_SYNC = '[%(asctime)s][%(levelname)s][%(name)s][PID %(process)d][CTX %(threadName)s] %(message)s'

GlobalAsyncLoggingContext: ContextVar[str] = ContextVar('async_context', default='global')


class AsyncAdapter(logging.LoggerAdapter):
    def __init__(self, logger, extra, async_context):
        super().__init__(logger, extra)
        self.async_context = async_context

    def process(self, msg, kwargs):
        if self.async_context:
            kwargs.setdefault('extra', {})['async_context'] = GlobalAsyncLoggingContext.get()
        else:
            kwargs.setdefault('extra', {})['async_context'] = threading.current_thread().name
        return msg, kwargs


def get_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    try:
        asyncio.get_running_loop()
        async_context = True
    except RuntimeError:
        async_context = False

    if not logger.hasHandlers():
        formatter = logging.Formatter(LOG_FORMAT_ASYNC if async_context else LOG_FORMAT_SYNC)

        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    return AsyncAdapter(logger, {'async_context': 'global'}, async_context)


def generate_random_id(count=10):
    return ''.join(random.choices(['1', '2', '3', '4', '5', '6', '7', '8', '9', '0',
                                   'a', 'b', 'c', 'd', 'e', 'f'], k=count))


def set_logger_context_on_enter(logger: Optional[AsyncAdapter] = None, enter_exit_messages_level: int = logging.INFO,
                                generate_id: Callable = generate_random_id):
    def wrapper(func):
        @functools.wraps(func)
        async def wrapped(*args, **kwargs):
            context = generate_id()
            GlobalAsyncLoggingContext.set(context)
            if logger is not None and enter_exit_messages_level:
                logger.log(enter_exit_messages_level, f'Entering function {func.__name__}; context set to {context}')

            result = await func(*args, **kwargs)

            if logger is not None and enter_exit_messages_level:
                logger.log(enter_exit_messages_level, f'Function {func.__name__} ({context}) returned')
            return result
        return wrapped
    return wrapper


# This one matches against strins that contains ONLY one URL
URL_REGEX_STRICT = r"^https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)$"
# This used to find URLs in text
URL_REGEX = r"https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)"

IS_DEV = os.getenv('RAINDROPBOT_DEV', 'false') == 'true'
RUN_IN_DOCKER = os.getenv('RUN_IN_DOCKER', 'false') == 'true'
