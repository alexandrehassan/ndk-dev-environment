import logging
import shutil
from typing import Dict
import os
import requests

import json

GITHUB_GIST = "https://api.github.com/gists"


def _mkdir(name: str) -> None:
    """Make directory"""
    path = os.path.join(os.path.dirname(__file__), name)
    if not os.path.exists(path):
        os.mkdir(path)
    return path


def archive(name: str, data: Dict[str, Dict[str, str]], protocol: str = "tar") -> None:
    _mkdir("output")
    for filename, content in data.items():
        with open(f"output/{filename}", "w") as f:
            f.write(content["content"])
    shutil.make_archive(f"output/{name}", protocol, "output")


def upload_to_gists(name: str, files: Dict[str, str], oauth: str) -> None:
    """Upload files to GitHub Gists

    Args:
        name: Name of the gist
        files: Files to upload
        oauth: GitHub OAuth token
    """
    # TODO: This is temporary
    if not oauth:
        with open(".oauth", "r") as file:
            oauth = file.read()
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"token {oauth}",
    }
    params = {"scope": "gist"}
    payload = {
        "description": name,
        "public": False,
        "files": files,
    }
    response = requests.post(
        GITHUB_GIST,
        headers=headers,
        params=params,
        json=payload,
    )
    print(f"code: {response.status_code}, response: {response.text}")
    logging.info(f"code: {response.status_code}")


def test_gists():
    res = requests.get(GITHUB_GIST, params={"per_page": 1, "page": 1}).text
    json_res = json.loads(res)[0]["url"]

    print(json_res)
    logging.info(json_res)


# try:
#     test_gists()
# except Exception as e:
#     print(e)
#     logging.error(e)
