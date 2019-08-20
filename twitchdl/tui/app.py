import logging
import urwid
import webbrowser
import requests

from concurrent.futures import ThreadPoolExecutor
from threading import current_thread

from twitchdl import CLIENT_ID
from twitchdl.utils import format_duration
from twitchdl.tui.constants import PALETTE


logger = logging.getLogger("twitchdl")


def authenticated_get(url, params={}):
    headers = {'Client-ID': CLIENT_ID}
    return requests.get(url, params, headers=headers)


def get_resolutions(video):
    return reversed([
        (k, v, str(round(video["fps"][k])))
        for k, v in video["resolutions"].items()
    ])


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
            video = self.video_list.get_focused_video()
            self.show_download_overlay(video)
            return

    def show_download_overlay(self, video):
        self.loop.widget = DownloadView(video, self.loop)
        self.loop.widget.run()


class SelectableText(urwid.Text):
    _selectable = True


class VideoListItem(urwid.WidgetWrap):
    def sizing(self):
        return frozenset([urwid.FLOW])

    signals = ["click"]

    def __init__(self, video):
        published_at = "{} {}{}".format(
            video["published_at"][:10],
            video["published_at"][11:16],
            video["published_at"][19:],
        )
        published_at_len = len(published_at)

        published_at = SelectableText(published_at)
        published_at = urwid.AttrMap(published_at, 'blue', focus_map='blue_selected')

        widgets = [
            ('fixed', published_at_len, published_at),
            urwid.Text(video["title"], wrap="clip"),
        ]
        cols = urwid.Columns(widgets, dividechars=1)
        self.__super.__init__(cols)

    def keypress(self, size, key):
        if self._command_map[key] == urwid.ACTIVATE:
            self._emit('click')
            return

        return key

    def mouse_event(self, size, event, button, x, y, focus):
        if button == 1:
            self._emit('click')

        return super().mouse_event(size, event, button, x, y, focus)


class VideoDetails(urwid.Pile):
    def __init__(self, video):
        video_id = video['_id'][1:]
        duration = format_duration(video['length'])
        published_at = video['published_at'].replace('T', ' @ ').replace('Z', '')
        channel_name = video['channel']['display_name']

        contents = [
            ('pack', urwid.Text(("blue_bold", video_id))),
            ('pack', urwid.Text(("green", video['title']))),
            ('pack', urwid.Divider("~")),
            ('pack', urwid.Text([("cyan", channel_name), " playing ", ("cyan", video['game'])])),
            ('pack', urwid.Divider("~")),
            ('pack', urwid.Text(["  Published: ", ("cyan", published_at)])),
            ('pack', urwid.Text(["     Length: ", ("cyan", duration)])),
            ('pack', urwid.Divider("~")),
            ('pack', urwid.Text("Resolutions: ")),
        ]

        for name, resolution, fps in get_resolutions(video):
            contents.append(
                ('pack', urwid.Text([
                    " * ", ("cyan", name),
                    " (", resolution, " @ ", fps, "fps)"
                ]))
            )

        contents.append(('weight', 1, urwid.SolidFill(" ")))
        contents.append(('pack', urwid.Divider("-")))
        contents.append(('pack', urwid.Text(("italic", video['url']))))
        contents.append(('pack', urwid.Text([
            "Actions: ",
            ("cyan_bold", "V"),
            ("cyan", "iew"),
            " ",
            ("cyan_bold", "D"),
            ("cyan", "ownload"),
        ])))

        super().__init__(contents)


class VideoList(urwid.Columns):
    def __init__(self, videos):
        self.videos = videos
        self.details_shown = False

        # TODO: handle no videos

        self.details = VideoDetails(videos[0])
        self.video_list = self.build_video_list(videos)

        super().__init__([
            ("weight", 50, self.video_list)
        ], dividechars=1)

        logger.info(self.widget_list)

    def refresh(self):
        if self.details_shown:
            self.contents = [
                (self.video_list, ("weight", 50, False)),
                (self.details, ("weight", 50, False)),
            ]
        else:
            self.contents = [
                (self.video_list, ("weight", 50, False)),
            ]

    def build_video_list(self, videos):
        body = []
        for video in videos:
            video_item = VideoListItem(video)
            urwid.connect_signal(video_item, 'click', self.show_details)
            body.append(urwid.AttrMap(video_item, None, focus_map='blue_selected'))

        walker = urwid.SimpleFocusListWalker(body)
        urwid.connect_signal(walker, 'modified', self.video_selected)
        return urwid.ListBox(walker)

    def show_details(self, *args):
        if not self.details_shown:
            self.details_shown = True
            self.refresh()

    def hide_details(self):
        if self.details_shown:
            self.details_shown = False
            self.refresh()

    def draw_details(self, video):
        self.details = VideoDetails(video)
        self.refresh()

    def keypress(self, pos, key):
        if key in ("v", "V"):
            video = self.get_focused_video()
            webbrowser.open(video["url"])
            return

        # TODO: open in VLC/MPV

        if key == 'esc':
            self.hide_details()
            return

        return super().keypress(pos, key)

    def run(self):
        self.loop.run()

    def video_selected(self):
        """Triggered when the focused video has changed."""
        self.draw_details(self.get_focused_video())

    def get_focused_video(self):
        return self.videos[self.video_list.body.focus]


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
    def __init__(self, video, loop):
        logger.info("outside: " + str(current_thread()))
        self.video = video
        self.loop = loop
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
        self.loop.set_alarm_in(0, self.video_loaded, user_data=response)

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

        # maybe ???
        # https://github.com/CanonicalLtd/subiquity/blob/master/subiquitycore/core.py#L280

        # educational:
        # https://github.com/TomasTomecek/sen/blob/master/sen/tui/ui.py


    def resolution_selected(self, widget, name):
        logger.info("Selected resulution: {}".format(name))

    def keypress(self, size, key):
        logger.info("overlay keypress {}".format(key))
        return key
