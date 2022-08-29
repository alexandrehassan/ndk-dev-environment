import logging
from typing import Any, Dict
import grpc
import json
from datetime import datetime

from base_agent import BaseAgent

from ndk import sdk_service_pb2
from ndk import config_service_pb2
from ndk import sdk_common_pb2 as sdk_common
from ndk.sdk_common_pb2 import SdkMgrStatus as sdk_status

from uploader import Archive


TIME_FORMAT = "%Y-%m-%d-%H.%M.%S"


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
        paths = {
            "running:/": "running",
            "state:/": "state",
            "show:/interface": "show_interface",
        }
        for path, alias in paths.items():
            self._set_data(f"support/files[path={path}]", {"alias": alias})

    def _subscribe_to_config(self):
        """Subscribe to configuration"""
        request = sdk_service_pb2.NotificationRegisterRequest(
            stream_id=self.stream_id,
            op=sdk_service_pb2.NotificationRegisterRequest.AddSubscription,
            config=config_service_pb2.ConfigSubscriptionRequest(),
        )

        response = self.sdk_mgr_client.NotificationRegister(
            request=request, metadata=self.metadata
        )
        if response.status == sdk_status.kSdkMgrSuccess:
            logging.info(
                f"Subscribed to config successfully :: "
                f"stream_id: {response.stream_id} sub_id: {response.sub_id}"
            )
        else:
            logging.error(
                f"Failed to subscribe to config :: "
                f"stream_id: {response.stream_id} sub_id: {response.sub_id}"
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
                self._handle_change_notification(notification)
        elif notification.key.js_path == ".commit.end":
            logging.info("Received commit end notification")
        else:
            logging.info(f"Unhandled config notification: {notification}")

    def _handle_change_notification(self, notification):
        """Handle change notification"""
        if notification.key.js_path == self.path:
            logging.info(f"Change to base path: {self.path}")
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
            data = self._get_data(path=[path])["notification"][0]["update"][0]["val"]
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
        # Gists().upload_all("support agent output", data)
        Archive().upload_all("archive", data)

    def run(self):
        try:
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
