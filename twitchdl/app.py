import json
import urwid
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


PALETTE = [
    ('reversed', 'standout', ''),
    ('header', 'white', 'dark blue'),
    ('header_bg', 'black', 'dark red'),
    ('selected', 'white', 'dark green'),
    ('green', 'light green', ''),
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

        return key

    def mouse_event(self, size, event, button, x, y, focus):
        if button != 1 or not urwid.is_mouse_press(event):
            return False

        self._emit('click')
        return True


class App:
    def __init__(self, videos):
        self.videos = videos
        self.details_shown = False

        self.header = self.build_header()
        self.details = urwid.Pile([])
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

    def build_frame(self, details):
        if details:
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
        video_id = video['_id'][1:]

        self.details.contents = [
            (urwid.Text(("blue", video_id)), ('pack', None)),
            (urwid.Text(video['title']), ('pack', None)),
        ]

    def handle_keypress(self, key):
        if key in ('q', 'Q'):
            raise urwid.ExitMainLoop()

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
