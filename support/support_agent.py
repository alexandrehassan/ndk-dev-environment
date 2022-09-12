import logging
from typing import Dict
import json
from datetime import datetime
import grpc
from base_agent import BaseAgent
import uploader

from ndk.config_service_pb2 import ConfigSubscriptionRequest, ConfigNotification
from ndk.sdk_common_pb2 import SdkMgrOperation as OpCode

logger = logging.getLogger(__name__)

Snapshot = Dict[str, Dict[str, str]]
Path = Dict[str, str]

TIME_FORMAT = "%Y-%m-%d-%H.%M.%S"
NET_NS = "srbase-mgmt"

DEFAULT_PATHS = {
    "running:/": "running",
    "state:/": "state",
    "show:/interface": "show_interface",
}


class Support(BaseAgent):
    def __init__(self, name):
        global logger
        logger = logging.getLogger(f"Agent.{name}")
        super().__init__(name)
        self.path = ".support"
        self._use_default_paths: bool = True
        self._ready_to_run: bool = False
        self.custom_paths: Dict[str, str] = {}

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
        if js_path == self.path and notification.op == OpCode.Change:
            self._handle_config_change(notification)
        elif js_path == self.path and notification.op == OpCode.Create:
            pass
        elif js_path == f"{self.path}.files":
            self._handle_files_notification(notification)
        elif js_path == ".commit.end":
            pass
        else:
            logger.info(
                f"Unhandled config notification:{notification.op}\n{notification}"
            )

    def _handle_config_change(self, notification):
        """Handle change notification"""
        json_data = json.loads(notification.data.json)
        if "run" in json_data and json_data["run"]["value"]:
            if self._ready_to_run:
                self._run_agent()
            else:
                logger.info("Not ready to run")
                self._update_agent_telemetry()
                self._gnmi_set(update=("support/run", False))
        if "use_default_paths" in json_data:
            self._use_default_paths = json_data["use_default_paths"]["value"]

    def _run_agent(self):
        """Run the agent's archive function"""
        # The paths to query only include the default paths if the use_default_paths
        # flag is set to true
        paths = (
            {**self.custom_paths, **DEFAULT_PATHS}
            if self._use_default_paths
            else {**self.custom_paths}
        )

        logger.info(f"Archiving data from ({len(paths)}) path(s)")

        snapshot = self._get_path_snapshot(paths)
        # Snapshots are archived only if they are not empty
        if snapshot:
            self._archive_snapshot(snapshot)

        # Flip the run flag back to false
        self._gnmi_set(update=("support/run", False))

    def _handle_files_notification(self, notification: ConfigNotification) -> None:
        key_list = notification.key.keys

        # There should only be one key in the list for this notification
        if len(key_list) != 1:
            logger.info(f"files notification key has {len(key_list)} keys")
            return
        key = key_list.pop()

        # Form the telemetry path
        telemetry_path = f'{self.path}.files{{.path=="{key}"}}'

        # Handle path deletion
        if notification.op == OpCode.Delete:
            logger.debug(f"Received delete notification for path {key}")
            removed = self.custom_paths.pop(key, None)
            if removed:
                logger.info(f"Removed {removed}")
                self._delete_telemetry(telemetry_path)
            else:
                logger.info(f"{key} not found")
            return

        # Handle path creation or change
        alias = json.loads(notification.data.json)["files"]["alias"]["value"]
        if notification.op == OpCode.Create:
            logger.info(f"Creating {key}")
            assert key not in self.custom_paths
            self.custom_paths[key] = alias
            self._update_telemetry(telemetry_path, {"alias": alias})
        elif notification.op == OpCode.Change:
            logger.info(f"Changing {key}")
            assert key in self.custom_paths
            self.custom_paths[key] = alias
            self._update_telemetry(telemetry_path, {"alias": alias})
        else:
            logger.info(f"Unhandled notification: {notification}")

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
            for path, data in self._gnmi_get(list(paths.keys())).items()
        }

        # Filter out the null values TODO
        res = {k: v for k, v in res.items() if v != "null"}

        if not res:
            logger.info("No data to archive")
            return {}

        time = datetime.now().strftime(TIME_FORMAT)
        return {
            f"{time}-{alias}.json": {"content": res[path]}
            for path, alias in paths.items()
            if path in res
        }

    def _archive_snapshot(self, snapshot: Snapshot) -> None:
        """Archive data"""
        # TODO: Multiple archive methods should be implemented, how to
        #      configure/select the method to use?
        uploader.archive("archive", snapshot)

    def _update_agent_telemetry(self):
        """Update the agent telemetry"""
        data = {
            "ready_to_run": self._ready_to_run,
            "use_default_paths": self._use_default_paths,
        }
        self._update_telemetry(self.path, data)

    def run(self):
        try:
            # Set the initial state of the agent
            self._update_agent_telemetry()
            if self._change_netns(NET_NS):
                logger.info(f"Changed to network namespace: {NET_NS}")

            # Signal that the agent is ready to run
            self._ready_to_run = True
            self._update_agent_telemetry()

            # Main loop
            for obj in self._get_notifications():
                self._handle_notification(obj)
        except SystemExit:
            logger.info("Handling SystemExit")
        except grpc.RpcError:
            logger.info("grpc exception")
        except Exception as e:
            logger.error(f"Unhandled exception: {type(e)} - {e}")
            raise e
        finally:
            logger.info("End of notification stream reading")


def _get_val(message: dict):
    try:
        return message["notification"][0]["update"][0]["val"]
    except KeyError as e:
        logger.info(f"KeyError: {e}\n{message}")
        return None
