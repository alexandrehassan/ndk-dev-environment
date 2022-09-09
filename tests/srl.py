from pygnmi.client import gNMIclient

host = ("clab-support-dev-srl1", 57400)
cert = "/ca/srl1/srl1.pem"
enc = "json_ietf"


class srl:
    ROBOT_LIBRARY_SCOPE = "TEST CASE"

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

    def _query_path(self, path: str, datatype: str = "all"):
        return _get_val(self.gc.get(path=[path], encoding=enc, datatype=datatype))

    def start_agent(self):
        m = [("/tools/system/app-management/application[name=support]", {"start": ""})]
        self.gc.set(update=m, encoding=enc)

    def stop_agent(self):
        m = [("/tools/system/app-management/application[name=support]", {"stop": ""})]
        self.gc.set(update=m, encoding=enc)

    def get_agent_status(self):
        path = "/system/app-management/application[name=support]/state"
        return self._query_path(path)

    def agent_initial_state(self):
        result = self._query_path("support")
        # Note: There is no way of checking ready_to_run fast enough to reliably test it
        return all(["run" not in result, result["use_default_paths"]])

    def add_custom_path(self, path, alias):
        self.gc.set(
            update=[(f"/support/files[path={path}]", {"alias": alias})], encoding=enc
        )

    def _remove_all_paths(self):
        self.gc.set(delete=["/support/files"])

    def paths_added_to_state(self):
        # Should start with an empty list
        self._remove_all_paths()
        result = self.gc.get(path=["support/files"], encoding=enc)
        if "update" in result["notification"][0]:
            return False
        path = "support:support/run"
        alias = "support_run"
        self.add_custom_path(path, alias)
        result = self.gc.get(path=["support"], encoding=enc)
        if "files" not in _get_val(result) or len(_get_val(result)["files"]) != 1:
            return False
        res = _get_val(result)["files"][0]
        return res["path"] == path and res["alias"] == alias

    def delete_custom_path(self, path):
        self.gc.set(delete=[f"/support/files[path={path}]"])

    def paths_removed_from_state(self):
        self._remove_all_paths()
        path = "support:support/run"
        self.add_custom_path(path, "support_run")
        self.delete_custom_path(path)
        # result = self.gc.get(path=["support"], encoding=enc)
        result = self._query_path("support")
        return "files" not in result

    def paths_modified_in_state(self):
        self._remove_all_paths()
        path = "support:support/run"
        self.add_custom_path(path, "support_run")
        count = len(_get_val(self.gc.get(path=["support"], encoding=enc))["files"])
        self.gc.set(
            update=[(f"/support/files[path={path}]", {"alias": "support_run2"})],
            encoding=enc,
        )
        # result = self.gc.get(path=["support"], encoding=enc)
        files = self._query_path("support")["files"]
        # files = _get_val(result)["files"]
        return len(files) == count and files[0]["alias"] == "support_run2"

    def agent_run_not_in_state(self):
        # result = self.gc.get(path=["support"], encoding=enc)
        # assert "run" not in _get_val(result)
        result = self._query_path("support")
        assert "run" not in result, "run found in state"
        # result = self.gc.get(path=["support"], encoding=enc, datatype="config")
        result = self._query_path("support", datatype="config")
        # assert "run" in _get_val(result)
        assert "run" in result, "run not found in config"

    def agent_run_value(self):
        # result = self.gc.get(path=["support/run"], encoding=enc, datatype="config")
        try:
            # return _get_val(result)
            return self._query_path("support/run", datatype="config")
        except KeyError:
            return False

    def trigger_agent(self):
        self._remove_all_paths()
        result = self.gc.set(update=[("/support/run", True)], encoding=enc)
        print(result)


def _get_val(message: dict):
    return message["notification"][0]["update"][0]["val"]
