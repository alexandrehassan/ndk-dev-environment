class gNMI_Info:
    """
    Class to store gNMI connection info"""

    def __init__(
        self,
        target_path: str = "unix:///opt/srlinux/var/run/sr_gnmi_server",
        target_port: int = 57400,
        username: str = "admin",
        password: str = "admin",
        insecure: bool = True,
    ):
        self.target = (target_path, target_port)
        self.username = username
        self.password = password
        self.insecure = insecure


class Get_Info:
    """
    Class to store query info"""

    def __init__(self, encoding: str = "json_ietf", datatype: str = "all"):
        self.encoding = encoding
        self.datatype = datatype
