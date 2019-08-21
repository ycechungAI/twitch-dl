import logging
import urwid


from concurrent.futures import ThreadPoolExecutor
from threading import current_thread

from twitchdl.tui.constants import PALETTE
from twitchdl.tui.video_list import VideoList
from twitchdl.tui.utils import get_resolutions, authenticated_get

logger = logging.getLogger("twitchdl")


class TUI(urwid.Frame):
    """Main TUI frame."""

    @classmethod
    def create(cls, videos):
        """Factory method, sets up TUI and an event loop."""

        tui = cls(videos)
        loop = urwid.MainLoop(
            tui,
            palette=PALETTE,
            event_loop=urwid.AsyncioEventLoop(),
            unhandled_input=tui.unhandled_input,
        )
        tui.loop = loop

        return tui, loop

    def __init__(self, videos):
        self.loop = None  # set in `create`

        header = urwid.Text(('header', 'twitch-dl '), align='left')
        header = urwid.AttrMap(header, 'header')
        header = urwid.Padding(header)

        self.video_list = VideoList(videos)

        super().__init__(self.video_list, header=header)

    def run(self):
        self.loop.run()

    def unhandled_input(self, key):
        if key in ('q', 'Q'):
            raise urwid.ExitMainLoop()

        if key in ["d", "D"]:
            self.show_download_overlay()
            return

    def show_download_overlay(self):
        video = self.video_list.get_focused_video()
        self.body = DownloadView(video, self)
        self.body.run()


class ResolutionText(urwid.Text):
    signals = ["click"]
    _selectable = True

    def __init__(self, name, res, fps):
        super().__init__(" > " + name)

    def keypress(self, size, key):
        if self._command_map[key] == urwid.ACTIVATE:
            self._emit('click')
            return

        return key

    def mouse_event(self, size, event, button, x, y, focus):
        if event == "mouse press" and button == 1:
            self._emit('click')
            return


class DownloadView(urwid.Overlay):
    def __init__(self, video, tui):
        logger.info("outside: " + str(current_thread()))
        self.video = video
        self.tui = tui
        self.executor = ThreadPoolExecutor(max_workers=1)

        # TODO: shut down executor before closing

        self.pile = urwid.Pile([
            urwid.Text("Loading video..."),
            urwid.Text(("yellow", video["_links"]["self"])),
        ])

        top_w = urwid.LineBox(self.pile, title="Download video")

        bottom_w = urwid.SolidFill()
        super().__init__(
            top_w, bottom_w,
            'center', ('relative', 80),
            'middle', 'pack',
            min_width=20,
            min_height=12
        )

    def run(self):
        # Asynchronously fetch the video info
        future = self.executor.submit(authenticated_get, self.video["_links"]["self"])
        future.add_done_callback(self.video_loaded_callback)

    def video_loaded_callback(self, future):
        """
        Called by the executor thread when the video details have been loaded.
        Uses `set_alarm_in` to run the callback in the main thread.
        """
        response = future.result()
        self.tui.loop.set_alarm_in(0, self.video_loaded, user_data=response)

    def video_loaded(self, main_loop, response):
        if not response.ok:
            self.pile.contents.append((urwid.Text(("red", "An error occured :(")), ("pack", None)))
            self.pile.contents.append((urwid.Button("Go back"), ("pack", None)))
            return

        video = response.json()

        # Show available resolutions for download
        resolutions = [(urwid.Text("Pick quality:"), ('pack', None))]
        for name, res, fps in get_resolutions(video):
            text = ResolutionText(name, res, fps)
            urwid.connect_signal(text, 'click', self.resolution_selected, user_args=[name])
            resolutions.append(
                (urwid.AttrMap(text, None, focus_map='blue_selected'), ('pack', None))
            )

        for res in resolutions:
            self.pile.contents = resolutions

    def resolution_selected(self, widget, name):
        logger.info("Selected resulution: {}".format(name))

    def keypress(self, size, key):
        logger.info("overlay keypress {}".format(key))
        return key
