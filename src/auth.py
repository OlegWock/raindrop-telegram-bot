import os

from aiogram import types as tgtypes
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.dispatcher.handler import CancelHandler, current_handler
from motor import motor_asyncio

from db import User
from utils import get_logger

logger = get_logger('bot')


class UserAuthMiddleware(BaseMiddleware):
    def __init__(self, db: motor_asyncio.AsyncIOMotorDatabase):
        super().__init__()
        self.db = db

    async def on_process_message(self, message: tgtypes.Message, data: dict):
        admin_id = int(os.getenv('ADMIN_TELEGRAM_ID', -1))
        handler = current_handler.get()

        logger.info(f'Processing message from user {message.from_user.id}')

        if handler and getattr(handler, 'only_for_admin', False) and admin_id != message.from_user.id:
            await message.reply('This feature available only for admin!')
            raise CancelHandler()

        user = await User.get_by_telegram_id(self.db, message.from_user.id)
        if user is None:
            if handler and getattr(handler, 'only_for_registered_users', False):
                await message.reply('Sorry, this function is available only for registered users. '
                                    'Please check /help for instructions')
                raise CancelHandler()

        data['user'] = user

    async def on_pre_process_inline_query(self, inline_query: tgtypes.InlineQuery, data: dict):
        logger.info(f'Pre processing inline query from {inline_query.from_user.id}')
        user = await User.get_by_telegram_id(self.db, inline_query.from_user.id)

        data['user'] = user


def only_for_registered(func):
    setattr(func, 'only_for_registered_users', True)
    return func


def only_for_admin(func):
    setattr(func, 'only_for_admin', True)
    return func
