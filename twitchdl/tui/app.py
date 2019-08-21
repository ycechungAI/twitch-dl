import logging
import urwid

from concurrent.futures import ThreadPoolExecutor

from twitchdl.tui.constants import PALETTE
from twitchdl.tui.utils import get_resolutions, authenticated_get
from twitchdl.tui.video_list import VideoList
from twitchdl.tui.widgets import SelectableText

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

    def close_download_overlay(self):
        self.body = self.video_list


class DownloadView(urwid.Overlay):
    def __init__(self, video, tui):
        self.video = video
        self.tui = tui
        self.executor = ThreadPoolExecutor(max_workers=1)

        # TODO: shut down executor before closing

        self.pile = urwid.Pile([
            urwid.Text("Loading video..."),
            urwid.Text(("yellow", video["_links"]["self"])),
        ])

        top_w = urwid.LineBox(self.pile, title="Download video")
        bottom_w = tui.video_list

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
        # TODO: handle error
        response = future.result()
        self.tui.loop.set_alarm_in(0, self.video_loaded, user_data=response)

    def video_loaded(self, main_loop, response):
        if not response.ok:
            self.pile.contents.append((urwid.Text(("red", "An error occured :(")), ("pack", None)))
            self.pile.contents.append((urwid.Button("Go back"), ("pack", None)))
            return

        video = response.json()

        # Show available resolutions for download
        # TODO: this should probably be a separate widget instead of reusing this one
        resolutions = []

        focus_map = {
            "blue": "blue_selected",
            "yellow": "blue_selected",
            None: "blue_selected",
        }

        for name, res, fps in get_resolutions(video):
            text = SelectableText([
                ("blue", name), " ",
                ("yellow", res), " ",
                fps, "fps"
            ])
            urwid.connect_signal(text, 'click', self.resolution_selected, user_args=[name])
            resolutions.append(
                (urwid.AttrMap(text, None, focus_map=focus_map), ('pack', None))
            )

        self.top_w.set_title("Select video quality")
        self.pile.contents = resolutions

    def resolution_selected(self, widget, name):
        logger.info("Selected resulution: {}".format(name))

    def keypress(self, pos, key):
        logger.info("DownloadView keypress: {}".format(key))

        # Don't re-download if D is pressed
        if key in ['d', 'D']:
            return

        # Close download window on ESC
        if key == 'esc':
            self.tui.close_download_overlay()

        return super().keypress(pos, key)
