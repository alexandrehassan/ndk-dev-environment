#!/usr/bin/env python
# coding=utf-8

from types import TracebackType
from typing import Generator, Iterable, List, Optional, Tuple, Type, Union
import grpc
import sys
import logging
import signal
import json
import time

from pygnmi.client import gNMIclient, gNMIException

from pyroute2 import netns

from ndk import sdk_service_pb2
from ndk import sdk_service_pb2_grpc
from ndk import telemetry_service_pb2_grpc
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

from gnmi_info import Get_Info, Set_Info, gNMI_Info

SetData = Tuple[List[str], str]


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

    def _gnmi_get(
        self,
        path: List[str],
        gnmi_info: gNMI_Info = gNMI_Info(),
        query_info: Get_Info = Get_Info(),
    ) -> dict:
        """Get state data from gNMI server.
        Args:
            path: Path to state data.
            gnmi_info: gNMI server information.
            query_info: Query information.
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
        with gNMIclient(**vars(gnmi_info)) as client:
            return client.get(path=path, **vars(query_info))

    def _gnmi_set(
        self,
        data: Union[SetData, Iterable[SetData]],
        gnmi_info: gNMI_Info = gNMI_Info(),
        query_info: Set_Info = Set_Info(),
    ):
        """Set data on gNMI server.
        Args:
            data: Tuple containing path and value to set or
                iterable of tuples containing path and value to set.
            gnmi_info: gNMI server information.
            query_info: Query information.

        Returns:
            Response from gNMI server as dict.
        """
        # TODO: This is a temporary fix to ensure that the data is an iterable.
        if isinstance(data, Tuple):
            data = [data]
        logging.info(f"Setting data on gNMI server - {data}")
        responses = {}
        with gNMIclient(**vars(gnmi_info)) as client:
            for datapoint in data:
                logging.info(f"Setting data on gNMI server - {datapoint}")
                try:
                    response = client.set(update=[datapoint], **vars(query_info))
                except gNMIException as e:
                    logging.error(f"Error setting data on gNMI server, continuing: {e}")
                    response = None
                responses[datapoint[0]] = response
        return response

    def _gnmi_set_retry(
        self,
        data: SetData,
        max_retries: int = 10,
        retry_delay: int = 1,
        gnmi_info: gNMI_Info = gNMI_Info(),
        query_info: Set_Info = Set_Info(),
    ) -> dict:
        """Set data on gNMI server retrying if necessary.
        Args:
            data: Tuple containing path and value to set.
            max_retries: Maximum number of retries.
            retry_delay: Delay between retries. (seconds)
            gnmi_info: gNMI server information.
            query_info: Query information.

        Returns:
            Response from gNMI server as dict, or None if unsuccessful.
        """
        with gNMIclient(
            **vars(gnmi_info),
        ) as client:
            while max_retries > 0:
                logging.info(f"try {max_retries}")
                try:
                    response = client.set(update=[data], **vars(query_info))
                    logging.info(
                        f"Succesfully set data on gNMI server - {data[0]} - {data[1]}"
                    )
                    return response
                except gNMIException as e:
                    logging.error(
                        "Error setting data on gNMI server: "
                        f"retrying in {retry_delay} seconds - {e}"
                    )
                    max_retries -= 1
                    time.sleep(retry_delay)
            return None

    def _register_for_notifications(
        self,
        intf_request: InterfaceSubscriptionRequest = None,
        nw_request: NetworkInstanceSubscriptionRequest = None,
        lldp_neighbor_request: LldpNeighborSubscriptionRequest = None,
        config_request: ConfigSubscriptionRequest = None,
        bfd_session_request: BfdSessionSubscriptionRequest = None,
        route_request: IpRouteSubscriptionRequest = None,
        appid_request: AppIdentSubscriptionRequest = None,
        nhg_request: NextHopGroupSubscriptionRequest = None,
    ):
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

        request = sdk_service_pb2.NotificationRegisterRequest(
            stream_id=self.stream_id,
            op=sdk_service_pb2.NotificationRegisterRequest.AddSubscription,
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
        success = response.status == sdk_status.kSdkMgrSuccess
        msg_str = f"stream_id: {response.stream_id} sub_id: {response.sub_id}"
        if success:
            logging.info(f"Subscribed successfully :: {msg_str}")
        else:
            logging.error(f"Failed to subscribe :: {msg_str}")
        return response.status == sdk_status.kSdkMgrSuccess

    def _handle_notification(self, notification: sdk_service_pb2.Notification):
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
        self, netns_name: str, timeout: int = 10, interval: int = 1
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
