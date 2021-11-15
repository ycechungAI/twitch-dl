#!/usr/bin/env python3
import asyncio
import httpx
import logging
import m3u8
import os
import re
import requests
import time

from dataclasses import dataclass, field
from prompt_toolkit import Application, HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Dimension
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from typing import Callable, Dict, List, Optional

from twitchdl import twitch
from twitchdl.utils import format_size, format_duration

logging.basicConfig(filename="log.log", level=logging.DEBUG)
logger = logging.getLogger("asyncio")

# WORKER_POOL_SIZE = 5
CHUNK_SIZE = 1024 * 256
# CONNECT_TIMEOUT = 5
# RETRY_COUNT = 5


@dataclass
class Task:
    id: int
    pid: int
    filename: str
    size: Optional[int] = None
    downloaded: int = 0
    progress: int = 0
    start_time: float = field(default_factory=time.time)
    speed: float = 0

    def report_chunk(self, chunk_size):
        self.downloaded += chunk_size
        self.progress = int(100 * self.downloaded / self.size)
        self.speed = int(self.downloaded / (time.time() - self.start_time))


class Downloader:
    start_time: float
    avg_speed: float
    chunk_count: int
    vod_count: int = 0
    vod_size: int = 0
    bytes_downloaded: int = 0
    estimated_total: int
    estimated_remaining_time: int
    progress: int = 0

    active_tasks: Dict[int, Task] = {}

    def __init__(self, worker_count: int):
        self.start_time = time.time()
        self.worker_count = worker_count
        self.progress_bars = [
            Window(height=1, content=FormattedTextControl(text=HTML("<gray>Worker idle</gray>")))
            for _ in range(worker_count)
        ]
        self.header = Window(height=1,
            content=FormattedTextControl(text=HTML("<gray>Initializing</gray>")))

        kb = KeyBindings()
        kb.add("q")(lambda event: event.app.exit())

        divider = Window(height=1, char='─')
        root_container = HSplit([self.header, divider] + self.progress_bars)
        layout = Layout(root_container)

        self.app = Application(layout=layout, key_bindings=kb)

    async def run(self, loop, sources, targets):
        if len(sources) != len(targets):
            raise ValueError(f"Got {len(sources)} sources but {len(targets)} targets.")

        self.chunk_count = len(sources)
        loop.create_task(self.download(sources, targets))
        await self.app.run_async()

    async def download(self, sources, targets):
        await download_all(sources, targets, self.worker_count,
            self.on_init, self.on_start, self.on_progress, self.on_end)
        self.app.exit()

    def on_init(self, task_id: int, filename: str):
        # Occupy an unoccupied progress bar
        pid = self.get_free_pid()
        task = Task(task_id, pid, filename)
        self.active_tasks[task_id] = task
        self.set_task_progress(task, "<gray>Initializing...</gray>")

    def get_free_pid(self):
        occupied_pids = [t.pid for t in self.active_tasks.values()]
        pid = next(pid for pid in range(self.worker_count) if pid not in occupied_pids)
        return pid

    def on_start(self, task_id: int, size: int):
        task = self.active_tasks[task_id]
        task.size = size

        self.vod_count += 1
        self.vod_size += size
        self.estimated_total = int(self.chunk_count * self.vod_size / self.vod_count)
        self.progress = int(100 * self.bytes_downloaded / self.estimated_total)

    def on_progress(self, task_id: int, chunk_size: int):
        task = self.active_tasks[task_id]
        task.report_chunk(chunk_size)

        self.bytes_downloaded += chunk_size
        self.progress = int(100 * self.bytes_downloaded / self.estimated_total)
        self.avg_speed = self.bytes_downloaded - (time.time() - self.start_time)
        self.estimated_remaining_time = int((self.estimated_total - self.bytes_downloaded) / self.avg_speed)

        self.set_task_progress(task)
        self.update_header()

    def on_end(self, task_id: int):
        task = self.active_tasks[task_id]
        self.set_task_progress(task, "<gray>Idle</gray>")
        del self.active_tasks[task_id]

    def update_header(self):
        self.header.content.text = (
            f"{format_size(self.bytes_downloaded)} "
            f"of {format_size(self.estimated_total)} "
            f"({self.progress}%) "
            f"ETA {format_duration(self.estimated_remaining_time)}"
        )

    def set_task_progress(self, task: Task, message: str = None):
        content = message or " │ ".join([
            f"#{task.pid:02}",
            task.filename,
            f"{task.progress}%",
            f"{format_size(task.speed)}/s"
        ])

        self.progress_bars[task.pid].content.text = HTML(content)
        self.app.invalidate()


async def download_one(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    task_id: int,
    source: str,
    target: str,
    on_init: Callable[[int, str], None],
    on_start: Callable[[int, int], None],
    on_progress: Callable[[int, int], None],
    on_end: Callable[[int], None]
):
    async with semaphore:
        with open(target, 'wb') as f:
            # TODO: handle failure (retries etc)
            on_init(task_id, os.path.basename(target))
            async with client.stream('GET', source) as response:
                size = int(response.headers.get('content-length'))
                on_start(task_id, size)
                async for chunk in response.aiter_bytes(chunk_size=CHUNK_SIZE):
                    f.write(chunk)
                    on_progress(task_id, len(chunk))
                on_end(task_id)


async def download_all(
    sources: List[str],
    targets: List[str],
    workers: int,
    on_init: Callable[[int, str], None],
    on_start: Callable[[int, int], None],
    on_progress: Callable[[int, int], None],
    on_end: Callable[[int], None]
):
    async with httpx.AsyncClient() as client:
        semaphore = asyncio.Semaphore(workers)
        tasks = [download_one(client, semaphore, task_id, source, target, on_init, on_start, on_progress, on_end)
                 for task_id, (source, target) in enumerate(zip(sources, targets))]
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    videos = twitch.get_channel_videos("bananasaurus_rex", 1, "time")
    video_id = videos["edges"][0]["node"]["id"]

    from twitchdl.commands.download import _get_vod_paths
    access_token = twitch.get_access_token(video_id)
    playlists = twitch.get_playlists(video_id, access_token)
    playlist_uri = m3u8.loads(playlists).playlists[0].uri
    playlist = requests.get(playlist_uri).text
    vods = _get_vod_paths(m3u8.loads(playlist), None, None)
    base_uri = re.sub("/[^/]+$", "/", playlist_uri)
    urls = ["".join([base_uri, vod]) for vod in vods][:10]
    targets = [f"tmp/{os.path.basename(url).zfill(8)}" for url in urls]

    loop = asyncio.get_event_loop()
    d = Downloader(5)
    loop.run_until_complete(d.run(loop, urls, targets))
