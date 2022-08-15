from pygnmi.client import gNMIclient
from robot.api import logger

host = ('clab-{{ getenv "APPNAME" }}-dev-srl1', 57400)
cert = "/ca/srl1/srl1.pem"
enc = 'json_ietf'

class srl:
    def __init__(self):
        self.gc = gNMIclient(target=host, username='admin', password='admin', insecure=False, debug=False, path_cert=cert)
        self.gc.__enter__() 

    def start_agent(self):
        m = [(
            "/tools/system/app-management/application[name={{ getenv "APPNAME" }}]",
            {
                "start": ""
            }
        )]
        self.gc.set(update=m, encoding=enc)
    
    def stop_agent(self):
        m = [(
            "/tools/system/app-management/application[name={{ getenv "APPNAME" }}]",
            {
                "stop": ""
            }
        )]
        self.gc.set(update=m, encoding=enc)
    def get_agent_status(self):
        result = self.gc.get(path=['/system/app-management/application[name={{ getenv "APPNAME" }}]/state'], encoding=enc)
        return result['notification'][0]['update'][0]['val']

    def set_name(self):
        m = [(
            "/{{ getenv "APPNAME" }}",
            {
                "name": "seb"
            }
        )]
        self.gc.set(update=m, encoding=enc)
    
    def check_uptime(self):
        result = self.gc.get(path=['/{{ getenv "APPNAME" }}/uptime'], encoding=enc)
        print(f"result is: {result}")
        #return True
        return result['notification'][0]['update'][0]['val']