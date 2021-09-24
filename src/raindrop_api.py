import asyncio
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, BinaryIO

import httpx
from httpx import AsyncClient
from pydantic import Field

from db import BaseModel
from utils import get_logger

ROOT_URL = 'https://api.raindrop.io/rest'

logger = get_logger('bot')


class RaindropApi:
    @staticmethod
    async def check_token(token: str) -> bool:
        async with AsyncClient() as client:
            try:
                response = await client.get(f'{ROOT_URL}/v1/user', headers={'Authorization': f'Bearer {token}'})
                return response.status_code == 200
            except Exception as e:
                logger.exception('Error while checking token')
                return False

    def __init__(self, api_key):
        self.api_key = api_key
        self.raindrops = _Raindrops(self)
        self.collections = _Collections(self)

    @property
    def client(self):
        return httpx.AsyncClient(base_url=ROOT_URL, headers={'Authorization': f'Bearer {self.api_key}'})

    async def post_link(self, link: str):
        await asyncio.sleep(3)
        return True


class BaseResourceModel(BaseModel):
    class Config(BaseModel.Config):
        arbitrary_types_allowed = True

    api: 'RaindropApi' = Field()


class SpecialCollectionIds:
    all = 0
    unsorted = -1
    trash = -99


class SortOrder(str, Enum):
    created_asc = 'created'
    created_desc = '-created'
    score = 'score'
    sort_desc = '-sort'
    title_asc = 'title'
    title_desc = '-title'
    domain_asc = 'domain'
    domain_desc = '-domain'


class Collection(BaseResourceModel):
    id: int = Field(..., alias='_id')


class RaindropUser(BaseResourceModel):
    pass


class RaindropType(str, Enum):
    link = 'link'
    article = 'article'
    image = 'image'
    video = 'video'
    document = 'document'
    audio = 'audio'


class Raindrop(BaseResourceModel):
    id: int = Field(..., alias='_id')
    collection_id: int = Field()
    cover: str = Field(),
    created: datetime = Field()
    domain: str = Field()
    title: str = Field()
    description: str = Field('', alias='excerpt')
    last_update: datetime = Field()
    link: str = Field()
    media: List[Dict[str, str]] = Field()
    tags: List[str] = Field()
    type: RaindropType = Field()

    def to_pretty(self, mode: str = 'text') -> str:
        if mode == 'markdown':
            result = f'**[{self.title}]({self.link})**\n\n' \
                     f'{self.description or ""}'
        else:
            result = f'{self.title}\n' \
                     f'{self.link}\n\n' \
                     f'{self.description or ""}'

        return result


class _ResourcesBase:
    def __init__(self, api):
        self.api = api


class _Raindrops(_ResourcesBase):
    async def get(self, *, collection_id: int = SpecialCollectionIds.all,
                  search: str = '', sort: SortOrder = SortOrder.sort_desc, page: int = 0,
                  per_page: int = 50) -> List[Raindrop]:
        async with self.api.client as client:
            response = await client.get(f'/v1/raindrops/{collection_id}', params={
                'search': search,
                'sort': sort,
                'page': page,
                'perpage': per_page,
            })
            js = response.json()

            return [Raindrop(api=self.api, **drop) for drop in js['items']]


    async def create(self, link: str, *, please_parse: bool = True,
                     title: Optional[str] = None, description: Optional[str] = None) -> Optional[Raindrop]:
        async with self.api.client as client:
            payload = {
                'link': link
            }
            if please_parse:
                payload['pleaseParse'] = {}
            else:
                payload['title'] = title
                payload['excerpt'] = description
            response = await client.post(f'/v1/raindrop', json=payload)
            try:
                response.raise_for_status()
                js = response.json()
                if js['result']:
                    return Raindrop(api=self.api, **js['item'])
                return None
            except Exception as e:
                logger.exception('Error while creating raindrop')
                return None

    async def upload_file(self, raindrop_id: int, file: BinaryIO, name: str, mime: str) -> bool:
        async with self.api.client as client:
            response = await client.put(f'/v1/raindrop/{raindrop_id}/file', files={
                'file': (name, file, mime)
            })
            try:
                response.raise_for_status()
                return True
            except Exception as e:
                print(e)
                return False


class _Collections:
    def __init__(self, api_key):
        self.api_key = api_key