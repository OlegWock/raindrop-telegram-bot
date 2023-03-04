import os
from httpx import AsyncClient

from utils import get_logger


HTMLSHARE_ROOT_URL = os.getenv('HTMLSHARE_BASE_URL', 'https://raindrop-html-share.sinja.io')
HTMLSHARE_PASSWORD = os.getenv('HTMLSHARE_PASSWORD', '')

logger = get_logger('bot')

logger.info(f"Using {HTMLSHARE_ROOT_URL} as htmlshare domain")

async def upload_html(html: str):
    # TODO: need to figure out why this fails `httpcore.ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self signed certificate`
    # if verify=True (or ommited) when calling htmlshare on sinja.io
    async with AsyncClient(verify=False) as client:
        response = await client.post(f'{HTMLSHARE_ROOT_URL}/html', json={"html": html, "password": HTMLSHARE_PASSWORD})
        if response.status_code != 200:
            return None
        return f'{HTMLSHARE_ROOT_URL}/html/{response.json()["id"]}'