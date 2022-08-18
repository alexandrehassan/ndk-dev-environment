import logging

from base_agent import BaseAgent

import grpc
import json

from pygnmi.client import gNMIclient

from ndk import sdk_service_pb2
from ndk import config_service_pb2

class Greeter(BaseAgent):
    def __init__(self, name):
        super().__init__(name)

    def __enter__(self):
        super().__enter__()
        self._subscribe()
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        return super().__exit__(exc_type, exc_value, exc_traceback)
    
    def _subscribe(self):
        op = sdk_service_pb2.NotificationRegisterRequest.AddSubscription
        entry = config_service_pb2.ConfigSubscriptionRequest()
        request = sdk_service_pb2.NotificationRegisterRequest(op=op, stream_id=self.stream_id, config=entry)

        subscription_response = self.sdk_mgr_client.NotificationRegister(request=request, metadata=self.metadata)
        logging.info(f"Status of configuration subscription response: {subscription_response.status}")
    
    def _get_name_from_configuration(self, obj) -> str:
        data = json.loads(obj.config.data.json)
        name = data["name"]["value"] if "name" in data else ""
        return name
    
    def _set_uptime(self):
        uptime = "8:00"
        telemetry_data = {"uptime": uptime}
        self._update_telemetry(f".{self.name}", telemetry_data)

    def _handle_notification(self, obj):        
        logging.info("Process notification")
        if obj.config.key.js_path == f".{self.name}":
            name = self._get_name_from_configuration(obj)
            if name == "":
               logging.info("greeter/name not configured") 
            else:
                self._set_uptime()
                up_time_from_gnmi = self._get_uptime_from_state()
                logging.info(f"Hello {name}, my uptime is {json.dumps(up_time_from_gnmi)}")
    
    def _get_uptime_from_state(self) -> str:
        uptime = ""        
        with gNMIclient(target=("unix:///opt/srlinux/var/run/sr_gnmi_server", 57400), username="admin", password="admin", insecure=True) as client:
            response = client.get(path=['/greeter/uptime'], encoding='json_ietf')
            uptime =  response['notification'][0]['update'][0]['val']
        return uptime

    def run(self):
        try:                
            stream_request = sdk_service_pb2.NotificationStreamRequest(stream_id=self.stream_id)
            stream_response = self.sdk_notification_client.NotificationStream(stream_request, metadata=self.metadata)
            logging.info(f"stream_response 1 \n{stream_response}")
           
            for r in stream_response:
                logging.info(f"NOTIFICATION:: \n{r.notification}")
                for obj in r.notification:
                    if obj.HasField("config") and obj.config.key.js_path == ".commit.end":
                        logging.info("TO DO -commit.end config")
                    else:                  
                        self._handle_notification(obj)
        except SystemExit as e:
            logging.info("Handling SystemExit")          
        except grpc._channel._Rendezvous as err:
            logging.error(f'Handling grpc exception: {err}')
        except Exception as e:
            logging.error(f"General exception caught :: {e}")           
        finally:
            logging.info(f"End of notification stream reading")