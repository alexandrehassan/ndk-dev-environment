#!/usr/bin/env python
# coding=utf-8

import threading
from types import TracebackType
from typing import Generator, List, Optional, Tuple, Type, Union
import grpc
import sys
import logging
import signal
import json
import time

from pygnmi.client import gNMIclient, gNMIException

from pyroute2 import netns

from ndk.sdk_service_pb2 import (
    AgentRegistrationRequest,
    NotificationRegisterRequest,
    Notification,
    NotificationStreamRequest,
    KeepAliveRequest,
)
from ndk.sdk_service_pb2_grpc import (
    SdkMgrServiceStub,
    SdkNotificationServiceStub,
)
from ndk.telemetry_service_pb2_grpc import SdkMgrTelemetryServiceStub
from ndk import telemetry_service_pb2
from ndk.interface_service_pb2 import (
    InterfaceNotification,
    InterfaceSubscriptionRequest,
)
from ndk.networkinstance_service_pb2 import (
    NetworkInstanceNotification,
    NetworkInstanceSubscriptionRequest,
)
from ndk.lldp_service_pb2 import (
    LldpNeighborNotification,
    LldpNeighborSubscriptionRequest,
)
from ndk.config_service_pb2 import ConfigNotification, ConfigSubscriptionRequest
from ndk.bfd_service_pb2 import BfdSessionNotification, BfdSessionSubscriptionRequest
from ndk.route_service_pb2 import IpRouteNotification, IpRouteSubscriptionRequest
from ndk.appid_service_pb2 import AppIdentNotification, AppIdentSubscriptionRequest
from ndk.nexthop_group_service_pb2 import (
    NextHopGroupNotification,
    NextHopGroupSubscriptionRequest,
)
from ndk.sdk_common_pb2 import SdkMgrStatus as sdk_status

from gnmi_info import gNMI_Info

SetData = Tuple[str, List[str]]

DATATYPES = {"all", "config", "state", "operational"}
ENCODINGS = {"json", "bytes", "proto", "ascii", "json_ietf"}


class BaseAgent(object):
    def __init__(self, name: str):
        self.name = name
        self.metadata = [("agent_name", self.name)]
        self.stream_id = None
        self.keepalive_interval = 10
        self.set_default_gnmi_info()

        signal.signal(signal.SIGTERM, self._handle_sigterm)
        signal.signal(signal.SIGHUP, self._handle_sighup)
        signal.signal(signal.SIGQUIT, self._handle_sigquit)

    def set_default_gnmi_info(self, gnmi_info: gNMI_Info = None) -> None:
        """Set the default gNMI info for the agent.

        Args:
            gnmi_info (gNMI_Info, optional): gNMI info to be used as defaults

        If no gNMI info is provided, defaults are:
            target_path: "unix:///opt/srlinux/var/run/sr_gnmi_server"
            target_port: 57400
            username: "admin"
            password: "admin"
            insecure: True

        """
        if gnmi_info is None:
            gnmi_info = gNMI_Info(
                target_path="unix:///opt/srlinux/var/run/sr_gnmi_server",
                target_port=57400,
                username="admin",
                password="admin",
                insecure=True,
            )
        self.default_gnmi_info = gnmi_info

    def __enter__(self):
        """Handles basic agent registration.

        - Registers the agent with the SDK Manager.
        - Registers the agent with the Telemetry Service.

        Returns:
            self

        Raises:
            Exception: If the agent registration fails.
        """
        self.channel = grpc.insecure_channel(
            "unix:///opt/srlinux/var/run/sr_sdk_service_manager:50053"
        )

        # Create  base service that defines agent registration, unregistration,
        # notification subscriptions, and keepalive messages.
        self.sdk_mgr_client = SdkMgrServiceStub(self.channel)
        # Create service for handling notifications.
        self.sdk_notification_client = SdkNotificationServiceStub(self.channel)

        # Create the telemetry service to store state data.
        self.sdk_telemetry_client = SdkMgrTelemetryServiceStub(self.channel)

        # Register agent
        register_request = AgentRegistrationRequest()
        register_request.agent_liveliness = self.keepalive_interval
        response = self.sdk_mgr_client.AgentRegister(
            request=register_request, metadata=self.metadata
        )
        if response.status == sdk_status.kSdkMgrSuccess:
            logging.info("Agent registered successfully")
        else:
            logging.error(f"Agent registration failed with error {response.error_str}")

        self._start_keepalive()
        request = NotificationRegisterRequest(op=NotificationRegisterRequest.Create)
        create_subscription_response = self.sdk_mgr_client.NotificationRegister(
            request=request, metadata=self.metadata
        )
        if create_subscription_response.status == sdk_status.kSdkMgrSuccess:
            self.stream_id = create_subscription_response.stream_id
        else:
            logging.warning(f"Failed to create subscription for agent {self.name}")
            raise Exception(f"Failed to create subscription for agent {self.name}")

        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        traceback: Optional[TracebackType],
    ):
        """
        Handles agent unregistration.

        Parameters:
            exc_type: Exception type.
            exc_value: Exception value.
            exc_traceback: Exception traceback.
        """
        logging.info("Exit GreeterAgent")

        if exc_type:
            logging.warning(f"Exception: {exc_type} {exc} :: \n\t{traceback}")

        try:
            self.sdk_mgr_client.AgentUnRegister(
                request=AgentRegistrationRequest(),
                metadata=self.metadata,
            )
        except grpc._channel._Rendezvous as err:
            logging.info(f"Error when unregistering: {err}")
        self.channel.close()

    def _handle_sigterm(self, *arg):
        """Agent recieved SIGTERM signal.
        Clean up and exit.
        """
        logging.info("Received SIGTERM, exiting")
        # Unregister agent
        self._unregister_agent()
        sys.exit()

    def _unregister_agent(self):
        """Attempt to unregister the agent from the SDK Manager."""
        logging.debug("Unregistering agent")
        unregister_request = AgentRegistrationRequest()
        response = self.sdk_mgr_client.AgentUnRegister(
            request=unregister_request, metadata=self.metadata
        )
        if response.status == sdk_status.kSdkMgrSuccess:
            logging.info("Agent unregistered successfully")
        else:
            logging.warning(f"Agent unregistration failed - {response.error_str}")

    def _handle_sighup(self, *arg):
        """Agent recieved SIGHUP signal.
        Reload configuration.
        """
        logging.info("Handle SIGHUP")
        logging.info("Reload config not implemented")

    def _handle_sigquit(self, *arg):
        """Agent recieved SIGQUIT signal.
        Terminate and generate a core dump.
        """
        logging.info("Handle SIGQUIT")
        logging.info("Stop and dump not implemented")

    def _start_keepalive(self):
        """Start keepalive thread."""
        self._keepalive_signal = threading.Event()
        keepalive_thread = threading.Thread(
            target=self.__keepalive, args=(self._keepalive_signal,)
        )
        keepalive_thread.daemon = True
        keepalive_thread.start()

    def _stop_keepalive(self):
        """Stop keepalive thread."""
        self._keepalive_signal.set()

    def __keepalive(self, stop_signal: threading.Event):
        """Start keepalive thread."""
        while not stop_signal.is_set():
            request = KeepAliveRequest()
            res = self.sdk_mgr_client.KeepAlive(request, metadata=self.metadata)
            if res.status == sdk_status.kSdkMgrFailed:
                logging.warning("KeepAlive failed")
            time.sleep(self.keepalive_interval)

    def run(self):
        logging.warning("Run() function not implemented")

    def _update_telemetry(self, path_json: str, data_json: str) -> bool:
        """Update telemetry data.

        Args:
            path_json: JSON string containing the path to the telemetry data.
            data_json: JSON string containing the telemetry data to be updated.

        Returns:
            True if the update was successful, False otherwise.

        Notes:
            The path_json and data_json strings are expected to be in "." notation.
            For example, the path to "interface[name=ethernet-1/1]/vlan-tagging"
            would be:
                .interface{.name=="ethernet-1/1"}.vlan-tagging
        """
        telemetry_update_request = telemetry_service_pb2.TelemetryUpdateRequest()

        # Form data to be sent to the telemetry service.
        telemetry_info = telemetry_update_request.state.add()
        telemetry_info.key.js_path = path_json
        telemetry_info.data.json_content = json.dumps(data_json)

        # Send the telemetry update request.
        response = self.sdk_telemetry_client.TelemetryAddOrUpdate(
            request=telemetry_update_request, metadata=self.metadata
        )

        # Check the response.
        if response.status == sdk_status.kSdkMgrSuccess:
            logging.info("Telemetry update successful")
        else:
            logging.warning(f"Telemetry update failed error: {response.error_str}")

        return response.status

    def _delete_telemetry(self, js_path: str) -> bool:
        """Delete telemetry data.

        Args:
            js_path: js_path of the telemetry data to be deleted.

        Returns:
            True if the delete was successful, False otherwise.
        Notes:
            The path_json and data_json strings are expected to be in "." notation.
            For example, the path to "interface[name=ethernet-1/1]/vlan-tagging"
            would be:
                .interface{.name=="ethernet-1/1"}.vlan-tagging
        """
        telemetry_delete_request = telemetry_service_pb2.TelemetryDeleteRequest()

        # Form data to be sent to the telemetry service.
        telemetry_delete_request.key.add().js_path = js_path

        # Send the telemetry delete request.
        response = self.sdk_telemetry_client.TelemetryDelete(
            request=telemetry_delete_request, metadata=self.metadata
        )

        # Check the response.
        if response.status == sdk_status.kSdkMgrSuccess:
            logging.info("Telemetry delete successful")
        else:
            logging.warning(f"Telemetry delete failed error: {response.error_str}")

        return response.status

    def _get_notifications(self) -> Generator[Notification, None, None]:
        """Checks for notifications.

        Yields:
            Notification: Notification received from the SDK Manager.
        """
        stream_request = NotificationStreamRequest(stream_id=self.stream_id)
        stream_response = self.sdk_notification_client.NotificationStream(
            request=stream_request, metadata=self.metadata
        )

        for response in stream_response:
            for notification in response.notification:
                yield notification

    def _register_for_notifications(
        self,
        *,  # Force keyword arguments only
        intf_request: InterfaceSubscriptionRequest = None,
        nw_request: NetworkInstanceSubscriptionRequest = None,
        lldp_neighbor_request: LldpNeighborSubscriptionRequest = None,
        config_request: ConfigSubscriptionRequest = None,
        bfd_session_request: BfdSessionSubscriptionRequest = None,
        route_request: IpRouteSubscriptionRequest = None,
        appid_request: AppIdentSubscriptionRequest = None,
        nhg_request: NextHopGroupSubscriptionRequest = None,
    ) -> bool:
        """Agent subscribes to notifications from the SDK Manager.

        Args:
            intf_request: InterfaceSubscriptionRequest object.
            nw_request: NetworkInstanceSubscriptionRequest object.
            lldp_neighbor_request: LldpSubscriptionRequest object.
            config_request: ConfigSubscriptionRequest object.
            bfd_session_request: BfdSubscriptionRequest object.
            route_request: IpRouteSubscriptionRequest object.
            appid_request: AppIdentSubscriptionRequest object.
            nhg_request: NextHopGroupSubscriptionRequest object.

        Returns:
            True if subscription is successful, False otherwise.
        """

        request = NotificationRegisterRequest(
            stream_id=self.stream_id,
            op=NotificationRegisterRequest.AddSubscription,
            intf=intf_request,
            nw_inst=nw_request,
            lldp_neighbor=lldp_neighbor_request,
            config=config_request,
            bfd_session=bfd_session_request,
            route=route_request,
            appid=appid_request,
            nhg=nhg_request,
        )

        response = self.sdk_mgr_client.NotificationRegister(
            request=request, metadata=self.metadata
        )
        msg_str = f"stream_id: {response.stream_id} sub_id: {response.sub_id}"
        if response.status == sdk_status.kSdkMgrSuccess:
            logging.info(f"Subscribed successfully :: {msg_str}")
        else:
            logging.error(f"Failed to subscribe :: {msg_str}")
        return response.status

    def _handle_notification(self, notification: Notification):
        """
        Handles notifications.
        """
        data = {field.name: value for field, value in notification.ListFields()}
        sub_id = data["sub_id"]
        logging.debug(f"sub_id: {sub_id}")

        if "config" in data:
            self._handle_ConfigNotification(data["config"])
        if "intf" in data:
            self._handle_InterfaceNotification(data["intf"])
        if "nw_inst" in data:
            self._handle_NetworkInstanceNotification(data["nw_inst"])
        if "lldp_neighbor" in data:
            self._handle_LldpNeighborNotification(data["lldp_neighbor"])
        if "bfd_session" in data:
            self._handle_BfdSessionNotification(data["bfd_session"])
        if "route" in data:
            self._handle_IpRouteNotification(data["route"])
        if "appid" in data:
            self._handle_AppIdentNotification(data["appid"])
        if "nhg" in data:
            self._handle_NextHopGroupNotification(data["nhg"])

        known_fields = [
            "sub_id",
            "config",
            "intf",
            "nw_inst",
            "lldp_neighbor",
            "bfd_session",
            "route",
            "appid",
            "nhg",
        ]
        unknown_fields = {field for field in data if field not in known_fields}
        if unknown_fields:
            logging.warning(
                "Unknown fields in notification verify documentation for "
                f"Notification information - unknown fields: {unknown_fields}"
            )

    def _handle_ConfigNotification(self, notification: ConfigNotification):
        """
        Handles config notifications.
        """
        logging.warning("ConfigNotification handling not implemented")
        logging.info(f"Received ConfigNotification: {notification}")

    def _handle_InterfaceNotification(self, notification: InterfaceNotification):
        """
        Handles interface notifications.
        """
        logging.warning("InterfaceNotification handling not implemented")
        logging.info(f"Received InterfaceNotification: {notification}")

    def _handle_NetworkInstanceNotification(
        self, notification: NetworkInstanceNotification
    ):
        """
        Handles network instance notifications.
        """
        logging.warning("NetworkInstanceNotification handling not implemented")
        logging.info(f"Received NetworkInstanceNotification: {notification}")

    def _handle_LldpNeighborNotification(self, notification: LldpNeighborNotification):
        """
        Handles lldp neighbor notifications.
        """
        logging.warning("LldpNeighborNotification handling not implemented")
        logging.info(f"Received LldpNeighborNotification: {notification}")

    def _handle_BfdSessionNotification(self, notification: BfdSessionNotification):
        """
        Handles bfd session notifications.
        """
        logging.warning("BfdSessionNotification handling not implemented")
        logging.info(f"Received BfdSessionNotification: {notification}")

    def _handle_IpRouteNotification(self, notification: IpRouteNotification):
        """
        Handles ip route notifications.
        """
        logging.warning("IpRouteNotification handling not implemented")
        logging.info(f"Received IpRouteNotification: {notification}")

    def _handle_AppIdentNotification(self, notification: AppIdentNotification):
        """
        Handles app ident notifications.
        """
        logging.warning("AppIdentNotification handling not implemented")
        logging.info(f"Received AppIdentNotification: {notification}")

    def _handle_NextHopGroupNotification(self, notification: NextHopGroupNotification):
        """
        Handles next hop group notifications.
        """
        logging.warning("NextHopGroupNotification handling not implemented")
        logging.info(f"Received NextHopGroupNotification: {notification}")

    def _change_netns(
        self, netns_name: str, *, timeout: int = 10, interval: int = 1
    ) -> bool:
        """
        Changes network namespace to the specified name.

        Args:
            netns_name: Name of the network namespace.
            timeout: Maximum time to wait for the network namespace to be changed.
            interval: Retry interval in seconds.

        Returns:
            True if network namespace is changed, False otherwise.
        """
        while True:
            if netns_name in netns.listnetns():
                logging.info(f"Changing network namespace to {netns_name}")
                netns.setns(netns_name)
                return True
            # TODO: Can we use a better way to check if the network namespace is
            #  available? For now this is a blocking call.
            else:
                time.sleep(interval)
                timeout -= interval
                if timeout <= 0:
                    logging.error(f"Failed to change network namespace to {netns_name}")
                    return False

    def _gnmi_get(
        self,
        paths: Union[str, List[str]],
        *,
        gnmi_info: gNMI_Info = None,
        encoding: str = "json_ietf",
        datatype: str = "all",
    ) -> dict:
        """Get data from gNMI server.
        Args:
            paths: Path(s) to state data to be retrieved (string or list of strings).
            gnmi_info: gNMI server information if not uses the default
                information for the agent.
            encoding: Encoding format for the data to be retrieved.
            datatype: Type of data to be retrieved (all, config, state).
        Returns:
            If the given path is a string, returns the response, otherwise
            return a dictionary of paths and response data Formatted as:
                {"path": response from gNMI server as dict}

        Valid datatype values:
          - all
          - config
          - state
          - operational

        Valid encoding values:
          - json
          - bytes
          - proto
          - ascii
          - json_ietf

        response Format:
            {
                "notification": [
                    {
                        "timestamp": 1660737964042766695,
                        "prefix": None,
                        "alias": None,
                        "atomic": False,
                        "update": [{"path": "path", "val": Requested data}],
                    }
                ]
            }
        to get the value requested, use the following code:
        response["notification"][0]["update"][0]["val"]
        """
        gnmi_info = gnmi_info if gnmi_info else self.default_gnmi_info

        # Check that the data type is valid
        datatype = datatype.lower()
        if datatype not in DATATYPES:
            raise ValueError(f"Invalid datatype: {datatype}")

        # Check that the encoding is valid
        encoding = encoding.lower()
        if encoding not in ENCODINGS:
            raise ValueError(f"Invalid encoding: {encoding}")

        query_info = {"encoding": encoding, "datatype": datatype}
        single_request = isinstance(paths, str)
        if single_request:
            paths = [paths]
        with gNMIclient(**vars(gnmi_info)) as client:
            responses = {}
            try:
                for path in paths:
                    responses[path] = client.get(path=[path], **query_info)
            except gNMIException as err:
                logging.error(f"Error for path {path}: err - {err}")
                raise err
        return responses[paths[0]] if single_request else responses
