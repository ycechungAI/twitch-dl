import aiohttp
import asyncio
import logging
import m3u8
import re

from prompt_toolkit import prompt
from urllib.parse import urlparse

PLAYLIST_URL = "http://d2nvs31859zcd8.cloudfront.net/a0d597168fd112da5a30_bananasaurus_rex_39701470206_1600199701/160p30/index-dvr.m3u8"
BASE_URL = re.sub("/[^/]+$", "/", PLAYLIST_URL)

CONCURRENT_DOWNLOADS = 100

logger = logging.getLogger(__name__)


async def get(session, url):
    logger.debug(f"GET {url}")
    async with session.get(url) as response:
        return await response.text()


async def get_file_size(session, sem, url):
    async with sem:
        logger.debug(f"HEAD {url}")
        async with session.head(url) as response:
            return int(response.headers["Content-Length"])


async def main():
    async with aiohttp.ClientSession() as session:
        playlist = await get(session, PLAYLIST_URL)
        playlist = m3u8.loads(playlist)

        sem = asyncio.Semaphore(CONCURRENT_DOWNLOADS)
        urls = [f"{BASE_URL}/{segment.uri}" for segment in playlist.segments]
        tasks = [get_file_size(session, sem, url) for url in urls]

        sizes = await asyncio.gather(*tasks)
        total_size = sum(sizes)

        print(sizes)

        print("total size: ", sum(sizes))


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
