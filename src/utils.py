import asyncio
import functools
import logging
import os
import random
import re
import threading
from contextvars import ContextVar
from typing import Optional, Callable, Tuple
from aiogram import types as tgtypes

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


async def generate_post_pretty_html(message: tgtypes.Message, include_forward_from: bool = True):
    text = ''
    if include_forward_from and message.is_forward():
        forward_from, url = await extract_forward_source(message)
        if url:
            link = f'<a href="{url}" target="_blank" class="forward-source">{forward_from}</a>'
        else:
            link = f'<span class="forward-source">{forward_from}</span>'


        text += f'<p class="forward-from">Forwarded from: {link}</p>'

    text_paragraphs = message.html_text.split('\n\n') if message.text or message.caption else []
    for p in text_paragraphs:
        url_regex = r"(?<!href=[\"'])(https?:\/\/(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,16}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*))"
        p = re.sub(url_regex, r'<a href="\g<1>" rel="nofollow" target="_blank">\g<1></a>', p)
        p = p.replace("\n", "<br>")
        text += '<p>{0}</p>'.format(p)
    return text


def guess_title(text: str) -> str:
    if not text:
        return ''
    title_threshold = 100
    paragraph_chunks = text.split('\n')
    if len(paragraph_chunks) and len(paragraph_chunks[0]) < title_threshold:
        return paragraph_chunks[0]

    sentence_chunks = re.split(r'[.!?]', text)
    if len(sentence_chunks) and len(sentence_chunks[0]) < title_threshold:
        return sentence_chunks[0]

    return text[:60]  # optimal len


async def extract_forward_source(message: tgtypes.Message, ) -> Tuple[str, str]:
    if message.forward_sender_name is not None:
        text = message.forward_sender_name
    elif message.forward_from is not None:
        text = message.forward_from.full_name
    elif message.forward_from_chat is not None:
        text = message.forward_from_chat.full_name
    else:
        text = ''

    if message.forward_from is not None:
        if message.forward_from.username:
            link = f'https://t.me/{message.forward_from.username}'
        else:
            link = f'tg://user?id={message.forward_from.id}'
    elif message.forward_from_chat is not None:
        link = await message.forward_from_chat.get_url()
    else:
        link = ''

    return text, link





# This one matches against strins that contains ONLY one URL
URL_REGEX_STRICT = r"^https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)$"
# This used to find URLs in text
URL_REGEX = r"https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)"

IS_DEV = os.getenv('RAINDROPBOT_DEV', 'false') == 'true'
RUN_IN_DOCKER = os.getenv('RUN_IN_DOCKER', 'false') == 'true'
