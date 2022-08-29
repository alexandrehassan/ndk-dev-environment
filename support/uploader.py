import shutil
from typing import Any, Dict
import os

GITHUB_GIST = "https://api.github.com/gists"


class Uploader:
    def upload(self, file):
        print("Uploading file: " + file)

    def upload_all(self, name, data):
        # for file in files:
        #     self.upload(file)
        pass


class Archive(Uploader):
    def _mkdir(self, name: str) -> None:
        """Make directory"""
        path = os.path.join(os.path.dirname(__file__), name)
        if not os.path.exists(path):
            os.mkdir(path)
        return path

    def upload(self, file):
        print("Archiving file: " + file)

    def upload_all(self, name, data):
        # print("Archiving files: " + str(directory))
        self._mkdir("output")
        for filename, content in data.items():
            with open(f"output/{filename}", "w") as f:
                f.write(content["content"])
        shutil.make_archive("output/archive", "tar", "output")
