import requests

from datetime import datetime

from twitchdl import CLIENT_ID


def authenticated_get(url, params={}):
    headers = {'Client-ID': CLIENT_ID}
    return requests.get(url, params, headers=headers)


def get_resolutions(video):
    return reversed([
        (k, v, str(round(video["fps"][k])))
        for k, v in video["resolutions"].items()
    ])


def parse_datetime(value):
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S%z")


def format_datetime(dttm):
    return dttm.strftime("%Y-%m-%d %H:%M")


def reformat_datetime(value):
    return format_datetime(parse_datetime(value))
