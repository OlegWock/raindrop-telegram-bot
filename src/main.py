import asyncio
import hashlib
import os
from typing import Optional

from aiogram import Bot, Dispatcher, types as tgtypes
from aiogram import filters
from aiogram.dispatcher import FSMContext
from bson import ObjectId

from motor import motor_asyncio

from db import get_db, User, get_fsm_storage
from auth import UserAuthMiddleware, only_for_registered, only_for_admin
from raindrop_api import RaindropApi, SpecialCollectionIds, SortOrder
from fsm import ConfigFlow, SettingsFlow
from utils import get_logger, URL_REGEX, IS_DEV

logger = get_logger('bot')


class RaindropioBot:
    def __init__(self, event_loop: asyncio.AbstractEventLoop):
        bot_token = os.getenv('BOT_TOKEN', None)

        if bot_token is None:
            raise ValueError("You forgot to set BOT_TOKEN variable")

        self.loop = event_loop
        self.bot = Bot(token=bot_token)
        self.dispatcher = Dispatcher(self.bot, storage=get_fsm_storage())
        self.db = None  # type: motor_asyncio.AsyncIOMotorDatabase

    def attach_listeners(self):
        self.register_command_and_text_handlers(self.on_help, 'help')
        self.register_command_and_text_handlers(self.on_help, 'start')

        self.register_command_and_text_handlers(self.on_global_cancel, 'cancel', state='*')
        self.dispatcher.register_message_handler(self.on_global_cancel,
                                                 filters.Text(equals='❌ cancel', ignore_case=True), state='*')

        self.register_command_and_text_handlers(self.on_config_init, 'config')

        self.dispatcher.register_message_handler(self.process_api_key, state=ConfigFlow.waiting_for_api_key)

        self.register_command_and_text_handlers(self.on_settings_init, 'settings')

        self.dispatcher.register_message_handler(self.init_key_change, filters.Text(equals='🔑 API key'),
                                                 state=SettingsFlow.waiting_for_setting_select)

        self.dispatcher.register_message_handler(self.update_api_key, state=SettingsFlow.waiting_for_new_key)

        self.dispatcher.register_message_handler(self.invalid_setting_picked,
                                                 lambda message: message.text not in ["🔑 API key"],
                                                 state=SettingsFlow.waiting_for_setting_select)

        self.dispatcher.register_message_handler(self.process_link, filters.Regexp(URL_REGEX))


        self.register_command_and_text_handlers(self.on_stats, 'stats')

        self.dispatcher.register_inline_handler(self.on_inline_search)

        self.dispatcher.register_message_handler(self.on_unknown_commands)

    async def set_commands(self):
        commands = [
            tgtypes.BotCommand('/help', 'Help me pleaaase!~'),
            tgtypes.BotCommand('/config', 'Let you configure this bot'),
            tgtypes.BotCommand('/settings', 'Change your settings'),
        ]
        await self.bot.set_my_commands(commands)

    def register_command_and_text_handlers(self, func, command, *args, **kwargs):
        self.dispatcher.register_message_handler(func, commands=[command], *args, **kwargs)
        self.dispatcher.register_message_handler(func, filters.Text(equals=command, ignore_case=True), *args, **kwargs)


    async def on_config_init(self, message: tgtypes.Message, user: Optional[User]):
        settings_url = 'https://app.raindrop.io/settings/integrations'

        await ConfigFlow.waiting_for_api_key.set()
        await message.reply("First of all, I need your API key to communicate with Raindrop servers. You can obtain it "
                            f"[here]({settings_url}). Under 'For Developers' section click 'Create new app', "
                            f"choose a name for your app and click 'Create'. Now, click on its name and "
                            f"select 'Create test token'. We're almost done, now send me this token. But don't disclose "
                            f"this token to anyone! I'd even recommend to delete it from this chat after I save it. "
                            f"Anyway, if you worry about it being used unfair you can always reset it there.",
                            parse_mode='markdown')

    async def process_api_key(self, message: tgtypes.Message, state: FSMContext):
        await message.reply('Okay! Let me check this key...')
        if await RaindropApi.check_token(message.text):
            user = User(
                id=ObjectId(),
                telegram_id=message.from_user.id,
                raindrop_api_key=message.text
            )
            await user.save(self.db)
            await state.finish()
            await message.reply("Hooray! You can now send me links or forward posts and I'll save them in Raindrop")

        else:
            await message.reply("It seems this is incorrect token :(\n\n"
                                "Did you read instructions carefully? If you would like to cancel configuration just "
                                "send me /cancel.")

    @only_for_registered
    async def on_settings_init(self, message: tgtypes.Message, user: User):
        await SettingsFlow.waiting_for_setting_select.set()
        keyboard_markup = tgtypes.ReplyKeyboardMarkup(row_width=2)
        keyboard_markup.add(
            tgtypes.KeyboardButton('🔑 API key'),
            tgtypes.KeyboardButton('❌ Cancel')
        )
        await message.reply('What would you like to change?', reply_markup=keyboard_markup)

    async def init_key_change(self, message: tgtypes.Message, state: FSMContext, user: User):
        await SettingsFlow.waiting_for_new_key.set()
        await message.reply('Okay, just send me new key', reply_markup=tgtypes.ReplyKeyboardRemove())

    async def invalid_setting_picked(self, message: tgtypes.Message, user: User):
        await message.reply('Please select one of options')

    async def update_api_key(self, message: tgtypes.Message, state: FSMContext, user: User):
        await message.reply('Okay! Let me check this key...')
        if await RaindropApi.check_token(message.text):
            user.raindrop_api_key = message.text
            await user.save(self.db)
            await state.finish()
            await message.reply("Raindrop API token updated.")
        else:
            await message.reply("It seems this is incorrect token :(\n\n"
                                "Did you read instructions carefully? If you would like to cancel configuration just "
                                "send me /cancel.")

    async def on_global_cancel(self, message: tgtypes.Message, state: FSMContext, user: Optional[User]):
        current_state = await state.get_state()
        if current_state is None:
            return await message.reply('Nothing to cancel...', reply_markup=tgtypes.ReplyKeyboardRemove())

        await state.finish()
        await message.reply('Cancelled.', reply_markup=tgtypes.ReplyKeyboardRemove())

    async def on_help(self, message: tgtypes.Message, user: Optional[User]):
        repo_link = "https://github.com/OlegWock/raindrop-telegram-bot"
        issues_link = "https://github.com/OlegWock/raindrop-telegram-bot/issues"
        help_text = "Hey hey! I can help you with forwarding links or posts from Telegram directly to your " \
                    "'Unsorted' in Raindrop.io. "
        if user is None:
            help_text += "To do this you'll need to do some configuration. Just send " \
                         "me /config and I'll provide you with instructions.\n\n"
        else:
            help_text += "You have set up all necessary settings, but if you would like to configure bot from " \
                         "scratch you can still use /config. If you would like to change particular " \
                         "settings just press /settings\n\n"

        help_text += "**What I can do**\n" \
                     "✔️ Forward links from this chats to Raindrop (into 'Unsorted' collection)\n" \
                     "✔️ Easily share your raindrops in other chats, just type `@raindropiobot <search query>` in any " \
                     "chat and pick which raindrop you would like to share. You can use all " \
                     "[advanced parameters](https://help.raindrop.io/using-search#operators) in search query.\n" \
                     "⏳ Coming soon: save forwarded posts to Raindrop (no more 'Saved Messages' " \
                     "cluttered with longreads)"

        help_text += "\n\nPlease, note that this bot isn't affiliated with Raindrop.io and being developed and "
        help_text += f"supported on non-profit basis. You can check out source code [here]({repo_link}) and ask "
        help_text += f"for help or report any issues [here]({issues_link})."
        await message.reply(help_text, parse_mode='markdown')

    async def on_unknown_commands(self, message: tgtypes.Message, user: Optional[User]):
        await message.reply("Sorry, I didn't understand what you mean. Try clicking /help")

    @only_for_registered
    async def process_link(self, message: tgtypes.Message, user: Optional[User]):
        link = message.text
        logger.info(f'Got link {link}')

        reply = await message.reply('Saving link...')
        api = RaindropApi(user.raindrop_api_key)
        result = await api.raindrops.create(link)

        if result:
            await reply.edit_text("Saved in Unsorted!", parse_mode='markdown')
        else:
            await reply.edit_text("Unknown error :(\n\n"
                                  "Is your API key still valid? You can change it in /settings")


    @only_for_admin
    async def on_stats(self, message: tgtypes.Message):
        await message.reply('Coming soon...')

    async def on_inline_search(self, inline_query: tgtypes.InlineQuery, user: User):
        if user is None:
            await self.bot.answer_inline_query(inline_query.id, results=[],
                                               cache_time=1 if IS_DEV else 300,
                                               switch_pm_text='You need to register first. Click here to do this',
                                               switch_pm_parameter='hello_mr_bot')
            return

        text = inline_query.query or ''
        api = RaindropApi(user.raindrop_api_key)
        if text:
            drops = await api.raindrops.get(collection_id=SpecialCollectionIds.all, search=text)
        else:
            drops = await api.raindrops.get(collection_id=SpecialCollectionIds.all, sort=SortOrder.created_asc)
        results = []
        for drop in drops:
            input_content = tgtypes.InputTextMessageContent(drop.to_pretty('markdown'), parse_mode='markdown')
            results.append(tgtypes.InlineQueryResultArticle(id=drop.id, title=drop.title, description=drop.description,
                                                            url=drop.link, input_message_content=input_content,
                                                            thumb_url=drop.cover))

        await self.bot.answer_inline_query(inline_query.id, results=results,
                                           cache_time=1 if IS_DEV else 300,
                                           is_personal=True)


    async def start(self):
        self.db = await get_db()
        await User.create_indexes(self.db)
        await self.set_commands()
        self.attach_listeners()
        self.dispatcher.middleware.setup(UserAuthMiddleware(self.db))
        await self.dispatcher.skip_updates()
        await self.dispatcher.start_polling()


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    bot = RaindropioBot(loop)
    loop.run_until_complete(bot.start())
