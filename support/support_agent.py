import logging
from typing import Dict
import grpc
import json
from datetime import datetime

from base_agent import BaseAgent, gnmi_get, gnmi_set, gnmi_set_retry
from gnmi_info import Get_Info
import uploader

from ndk.config_service_pb2 import ConfigSubscriptionRequest, ConfigNotification
from ndk.sdk_common_pb2 import SdkMgrOperation as OpCode

Snapshot = Dict[str, Dict[str, str]]

TIME_FORMAT = "%Y-%m-%d-%H.%M.%S"
NET_NS = "srbase-mgmt"
DEFAULT_PATHS = [
    ("support/files[path=running:/]", {"alias": "running"}),
    ("support/files[path=state:/]", {"alias": "state"}),
    ("support/files[path=show:/interface]", {"alias": "show_interface"}),
]


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
        self._register_for_notifications(config_request=ConfigSubscriptionRequest())

    def _handle_ConfigNotification(self, notification: ConfigNotification) -> None:
        """Handle configuration notification

        Args:
            config_notif: Configuration notification
        """
        js_path = notification.key.js_path
        if js_path.startswith(self.path) and notification.op == OpCode.Change:
            self._handle_config_change(notification)
        elif notification.op == OpCode.Delete or notification.op == OpCode.Create:
            pass
        elif js_path == ".commit.end":
            logging.info("Received commit end notification")
        else:
            logging.info(f"Unhandled config notification: {notification}")

    def _handle_config_change(self, notification):
        """Handle change notification"""
        if notification.key.js_path == self.path:
            json_data = json.loads(notification.data.json)
            if not json_data["ready_to_run"]["value"]:
                logging.info("Not ready to run")
                return
            if json_data["run"]["value"]:
                logging.info("Received run notification")
                paths = self._get_paths()
                snapshot = self._get_path_snapshot(paths)
                self._archive_snapshot(snapshot)
                self._signal_end_of_run()
        elif notification.key.js_path == f"{self.path}.files":
            logging.info(f"Change to files path: {self.path}.files")
        else:
            logging.info(f"Unhandled change notification: {notification}")

    def _get_paths(self) -> Dict[str, str]:
        """Get paths from config
        Need to query the config to get the paths as the agent is not updated if the
        config is updated through gNMI"""
        # TODO: why is datatype needed? Shouldn't all include config??
        response = _get_val(
            gnmi_get("/support/files", query_info=Get_Info(datatype="config"))
        )["files"]
        logging.info(f"Paths: {response}")
        return {entry["alias"]: entry["path"] for entry in response}

    def _get_path_snapshot(self, paths: Dict[str, str]) -> Snapshot:
        """Query the paths and return the data

        Args:
            paths: Paths to query

        Returns:
            Data from the paths in a dictionary in the format:
                {"path_alias": {"contents": "data from path"}}
        """
        res = {
            path: json.dumps(_get_val(data))
            for path, data in gnmi_get(paths.values()).items()
        }

        time = datetime.now().strftime(TIME_FORMAT)
        return {
            f"{time}-{alias}.json": {"content": res[path]}
            for alias, path in paths.items()
        }

    def _archive_snapshot(self, snapshot: Snapshot) -> None:
        """Archive data"""
        # TODO: Multiple archive methods should be implemented, how to
        #      configure/select the method to use?
        uploader.archive("archive", snapshot)

    def _signal_end_of_run(self):
        """Signal end of run"""
        response = gnmi_set(("support", {"run": False}))
        logging.info(f"Set run to false: {response}")

    def run(self):
        try:
            # Signal that the agent is ready to run
            # (also checks that yang model is loaded)
            gnmi_set_retry(("support", {"ready_to_run": True}))
            if self._change_netns(NET_NS):
                logging.info(f"Changed to network namespace: {NET_NS}")
            # Set the default paths
            gnmi_set(DEFAULT_PATHS)
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


def _get_val(message: dict):
    return message["notification"][0]["update"][0]["val"]
