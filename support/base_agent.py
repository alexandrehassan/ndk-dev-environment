#!/usr/bin/env python
# coding=utf-8

from types import TracebackType
from typing import Generator, List, Optional, Type
import grpc
import sys
import logging
import signal
import json

from pygnmi.client import gNMIclient

from ndk import sdk_service_pb2
from ndk import sdk_service_pb2_grpc
from ndk import telemetry_service_pb2_grpc
from ndk import telemetry_service_pb2
from ndk.config_service_pb2 import ConfigNotification
from ndk.interface_service_pb2 import InterfaceNotification
from ndk.networkinstance_service_pb2 import NetworkInstanceNotification
from ndk.lldp_service_pb2 import LldpNeighborNotification
from ndk.bfd_service_pb2 import BfdSessionNotification
from ndk.route_service_pb2 import IpRouteNotification
from ndk.appid_service_pb2 import AppIdentNotification
from ndk.nexthop_group_service_pb2 import NextHopGroupNotification
from ndk.sdk_common_pb2 import SdkMgrStatus as sdk_status


class BaseAgent(object):
    def __init__(self, name):
        self.name = name
        self.metadata = [("agent_name", self.name)]
        self.stream_id = None

        signal.signal(signal.SIGTERM, self._handle_sigterm)
        signal.signal(signal.SIGHUP, self._handle_sighup)
        signal.signal(signal.SIGQUIT, self._handle_sigquit)

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
        self.sdk_mgr_client = sdk_service_pb2_grpc.SdkMgrServiceStub(self.channel)
        # Create service for handling notifications.
        self.sdk_notification_client = sdk_service_pb2_grpc.SdkNotificationServiceStub(
            self.channel
        )

        # Create the telemetry service to store state data.
        self.sdk_telemetry_client = (
            telemetry_service_pb2_grpc.SdkMgrTelemetryServiceStub(self.channel)
        )

        # Register agent
        self.sdk_mgr_client.AgentRegister(
            request=sdk_service_pb2.AgentRegistrationRequest(), metadata=self.metadata
        )
        request = sdk_service_pb2.NotificationRegisterRequest(
            op=sdk_service_pb2.NotificationRegisterRequest.Create
        )
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
                request=sdk_service_pb2.AgentRegistrationRequest(),
                metadata=self.metadata,
            )
        except grpc._channel._Rendezvous as err:
            logging.info(f"Error when unregistering: {err}")
        self.channel.close()

    def _handle_sigterm(self, *arg):
        """Agent recieved SIGTERM signal.
        Clean up and exit.
        """
        logging.info("Revied SIGTERM, exiting")
        # Unregister agent
        unregister_request = sdk_service_pb2.AgentRegistrationRequest()
        unregister_response = self.sdk_mgr_client.AgentUnRegister(
            request=unregister_request, metadata=self.metadata
        )
        if unregister_response.status == sdk_status.kSdkMgrSuccess:
            logging.info("Agent unregistered successfully")
        else:
            logging.warning("Agent unregistration failed")
        sys.exit()

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

    def run(self):
        logging.warning("Run() function not implemented")

    def _update_telemetry(self, path_json: str, data_json: str) -> None:
        """Update telemetry data.

        Parameters:
            path_json: JSON string containing the path to the telemetry data.
            data_json: JSON string containing the telemetry data to be updated.
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

    def _get_notifications(self) -> Generator[sdk_service_pb2.Notification, None, None]:
        """Checks for notifications.

        Yields:
            Notification: Notification received from the SDK Manager.
        """
        stream_request = sdk_service_pb2.NotificationStreamRequest(
            stream_id=self.stream_id
        )
        stream_response = self.sdk_notification_client.NotificationStream(
            request=stream_request, metadata=self.metadata
        )

        for response in stream_response:
            for notification in response.notification:
                yield notification

    def _get_state_data(
        self,
        path: List[str],
        target_path: str = "unix:///opt/srlinux/var/run/sr_gnmi_server",
        target_port: int = 57400,
        username: str = "admin",
        password: str = "admin",
        insecure: bool = True,
        encoding: str = "json_ietf",
        datatype: str = "all",
    ) -> dict:
        """Get state data from gNMI server.
        Args:
            path: Path to state data.
            target_path: Path to gNMI server.
            target_port: Port of gNMI server.
            username: Username for gNMI server.
            password: Password for gNMI server.
            insecure: Whether to use insecure TLS.
        Returns:
            Response from gNMI server as dict.
            Response Format:
            {
                "notification": [
                    {
                        "timestamp": 1660737964042766695,
                        "prefix": None,
                        "alias": None,
                        "atomic": False,
                        "update": [{"path": "metric:metric/flag", "val": True}],
                    }
                ]
            }
            to get the value requested, use the following code:
            response["notification"][0]["update"][0]["val"]
        """
        with gNMIclient(
            target=(target_path, target_port),
            username=username,
            password=password,
            insecure=insecure,
        ) as client:
            return client.get(path=path, encoding=encoding, datatype=datatype)

    def _set_data(
        self,
        path: List[str],
        data: str,
        target_path: str = "unix:///opt/srlinux/var/run/sr_gnmi_server",
        target_port: int = 57400,
        username: str = "admin",
        password: str = "admin",
        insecure: bool = True,
        encoding: str = "json_ietf",
    ):
        """Set data on gNMI server.
        Args:
            path: Path to state data.
            target_path: Path to gNMI server.
            target_port: Port of gNMI server.
            username: Username for gNMI server.
            password: Password for gNMI server.
            insecure: Whether to use insecure TLS.
        """
        logging.info(f"Setting data on gNMI server: {target_path}:{target_port}")
        logging.info(f"Path: {path}")
        logging.info(f"Data: {data}")
        try:
            with gNMIclient(
                target=(target_path, 57400),
                username=username,
                password=password,
                insecure=insecure,
            ) as client:
                return client.set(update=[(path, data)], encoding=encoding)
        except Exception as e:
            logging.error(f"Error setting data on gNMI server: {e.message} ")
            return None

    def _handle_notification(self, notification: sdk_service_pb2.Notification):
        """
        Handles notifications.
        """
        data = {field.name: value for field, value in notification.ListFields()}
        sub_id = data["sub_id"]
        logging.info(f"sub_id: {sub_id}")

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
