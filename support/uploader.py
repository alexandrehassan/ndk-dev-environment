import shutil
from typing import Any, Dict
import os
import requests
import logging
import json

GITHUB_GIST = "https://api.github.com/gists"


class Uploader:
    def _mkdir(self, name: str) -> None:
        """Make directory"""
        path = os.path.join(os.path.dirname(__file__), name)
        if not os.path.exists(path):
            os.mkdir(path)
        return path

    def upload(self, file):
        print("Uploading file: " + file)

    def upload_all(self, name: str, data: Dict[str, Dict[str, str]]):
        # for file in files:
        #     self.upload(file)
        pass


class Archive(Uploader):
    def upload(self, file):
        print("Archiving file: " + file)

    def upload_all(self, name: str, data: Dict[str, Dict[str, str]]):
        # print("Archiving files: " + str(directory))
        self._mkdir("output")
        for filename, content in data.items():
            with open(f"output/{filename}", "w") as f:
                f.write(content["content"])
        shutil.make_archive("output/archive", "tar", "output")


class Gists(Uploader):
    def __init__(self):
        with open(".oauth", "r") as file:
            self.oauth = file.read()

    def _headers(self):
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"token {self.oauth}",
        }

    def _params(self):
        return {"scope": "gist"}

    def _payload(self, name: str, files: Dict[str, str]) -> Dict[str, Any]:
        return {
            "description": name,
            "public": False,
            "files": files,
        }

    def upload_all(self, name: str, files: Dict[str, str]):
        try:
            test_gists()
            response = requests.post(
                GITHUB_GIST,
                headers=self._headers(),
                params=self._params(),
                json=self._payload(name, files),
            )
            print(f"code: {response.status_code}, response: {response.text}")
            logging.info(f"code: {response.status_code}")
        except ConnectionError as e:
            logging.error(f"ConnectionError: {e}")
        except Exception as e:
            logging.error(f"Exception: {e}")


def test_gists():
    res = requests.get(GITHUB_GIST, params={"per_page": 1, "page": 1}).text
    json_res = json.loads(res)[0]["url"]

    print(json_res)
    logging.info(json_res)


test_gists()
