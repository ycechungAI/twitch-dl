import requests

from twitchdl import CLIENT_ID


def authenticated_get(url, params={}):
    headers = {'Client-ID': CLIENT_ID}
    return requests.get(url, params, headers=headers)


def get_resolutions(video):
    return reversed([
        (k, v, str(round(video["fps"][k])))
        for k, v in video["resolutions"].items()
    ])
