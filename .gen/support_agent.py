import logging
import os
from typing import Dict
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

    def _set_done(self):
        """Set done flag"""
        logging.info("*" * 8 + " Setting Flag Value " + "*" * 8)
        self._update_telemetry(self.path, {FLAG: "false"})
        self._update_flag_value()

    def _update_flag_value(self):
        logging.info("*" * 8 + " Getting Flag Value " + "*" * 8)
        # response = self._get_state_data(path=["/metric/flag"])
        response = self._get_state_data(path=[f"/{self.name}/{FLAG}"])
        logging.info(f"GNMI server Response: {response}")
        try:
            flag_value = response["notification"][0]["update"][0]["val"]
            logging.info(f"State of flag: {flag_value}")
            self.flag = flag_value
        except KeyError as e:
            logging.error(f"Server response not formatted as expected: {e}")

    def _handle_ConfigNotification(
        self, notification: config_service_pb2.ConfigNotification
    ) -> None:
        """Handle configuration notification

        Args:
            config_notif: Configuration notification
        """
        # logging.info(f"{notification}")
        if notification.key.js_path == self.path:
            # path_key = notification.key.keys[0]
            if _is_create_notif(notification):
                # self.paths.append(Path(path_key, notification.data.json))
                self._get_node_info()
            elif _is_delete_notif(notification):
                # self.paths.remove(self._find_path(path_key))
                pass
            elif _is_change_notif(notification):
                # self._find_path(path_key).update(notification.data.json)
                # pass
                logging.info(f"{notification}")
                self._get_node_info()
        elif notification.key.js_path == ".commit.end":
            logging.info("Received commit end notification")
        else:
            logging.info(f"Unhandled config notification: {notification}")

    def _mkdir(self, name: str) -> None:
        """Make directory"""
        path = os.path.join(os.path.dirname(__file__), name)
        if not os.path.exists(path):
            os.mkdir(path)
        return path

    def _get_node_info(self):
        """Writes the config found under each of the base paths to a file"""
        logging.info("*" * 8 + " Getting Node Info " + "*" * 8)
        response = self._get_state_data(path=PATHS)
        # Timestamp from first response is used for all subsequent
        # responses (convert from nanoseconds to seconds)
        timestamp_seconds = response["notification"][0]["timestamp"] // 1000000000
        timestamp = datetime.fromtimestamp(timestamp_seconds).strftime(TIME_F)

        # Ensure output directory exists
        self.output_path = self._mkdir("output")

        # Filter out empty updates
        responses = [r for r in response["notification"] if "update" in r]
        for path_response in responses:
            if len(path_response["update"]) != 1:
                logging.error(f"Unexpected number of updates for path: {path_response}")
            self._parse_update(path_response["update"][0], timestamp)

    def _parse_update(self, update: Dict[str, Dict], timestamp: str) -> None:
        """Parse update and write to file
        If an update has an empty body, the update is ignored.
        If an update has no path, recursively parse the update body.

        Args:
            update: Update to parse
            timestamp: Timestamp of update
        """
        path = update["path"]
        val = update["val"]
        if not path:
            for key, value in val.items():
                self._parse_update({"path": key, "val": value}, timestamp)
            return
        if not val:
            return
        path = path.split(":")[-1]  # Remove prefix
        logging.info(f"{self.output_path}/{timestamp}-{path}.json")
        with open(f"{self.output_path}/{timestamp}-{path}.json", "w") as f:
            f.write(json.dumps(val))

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
