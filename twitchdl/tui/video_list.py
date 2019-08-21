import logging
import urwid
import webbrowser

from twitchdl.tui.utils import get_resolutions
from twitchdl.utils import format_duration


logger = logging.getLogger("twitchdl")


class SelectableText(urwid.Text):
    _selectable = True


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

        text = [("blue", published_at), " ", video["title"]]
        text = SelectableText(text, wrap="clip")
        text = urwid.AttrMap(text, None, focus_map={
            "blue": "blue_selected",
            "green": "blue_selected",
        })

        super().__init__(text)

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
