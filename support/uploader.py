import logging
import shutil
import os
from typing import Dict
import requests
import paramiko
from paramiko import SSHClient
from scp import SCPClient

import json

Snapshot = Dict[str, Dict[str, str]]
GITHUB_GIST = "https://api.github.com/gists"


def _mkdir(name: str) -> None:
    """Make directory"""
    path = os.path.join(os.path.dirname(__file__), name)
    if not os.path.exists(path):
        os.mkdir(path)


def archive(name: str, data: Snapshot, protocol: str = "tar") -> None:
    """Write data to an archive

    Args:
        name: Name of the archive
        data: Data to archive in the format:
            {"filename": {"content": "file contents"}}
        protocol: Archive protocol to use
    """
    _mkdir("output")
    for filename, content in data.items():
        with open(f"output/{filename}", "w") as f:
            f.write(content["content"])
    shutil.make_archive(f"output/{name}", protocol, "output")


def upload_to_gists(name: str, files: Snapshot, oauth: str) -> None:
    """Upload files to GitHub Gists

    Args:
        name: Name of the gist
        files: Files to upload in the format:
            {"filename": {"content": "file contents"}}
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


class SshConnection:
    """Wrapper for SSHClient.connect allowing to use it as a context manager"""

    def __init__(self, server: str, username: str) -> None:
        self._client = SSHClient()
        # self._client.load_system_host_keys("/home/admin/.ssh/known_hosts")
        self._client.load_system_host_keys()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.server = server
        self.username = username

    def __enter__(self):
        self._client.connect(self.server, username=self.username)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self._client:
            self._client.close()

    def scp_put(self, filename: str, destination: str) -> None:
        """Upload file to server"""
        with SCPClient(self._client.get_transport()) as scp:
            scp.put(filename, destination)


def scp_to_server(server: str, username: str, filename: str, destination: str) -> None:
    """SCP files to server"""
    with SshConnection(server, username) as ssh:
        ssh.scp_put(filename, destination)


def archive_and_scp(
    server: str,
    destination: str,
    data: Snapshot,
    protocol: str = "tar",
) -> None:
    archive("archive", data, protocol)
    try:
        scp_to_server(server, "root", f"output/archive.{protocol}", destination)
    except Exception as e:
        logging.error(e)
