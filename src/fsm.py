from aiogram.dispatcher.filters.state import State, StatesGroup


class ConfigFlow(StatesGroup):
    waiting_for_api_key = State()


class SettingsFlow(StatesGroup):
    waiting_for_setting_select = State()
    waiting_for_new_key = State()
