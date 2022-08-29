import logging
import os
from typing import Dict, Set, Tuple
import grpc
import json
from datetime import datetime

from base_agent import BaseAgent

from ndk import sdk_service_pb2
from ndk import config_service_pb2
from ndk import sdk_common_pb2 as sdk_common
from ndk.sdk_common_pb2 import SdkMgrStatus as sdk_status

FLAG = "run"
PATHS = [
    "acl",
    "bfd",
    "interface",
    "platform",
    "system",
    "network-instance",
    "routing-policy",
    "qos",
    "tunnel",
    "tunnel-interface",
    "support",
]

TIME_F = "%Y-%m-%d %H.%M.%S"


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

        # self._set_data(f"support/files[path=running:/]", {"alias": "running"})

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
                # self._get_specific_data()
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
            self._get_specific_data(paths)
        elif notification.key.js_path == f"{self.path}.files":
            logging.info(f"Change to files path: {self.path}.files")
        else:
            logging.info(f"Unhandled change notification: {notification}")
            return
        logging.info(f"Change notification: {notification}")

    def _mkdir(self, name: str) -> None:
        """Make directory"""
        path = os.path.join(os.path.dirname(__file__), name)
        if not os.path.exists(path):
            os.mkdir(path)
        return path

    def _get_paths(self) -> Dict[str, str]:
        """Get paths"""
        # TODO: why is datatype needed? Shouldn't all include config??
        response = self._get_state_data(path=["/support/files"], datatype="config")
        logging.info(f"GNMI server Response: {response}")
        try:
            data = response["notification"][0]["update"][0]["val"]["files"]
            logging.info(f"State of paths: {data}")
            paths = {entry["alias"]: entry["path"] for entry in data}
            return paths
        except KeyError as e:
            logging.error(f"Server response not formatted as expected: {e}")

    def _get_specific_data(self, paths: Dict[str, str]) -> None:
        responses = {}
        for name, path in paths.items():
            responses[name] = self._get_state_data(path=[path], encoding="json_ietf")[
                "notification"
            ][0]["update"]

        self.output_path = self._mkdir("output")
        try:
            for name, response in responses.items():
                with open(f"{self.output_path}/{name}.json", "w") as f:
                    f.write(json.dumps(response, indent=4))
        except Exception as e:
            logging.error(
                f"Error writing output: {e} :: {name} :: {type(response)} :: {response}"
            )

    def run(self):
        try:
            for obj in self._get_notifications():
                self._handle_notification(obj)
        except SystemExit:
            logging.info("Handling SystemExit")
        except grpc._channel._Rendezvous as err:
            logging.error(f"Handling grpc exception: {err}")
        except Exception as e:
            # logging.error(f"General exception caught :: {e}")
            raise e
        finally:
            logging.info("End of notification stream reading")


def _is_change_notif(notification):
    return notification.op == sdk_common.SdkMgrOperation.Change


def _is_create_notif(notification):
    return notification.op == sdk_common.SdkMgrOperation.Create


def _is_delete_notif(notification):
    return notification.op == sdk_common.SdkMgrOperation.Delete
