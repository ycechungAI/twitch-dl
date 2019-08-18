import json
import urwid
import logging
import webbrowser

from twitchdl.commands import format_duration

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


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
        logger.info("foo")
        if button == 1:
            self._emit('click')

        return super().mouse_event(size, event, button, x, y, focus)


class VideoDetails(urwid.Frame):
    def __init__(self, video):
        super().__init__(
            body=self.draw_body(video),
            footer=self.draw_footer(video),
        )

    def draw_footer(self, video):
        return urwid.Text([
            "Actions: ",
            ("cyan_bold", "V"),
            ("cyan", "iew"),
            " ",
            ("cyan_bold", "D"),
            ("cyan", "ownload"),
        ])

    def draw_body(self, video):
        video_id = video['_id'][1:]
        duration = format_duration(video['length'])
        published_at = video['published_at'].replace('T', ' @ ').replace('Z', '')
        channel_name = video['channel']['display_name']

        # (name, resolution, frame rate)
        resolutions = reversed([
            (k, v, str(round(video["fps"][k])))
            for k, v in video["resolutions"].items()
        ])

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

        for name, resolution, fps in resolutions:
            contents.append(
                ('pack', urwid.Text([
                    " * ", ("cyan", name),
                    " (", resolution, " @ ", fps, "fps)"
                ]))
            )

        contents.append(('pack', urwid.Divider()))
        contents.append(('pack', urwid.Text(("italic", video['url']))))

        return urwid.Pile(contents)


class App:
    def __init__(self, videos):
        self.videos = videos
        self.details_shown = False

        # TODO: handle no videos

        self.header = self.build_header()
        self.details = VideoDetails(videos[0])
        self.video_list = self.build_video_list(videos)

        self.loop = urwid.MainLoop(
            self.build_frame(self.details_shown),
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

        if key in ["v", "V"]:
            video = self.get_focused_video()
            # TODO: open in VLC
            webbrowser.open(video["url"])

        if key == 'esc':
            self.hide_details()
            return

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


with open('tmp/data.json') as f:
    data = json.load(f)
    app = App(data['videos'])
    app.run()
