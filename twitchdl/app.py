import json
import logging
import urwid
import webbrowser
import requests

from concurrent.futures import ThreadPoolExecutor

from twitchdl import CLIENT_ID
from twitchdl.commands import format_duration
from twitchdl import twitch

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("twitchdl")


PALETTE = [
    ('italic', 'white', ''),
    ('reversed', 'standout', ''),
    ('header', 'white', 'dark blue'),
    ('header_bg', 'black', 'dark red'),
    ('selected', 'white', 'dark green'),
    ('green', 'dark green', ''),
    ('cyan', 'dark cyan', ''),
    ('cyan_bold', 'dark cyan,bold', ''),
    ('green_selected', 'white,bold', 'dark green'),
    ('blue', 'light blue', ''),
    ('yellow', 'yellow', ''),
    ('blue_bold', 'light blue, bold', ''),
    ('blue_selected', 'white,bold', 'dark blue'),
]


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


def get_resolutions(video):
    return reversed([
        (k, v, str(round(video["fps"][k])))
        for k, v in video["resolutions"].items()
    ])


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


class VideoList:
    def __init__(self, videos):
        self.videos = videos
        self.details_shown = False

        # TODO: handle no videos

        self.header = self.build_header()
        self.details = VideoDetails(videos[0])
        self.video_list = self.build_video_list(videos)

        self.frame = self.build_frame(self.details_shown)
        self.download_overlay = None

        self.loop = urwid.MainLoop(
            self.frame,
            palette=PALETTE,
            unhandled_input=self.handle_keypress,
        )

    def build_video_list(self, videos):
        body = []
        for video in videos:
            video_item = VideoListItem(video)
            urwid.connect_signal(video_item, 'click', self.show_details)
            body.append(urwid.AttrMap(video_item, None, focus_map='blue_selected'))

        walker = urwid.SimpleFocusListWalker(body)
        urwid.connect_signal(walker, 'modified', self.video_selected)
        return urwid.ListBox(walker)

    def build_header(self):
        header = urwid.Text(('header', 'twitch-dl '), align='left')
        header = urwid.AttrMap(header, 'header')
        return urwid.Padding(header)

    def build_frame(self, show_details):
        if show_details:
            main_widget = urwid.Columns([
                ("weight", 50, self.video_list),
                ("weight", 50, self.details),
            ], dividechars=1)
        else:
            main_widget = self.video_list

        return urwid.Frame(main_widget, header=self.header)

    def show_details(self, *args):
        if not self.details_shown:
            self.details_shown = True
            self.video_selected()
            self.loop.widget = self.build_frame(True)

    def hide_details(self):
        if self.details_shown:
            self.details_shown = False
            self.loop.widget = self.build_frame(False)

    def draw_details(self, video):
        self.details = VideoDetails(video)
        self.loop.widget = self.build_frame(True)

    def handle_keypress(self, key):
        if key in ('q', 'Q'):
            raise urwid.ExitMainLoop()

        # TODO: open in VLC
        if key in ["v", "V"]:
            video = self.get_focused_video()
            webbrowser.open(video["url"])

        if key in ["d", "D"]:
            video = self.get_focused_video()
            self.show_download_overlay(video)
            return True

        if key == 'esc':
            self.hide_details()
            return

    def show_download_overlay(self, video):
        self.loop.widget = DownloadView(video)
        self.loop.widget.run()

    def run(self):
        self.loop.run()

    def video_selected(self):
        """Triggered when the focused video has changed."""
        if not self.details_shown:
            return

        video = self.get_focused_video()
        self.draw_details(video)

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
    def __init__(self, video):
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.video = video

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

    def video_loaded(self, future):
        """Called when the video details have been loaded."""
        response = future.result()
        if not response.ok:
            self.pile.contents.append((urwid.Text(("red", "An error occured :(")), ("pack", None)))
            self.pile.contents.append((urwid.Button("Go back"), ("pack", None)))
            return

        video = response.json()
        logger.info(video)

        self.top_w = urwid.LineBox(urwid.Text("hi!"), title="Download video")

    def run(self):
        url = self.video["_links"]["self"]
        headers = {'Client-ID': CLIENT_ID}

        # Asynchronously fetch the video info
        future = self.executor.submit(requests.get, url, headers=headers)
        future.add_done_callback(self.video_loaded)

    #     resolutions = [
    #         urwid.Text("Pick quality:")
    #     ]
    #     for name, res, fps in get_resolutions(video):
    #         text = ResolutionText(name, res, fps)
    #         urwid.connect_signal(text, 'click', self.resolution_selected, user_args=[name])
    #         resolutions.append(
    #             urwid.AttrMap(
    #                 text,
    #                 None,
    #                 focus_map='blue_selected'
    #             )
    #         )

    #     top_w = urwid.Pile(resolutions)
    #     top_w = urwid.LineBox(top_w, title="Download video")
    #     bottom_w = urwid.SolidFill()

    #     super().__init__(
    #         top_w, bottom_w,
    #         'center', ('relative', 80),
    #         'middle', 'pack',
    #         min_width=20,
    #         min_height=12
    #     )

    def resolution_selected(self, widget, name):
        logger.info("Selected resulution: {}".format(name))


# videos = twitch.get_channel_videos("bananasaurus_rex", limit=100)
# app = VideoList(videos["videos"])
# app.run()

with open('tmp/data.json') as f:
    data = json.load(f)
    app = VideoList(data['videos'])
    app.run()
