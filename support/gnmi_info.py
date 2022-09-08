class gNMI_Info:
    """
    Class to store gNMI connection info"""

    def __init__(
        self,
        target_path: str,
        target_port: int,
        username: str,
        password: str,
        insecure: bool,
    ) -> None:
        """Initialize gNMI_Info object

        Args:
            target_path: Path to gNMI target
            target_port: Port to gNMI target
            username: Username for gNMI target
            password: Password for gNMI target
            insecure: Whether to use insecure gNMI connection
        """
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
