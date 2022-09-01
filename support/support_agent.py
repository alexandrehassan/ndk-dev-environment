import logging
from typing import Any, Dict
import grpc
import json
from datetime import datetime

from base_agent import BaseAgent
import uploader

from ndk import config_service_pb2
from ndk import sdk_common_pb2 as sdk_common


TIME_FORMAT = "%Y-%m-%d-%H.%M.%S"
NET_NS = "srbase-mgmt"
DEFAULT_PATHS = {
    "running:/": "running",
    "state:/": "state",
    "show:/interface": "show_interface",
}


class Support(BaseAgent):
    def __init__(self, name):
        super().__init__(name)
        self.path = ".support"

    def __enter__(self):
        super().__enter__()
        self._subscribe_to_config()
        return self

    def _set_default_paths(self):
        """Set default paths"""

        for path, alias in DEFAULT_PATHS.items():
            self._set_data(f"support/files[path={path}]", {"alias": alias})

    def _subscribe_to_config(self):
        """Subscribe to configuration"""
        self._register_for_notifications(
            config_request=config_service_pb2.ConfigSubscriptionRequest()
        )

    def _handle_ConfigNotification(
        self, notification: config_service_pb2.ConfigNotification
    ) -> None:
        """Handle configuration notification

        Args:
            config_notif: Configuration notification
        """
        if notification.key.js_path.startswith(self.path):
            if _is_create_notif(notification):
                pass
            elif _is_delete_notif(notification):
                pass
            elif _is_change_notif(notification):
                logging.info(f"Change notification to path: {notification.key.js_path}")
                self._handle_config_change(notification)
        elif notification.key.js_path == ".commit.end":
            logging.info("Received commit end notification")
        else:
            logging.info(f"Unhandled config notification: {notification}")

    def _handle_config_change(self, notification):
        """Handle change notification"""
        if notification.key.js_path == self.path:
            logging.info(f"Change to base path: {self.path}")
            # TODO: Find a better way to trigger these.
            self._set_default_paths()
            paths = self._get_paths()
            data = self._get_path_data(paths)
            self._archive_data(data)
            # Archive().upload_all(self.output_path)
        elif notification.key.js_path == f"{self.path}.files":
            logging.info(f"Change to files path: {self.path}.files")
        else:
            logging.info(f"Unhandled change notification: {notification}")
            return
        logging.info(f"Change notification: {notification}")

    def _get_paths(self) -> Dict[str, str]:
        """Get paths from config
        Need to query the config to get the paths as the agent is not updated if the
        config is updated through gNMI"""
        # TODO: why is datatype needed? Shouldn't all include config??
        response = self._get_data(path=["/support/files"], datatype="config")
        # TODO: Is there a better way to get the paths?
        data = response["notification"][0]["update"][0]["val"]["files"]
        logging.info(f"Paths: {data}")
        return {entry["alias"]: entry["path"] for entry in data}

    def _get_path_data(self, paths: Dict[str, str]) -> Dict[str, Dict[str, str]]:
        """Query the paths and return the data

        Args:
            paths: Paths to query

        Returns:
            Data from the paths in a dictionary in the format:
                {"path_alias": "data from path"}
        """

        def _query(path: str) -> Dict[str, Any]:
            """Query the path and return the data"""
            logging.info(f"Querying path: {path}")
            try:
                data = self._get_data([path])["notification"][0]["update"][0]["val"]
            except grpc.RpcError as e:
                logging.error(f"Failed to query path: {path}")
                logging.debug(f"Failed to query path: {path} :: {e}")
                return {}
            except Exception as e:
                logging.error(f"Failed to query path: {path} :: {e}")
                return {}
            return data

        responses = {alias: _query(path) for alias, path in paths.items()}

        time = datetime.now().strftime(TIME_FORMAT)
        data = {
            f"{time}-{name}.json": {"content": json.dumps(response)}
            for name, response in responses.items()
        }
        return data

    def _archive_data(self, data: Dict[str, Dict[str, str]]) -> None:
        """Archive data"""
        # TODO: Multiple archive methods should be implemented, how to
        #      configure/select the method to use?

        uploader.archive_and_scp(
            "172.20.20.1", "root" "/root/git/ndk-dev-environment/", data
        )

    def run(self):
        try:
            if self._change_netns(NET_NS):
                logging.info(f"Changed to network namespace: {NET_NS}")
            # else:
            #     return
            for obj in self._get_notifications():
                self._handle_notification(obj)
        except SystemExit:
            logging.info("Handling SystemExit")
        except grpc._channel._Rendezvous as err:
            logging.error(f"Handling grpc exception: {err}")
        except Exception as e:
            raise e
        finally:
            logging.info("End of notification stream reading")


def _is_change_notif(notification):
    return notification.op == sdk_common.SdkMgrOperation.Change


def _is_create_notif(notification):
    return notification.op == sdk_common.SdkMgrOperation.Create


def _is_delete_notif(notification):
    return notification.op == sdk_common.SdkMgrOperation.Delete
