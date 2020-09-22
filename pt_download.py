import aiohttp
import asyncio
import logging
import m3u8
import re

from prompt_toolkit import prompt
from prompt_toolkit.shortcuts import ProgressBar

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


async def calculate_total_size(session):
    playlist = await get(session, PLAYLIST_URL)
    playlist = m3u8.loads(playlist)

    sem = asyncio.Semaphore(CONCURRENT_DOWNLOADS)
    urls = [f"{BASE_URL}{segment.uri}" for segment in playlist.segments]
    tasks = [get_file_size(session, sem, url) for url in urls]

    sizes = await asyncio.gather(*tasks)
    return sum(sizes)


async def download(session, url, target):
    total = 0
    async with session.get(url) as response:
        size = int(response.headers["Content-Length"])
        with ProgressBar() as pb:
            with open(target, "wb") as fd:
                while True:
                    chunk = await response.content.read(1024)
                    if not chunk:
                        break
                    fd.write(chunk)
                    total += len(chunk)
                    print(f"{total}/{size} ({total/size}%)")


from prompt_toolkit.application import Application
from prompt_toolkit.layout import (
    ConditionalContainer,
    FormattedTextControl,
    HSplit,
    Layout,
    VSplit,
    Window,
)


async def main():
    # url = "http://d2nvs31859zcd8.cloudfront.net/a0d597168fd112da5a30_bananasaurus_rex_39701470206_1600199701/chunked/0.ts"
    # async with aiohttp.ClientSession() as session:
    #     await download(session, url, "vod.ts")

    application = Application(
        layout=Layout(
            VSplit([
                Window(
                    content=FormattedTextControl("hi")
                )
            ])
        )
    )

    result = await application.run_async()
    print(result)

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
