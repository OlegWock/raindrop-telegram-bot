import os
import asyncio
from pymongo import IndexModel, ASCENDING
from motor import motor_asyncio
from aiogram.contrib.fsm_storage import mongo as mongo_fsm

from typing import List, Type, TypeVar, Optional
from motor import motor_asyncio
from datetime import datetime
import pydantic
from pydantic import BaseConfig, Field
from bson import ObjectId
from bson.errors import InvalidId


def to_camelcase(string: str) -> str:
    res = ''.join(word.capitalize() for word in string.split('_'))
    return res[0].lower() + res[1:]


class BaseModel(pydantic.BaseModel):
    class Config(BaseConfig):
        ignore_extra = True
        alias_generator = to_camelcase
        allow_population_by_field_name = True
        use_enum_values = True


class OID(str):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        try:
            return ObjectId(str(v))
        except InvalidId:
            raise ValueError("Not a valid ObjectId")


T = TypeVar('T', bound='MongoModel')


class MongoModel(BaseModel):
    class Config(BaseConfig):
        allow_population_by_field_name = True
        json_encoders = {
            datetime: lambda dt: dt.isoformat(),
            ObjectId: lambda oid: str(oid),
        }

    @classmethod
    async def create_indexes(cls: Type[T], db: motor_asyncio.AsyncIOMotorDatabase):
        model_indexes = cls.indexes
        collection = db[cls.collection]
        await collection.create_indexes(model_indexes)

    @classmethod
    def from_mongo(cls: Type[T], data: dict) -> T:
        """We must convert _id into "id". """
        if not isinstance(data, dict):
            raise TypeError('data must be dict')
        id = data.pop('_id', None)
        return cls(**dict(data, id=id))

    @classmethod
    async def from_mongo_cursor(cls: Type[T], cursor: motor_asyncio.AsyncIOMotorCursor) -> List[T]:
        return [cls.from_mongo(x) async for x in cursor]

    def mongo(self, **kwargs):
        exclude_unset = kwargs.pop('exclude_unset', True)
        by_alias = kwargs.pop('by_alias', False)

        parsed = self.dict(
            exclude_unset=exclude_unset,
            by_alias=by_alias,
            **kwargs,
        )

        # Mongo uses `_id` as default key. We should stick to that as well.
        if '_id' not in parsed and 'id' in parsed:
            parsed['_id'] = parsed.pop('id')

        return parsed

    async def save(self, db):
        await db[self.collection].update_one({
            '_id': self.id,
        }, {
            '$set': self.mongo()
        }, upsert=True)


class User(MongoModel):
    id: OID = Field()
    telegram_id: int = Field()
    raindrop_api_key: Optional[str] = Field(None)

    @classmethod
    @property
    def collection(cls):
        return 'User'

    @classmethod
    @property
    def indexes(cls):
        return [
            IndexModel([('telegram_id', ASCENDING)], name="telegram_id"),
        ]

    @classmethod
    async def get_by_telegram_id(cls, db, telegram_id):
        user = await db[User.collection].find_one({
            'telegram_id': telegram_id
        })
        if user is not None:
            user = cls.from_mongo(user)

        return user


MONGO_HOST = os.getenv('MONGO_HOST')
MONGO_PORT = int(os.getenv('MONGO_PORT'))
MONGO_USER = os.getenv('MONGO_INITDB_ROOT_USERNAME')
MONGO_PASSWORD = os.getenv('MONGO_INITDB_ROOT_PASSWORD')
MONGO_URI = f'mongodb://{MONGO_USER}:{MONGO_PASSWORD}@{MONGO_HOST}:{MONGO_PORT}'
MONGO_DB_NAME = 'raindropiobot'


async def get_db_client() -> motor_asyncio.AsyncIOMotorClient:
    mongo = motor_asyncio.AsyncIOMotorClient(MONGO_URI)
    for i in range(60):
        try:
            await mongo.server_info()
            break
        except Exception:
            await asyncio.sleep(0.2)
    return mongo


async def get_db() -> motor_asyncio.AsyncIOMotorDatabase:
    return (await get_db_client())[MONGO_DB_NAME]


def get_fsm_storage() -> mongo_fsm.MongoStorage:
    storage = mongo_fsm.MongoStorage(uri=MONGO_URI, db_name=MONGO_DB_NAME + '_fsm')
    return storage
