import logging
from typing import Dict
import grpc
import json
from datetime import datetime

from base_agent import BaseAgent, gnmi_get
import uploader

from ndk.config_service_pb2 import ConfigSubscriptionRequest, ConfigNotification
from ndk.sdk_common_pb2 import SdkMgrOperation as OpCode

Snapshot = Dict[str, Dict[str, str]]
Path = Dict[str, str]

TIME_FORMAT = "%Y-%m-%d-%H.%M.%S"
NET_NS = "srbase-mgmt"
DEFAULT_PATHS = {
    "support/files[path=running:/]": "running",
    "support/files[path=state:/]": "state",
    "support/files[path=show:/interface]": "show_interface",
}


class Support(BaseAgent):
    def __init__(self, name):
        super().__init__(name)
        self.path = ".support"
        self._use_default_paths = True
        self._is_running = False
        self._ready_to_run = False
        self.custom_paths = {}

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
            logging.info(
                f"Unhandled config notification:{notification.op}\n{notification}"
            )

    def _handle_config_change(self, notification):
        """Handle change notification"""
        json_data = json.loads(notification.data.json)
        logging.info(f"json_data = {json_data}")
        if "run" in json_data and json_data["run"]["value"]:
            if self._ready_to_run:
                self._run_agent()
            else:
                logging.info("Not ready to run")
                self._signal_end_of_run()
        if "use_default_paths" in json_data:
            self._use_default_paths = json_data["use_default_paths"]["value"]
            logging.info(f"use_default_paths = {self._use_default_paths}")

    def _run_agent(self):
        """Run the agent"""
        logging.info("Running agent")
        self._signal_begin_run()
        paths = {**self.custom_paths}
        if self._use_default_paths:
            paths.update(DEFAULT_PATHS)
        snapshot = self._get_path_snapshot(paths)
        self._archive_snapshot(snapshot)
        self._signal_end_of_run()

    def _handle_files_notification(self, notification: ConfigNotification) -> None:
        key_list = notification.key.keys
        if len(key_list) != 1:
            logging.info(f"files notification key has {len(key_list)} keys")
            return
        key = key_list.pop()

        if notification.op == OpCode.Delete:
            # logging.info(f"Deleting {key}")
            # removed = self.custom_paths.pop(key, None)
            # if removed:
            #     logging.info(f"Removed {key}")
            #     self._delete_telemetry(telem_path)
            # else:
            #     logging.info(f"{key} not found")
            return
        logging.info("\n" * 100)
        logging.info(f"\n{notification}")
        alias = json.loads(notification.data.json)["files"]["alias"]["value"]
        telem_path = f'.support.files{{.path=="{key}"}}'
        t1_path1 = f"support.files[path={key}]"
        t1_path2 = f".support.files[path={key}].path"
        t1_path2 = f"support:support/files[path={key}]"
        t1_path3 = f"support/files[path={key}]"
        t1_data = {"alias": alias}

        t2_path1 = "support.files"
        t2_path2 = "/support"
        t2_path2 = "support:support/files"
        t2_path3 = "support/files"
        t2_data = {"alias": alias, "path": key}

        if notification.op == OpCode.Create:
            # self._update_telemetry(telem_path, {"alias": alias})
            logging.info(f"testing path: {t1_path1} with data: {t1_data}")
            self._update_telemetry(t1_path1, t1_data)
            logging.info(f'Query after\n{gnmi_get("support:support")}')

            logging.info(f"testing path: {t1_path2} with data: {t1_data}")
            self._update_telemetry(t1_path2, t1_data)
            logging.info(f'Query after\n{gnmi_get("support:support")}')

            logging.info(f"testing path: {t1_path3} with data: {t1_data}")
            self._update_telemetry(t1_path3, t1_data)
            logging.info(f'Query after\n{gnmi_get("support:support")}')

            logging.info(f"testing path: {t2_path1} with data: {t2_data}")
            self._update_telemetry(t2_path1, t2_data)
            logging.info(f'Query after\n{gnmi_get("support:support")}')

            logging.info(f"testing path: {t2_path2} with data: {t2_data}")
            self._update_telemetry(t2_path2, t2_data)
            logging.info(f'Query after\n{gnmi_get("support:support")}')

            logging.info(f"testing path: {t2_path3} with data: {t2_data}")
            self._update_telemetry(t2_path3, t2_data)
            logging.info(f'Query after\n{gnmi_get("support:support")}')

            logging.info(f"\n\nResult with correct request: {telem_path}")
            self._update_telemetry(telem_path, {"alias": alias})
            logging.info(f'Query after\n{gnmi_get("support:support")}')

        elif notification.op == OpCode.Change:
            self._update_telemetry(telem_path, {"alias": alias})
        else:
            logging.info(f"Unhandled notification: {notification}")

    def _get_path_snapshot(self, paths: Dict[str, str]) -> Snapshot:
        """Query the paths and return the data

        Args:
            paths: Paths to query

        Returns:
            Data from the paths in a dictionary in the format:
                {"path_alias": {"contents": "data from path"}}
        """
        logging.info(f"Snapshot of paths - {paths}")
        logging.info(f"Query response = {gnmi_get(paths.keys())}")
        res = {
            path: json.dumps(_get_val(data))
            for path, data in gnmi_get(paths.keys()).items()
        }

        # Filter out the null values TODO
        res = {k: v for k, v in res.items() if v != "null"}

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

    def _signal_ready(self):
        """Signal that the agent is ready to run"""
        self._ready_to_run = True
        self._update_telemetry(self.path, {"run": False, "ready_to_run": True})
        # self._update_telemetry(self.path, {"ready_to_run": True})

    def _signal_begin_run(self):
        """Signal that the agent is ready to run"""
        self._is_running = True
        self._update_telemetry(self.path, {"run": True})

    def _signal_end_of_run(self):
        """Signal end of run"""
        self._is_running = False
        self._update_telemetry(self.path, {"run": False})

    def run(self):
        try:
            self._signal_ready()
            if self._change_netns(NET_NS):
                logging.info(f"Changed to network namespace: {NET_NS}")
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
    try:
        return message["notification"][0]["update"][0]["val"]
    except KeyError as e:
        logging.info(f"KeyError: {e}\n{message}")
        return None
