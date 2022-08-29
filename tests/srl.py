from pygnmi.client import gNMIclient

host = ("clab-support-dev-srl1", 57400)
cert = "/ca/srl1/srl1.pem"
enc = "json_ietf"


class srl:
    def __init__(self):
        self.gc = gNMIclient(
            target=host,
            username="admin",
            password="admin",
            insecure=False,
            debug=False,
            path_cert=cert,
        )
        self.gc.__enter__()

    def start_agent(self):
        m = [("/tools/system/app-management/application[name=support]", {"start": ""})]
        self.gc.set(update=m, encoding=enc)

    def stop_agent(self):
        m = [("/tools/system/app-management/application[name=support]", {"stop": ""})]
        self.gc.set(update=m, encoding=enc)

    def get_agent_status(self):
        result = self.gc.get(
            path=["/system/app-management/application[name=support]/state"],
            encoding=enc,
        )
        return result["notification"][0]["update"][0]["val"]

    def get_agent_paths(self):
        result = self.gc.get(
            path=["/support/files"],
            encoding=enc,
            datatype="config",
        )
        return result["notification"][0]["update"][0]["val"]["files"]

    def default_paths(self):
        paths = {
            "running:/": "running",
            "state:/": "state",
            "show:/interface": "show_interface",
        }
        return [{"path": path, "alias": alias} for path, alias in paths.items()]
