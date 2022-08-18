import logging
from typing import Callable, Dict, List

from base_agent import BaseAgent

import grpc
import json


from ndk import sdk_service_pb2
from ndk import config_service_pb2
from ndk import sdk_common_pb2 as sdk_common
from ndk.sdk_common_pb2 import SdkMgrStatus as sdk_status

THRESHOLD_OPS: Dict[str, Callable[[int, int], bool]] = {
    "gt": lambda x, y: x > y,
    "lt": lambda x, y: x < y,
    "eq": lambda x, y: x == y,
    "neq": lambda x, y: x != y,
    "ge": lambda x, y: x >= y,
    "le": lambda x, y: x <= y,
}


class Support(BaseAgent):
    def __init__(self, name):
        super().__init__(name)
        self.paths: List[Path] = []
        self.flag = False

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

    def _set_flag(self, value: bool) -> None:
        logging.info(f"Setting flag to {value}")
        flag = {"flag": "true" if value else "false"}
        self._update_telemetry(".metric", flag)
        self._update_flag_value()

    def _update_flag_value(self):
        logging.info("*" * 8 + " Getting Flag Value " + "*" * 8)
        response = self._get_state_data(path=["/metric/flag"])
        logging.info(f"GNMI server Response: {response}")
        try:
            flag_value = response["notification"][0]["update"][0]["val"]
            logging.info(f"State of flag: {flag_value}")
            self.flag = flag_value
        except KeyError as e:
            logging.error(f"Server response not formatted as expected: {e}")

    def _find_path(self, key: str):
        """Find path object by key"""
        for path in self.paths:
            if path.path == key:
                return path
        return None

    def _handle_ConfigNotification(
        self, notification: config_service_pb2.ConfigNotification
    ) -> None:
        """Handle configuration notification

        Args:
            config_notif: Configuration notification
        """
        logging.info(f"{notification}")
        if notification.key.js_path == ".metric.paths":
            path_key = notification.key.keys[0]
            if _is_create_notif(notification):
                self.paths.append(Path(path_key, notification.data.json))
            elif _is_delete_notif(notification):
                self.paths.remove(self._find_path(path_key))
            elif _is_change_notif(notification):
                self._find_path(path_key).update(notification.data.json)
        elif notification.key.js_path == ".commit.end":
            logging.info("Received commit end notification")
        else:
            logging.info(f"Unhandled config notification: {notification}")

    def _log_paths(self):
        logging.info("*" * 8 + " Printing Paths " + "*" * 8)
        for path in self.paths:
            logging.info(f"{path}")

    def run(self):
        try:
            for obj in self._get_notifications():
                self._handle_notification(obj)
                self._log_paths()

        except SystemExit:
            logging.info("Handling SystemExit")
        except grpc._channel._Rendezvous as err:
            logging.error(f"Handling grpc exception: {err}")
        except Exception as e:
            # logging.error(f"General exception caught :: {e}")
            raise e
        finally:
            logging.info("End of notification stream reading")


class Path:
    def __init__(self, key: str, json_data: str):
        self.path = key
        try:
            self.data = json.loads(json_data)["paths"]
            self.sampling_rate = self.data["sampling_rate"]["value"]
            self.threshold = self.data["threshold"]["value"]
            self.operator = self.data["operator"]
            self.intervals = [int(data["value"]) for data in self.data["intervals"]]
        except KeyError as e:
            logging.error(f"KeyError {e}")

    def check_threshold(self, value: int) -> bool:
        """Check if value is within threshold

        Args:
            value: Value to check

        Returns:
            True if value is within threshold, False otherwise
        """
        return THRESHOLD_OPS[self.operator](value, self.threshold)

    def update(self, json_data: str) -> None:
        """Update the path with new data"""
        self.data = json.loads(json_data)["paths"]

        if self.data["sampling_rate"]["value"] != self.sampling_rate:
            self.sampling_rate = self.data["sampling_rate"]["value"]
            logging.info(f"Sampling rate updated to {self.sampling_rate}")
        if self.data["threshold"]["value"] != self.threshold:
            self.threshold = self.data["threshold"]["value"]
            logging.info(f"Threshold updated to {self.threshold}")
        if self.data["operator"] != self.operator:
            self.operator = self.data["operator"]
            logging.info(f"Operator updated to {self.operator}")

        new_interval = [int(data["value"]) for data in self.data["intervals"]]
        if new_interval != self.intervals:
            self.intervals = new_interval
            logging.info(f"Intervals updated to {self.intervals}")

    def __repr__(self) -> str:
        pass
        # return f"Path: {self.__str__()}"

    def __str__(self) -> str:
        return (
            f"key: {self.path}, sampling_rate: {self.sampling_rate}, "
            f"threshold: {self.threshold}, operator: {self.operator}, "
            f"intervals: {self.intervals}"
        )


def _is_change_notif(notification):
    return notification.op == sdk_common.SdkMgrOperation.Change


def _is_create_notif(notification):
    return notification.op == sdk_common.SdkMgrOperation.Create


def _is_delete_notif(notification):
    return notification.op == sdk_common.SdkMgrOperation.Delete
