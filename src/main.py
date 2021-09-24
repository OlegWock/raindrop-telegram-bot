import asyncio
import io
import os
import re
import uuid
from pprint import pprint
from typing import Optional

from aiogram import Bot, Dispatcher, types as tgtypes
from aiogram import filters
from aiogram.dispatcher import FSMContext
from aiogram.bot.api import TelegramAPIServer
from bson import ObjectId

from motor import motor_asyncio

from db import get_db, User, get_fsm_storage
from auth import UserAuthMiddleware, only_for_registered, only_for_admin
from raindrop_api import RaindropApi, SpecialCollectionIds, SortOrder
from fsm import ConfigFlow, SettingsFlow
from utils import get_logger, URL_REGEX, IS_DEV, URL_REGEX_STRICT, RUN_IN_DOCKER

logger = get_logger('bot')


# logging.basicConfig(level=logging.DEBUG)


class RaindropioBot:
    def __init__(self, event_loop: asyncio.AbstractEventLoop):
        bot_token = os.getenv('BOT_TOKEN', None)
        bot_server = TelegramAPIServer.from_base(os.getenv('BOT_SERVER_URL', 'https://api.telegram.org'))

        self.using_default_bot_server = bot_server == 'https://api.telegram.org'

        if bot_token is None:
            raise ValueError("You forgot to set BOT_TOKEN variable")

        self.loop = event_loop
        self.bot = Bot(token=bot_token, server=bot_server)
        self.dispatcher = Dispatcher(self.bot, storage=get_fsm_storage())
        self.db = None  # type: motor_asyncio.AsyncIOMotorDatabase
        with open('misc/post_template.html') as f:
            self.post_template = f.read()

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

        supported_media_types = tgtypes.ContentTypes.VIDEO | tgtypes.ContentTypes.PHOTO | tgtypes.ContentTypes.DOCUMENT
        self.dispatcher.register_message_handler(self.process_message,
                                                 content_types=tgtypes.ContentTypes.TEXT | supported_media_types,
                                                 is_forwarded=True)

        self.dispatcher.register_message_handler(self.process_message, content_types=supported_media_types)

        self.dispatcher.register_message_handler(self.process_link, filters.Regexp(URL_REGEX_STRICT))

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
    async def process_link(self, message: tgtypes.Message, user: User):
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

    @only_for_registered
    async def process_message(self, message: tgtypes.Message, user: User):
        print('Got forwarded message')
        has_supported_attachment = (message.photo is not None and len(message.photo) > 0) \
                                   or (message.video is not None) or (message.document is not None)
        if message.caption is not None:
            print("Has caption")
            text = message.caption
            entities = message.caption_entities
        else:
            text = message.text or ''
            entities = message.entities or []

        has_links = any([entity.type in ['url', 'text_link'] for entity in entities])
        links_to = None
        all_links_have_same_url = True
        for entity in entities:
            if entity.type in ['url', 'text_link']:
                if links_to is not None or links_to == entity.url:
                    links_to = entity.url
                else:
                    all_links_have_same_url = False
                    break

        text_len = len(re.sub(URL_REGEX, '', text))

        print('Got forwarded message. Has links:', has_links, 'has attachments', has_supported_attachment, 'len:',
              text_len)

        if not has_supported_attachment and not has_links and text_len < 100:
            await message.reply("Hmmmm, this doesn't look like longread 🤔, I can't save this to Raindrop.\n"
                                "If you need help just press /help")
            return

        api = RaindropApi(user.raindrop_api_key)

        if has_links and text_len < 700 and all_links_have_same_url:
            # This is probably some kind of announce and short description for shared article
            raindrop = await api.raindrops.create(links_to)
            await message.reply('Saved!')
        elif has_supported_attachment:
            # Save file to Raindrop
            if message.photo is not None and len(message.photo) > 0:
                attachment = sorted(message.photo, key=lambda x: x.width, reverse=True)[0]
                name = f'{uuid.uuid4()}.jpg'
                mime = 'image/jpg'
            else:
                attachment = message.video or message.document
                name = attachment.file_name
                mime = attachment.mime_type

            if self.using_default_bot_server and attachment.file_size > 1024 * 1024 * 20:
                await message.reply('Your file is too big :(\n\n'
                                    'Telegram allows us to only download files 20MB (or less)')
                return

            if attachment.file_size > 1024 * 1024 * 100:
                await message.reply('Your file is too big :(\n\n'
                                    'Raindrop supports only files up to 100MB')
                return

            raindrop = await api.raindrops.create(f'http://example.com/{uuid.uuid4()}', please_parse=False,
                                                  title='Saved from Telegram', description='')
            if raindrop is None:
                await message.reply('Unknown error :(')
                return


            if self.using_default_bot_server:
                attachment_file = await self.bot.download_file_by_id(attachment.file_id)
            else:
                attachment_info = await self.bot.get_file(attachment.file_id)
                if RUN_IN_DOCKER:
                    path = attachment_info.file_path.replace('/srv/', '/raindrop/', 1)
                else:
                    path = attachment_info.file_path.replace('/srv/public/', './bot_server_volume/', 1)
                attachment_file = open(path, 'rb')

            result = await api.raindrops.upload_file(raindrop.id, attachment_file, name, mime)
            attachment_file.close()
            if result:
                await message.reply('Saved!')
            else:
                await message.reply('Unknown error :(')
        else:
            raindrop = await api.raindrops.create(f'http://example.com/{uuid.uuid4()}', please_parse=False,
                                                  title='Saved from Telegram', description='')
            if raindrop is None:
                await message.reply('Unknown error :(')
                return

            html_file = io.BytesIO(
                bytes(self.format_post(message), 'utf-8')
            )
            result = await api.raindrops.upload_file(raindrop.id, html_file, f'{uuid.uuid4()}.html', 'text/html')
            if result:
                await message.reply('Saved!')
            else:
                await message.reply('Unknown error :(')



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

    def format_post(self, message):
        text = ''
        text_paragraphs = message.html_text.split('\n\n')
        for p in text_paragraphs:
            text += '<p>{0}</p>'.format(p.replace("\n", "<br>"))
        return self.post_template.format(title="Saved from Telegram", text=text)

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
