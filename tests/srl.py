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
        assert "run" not in result, "run found in state, should be config only"
        assert result["use_default_paths"], "use_default_paths not true by default"

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
        assert (
            "update" not in result["notification"][0]
        ), f"Path list not empty to start {result}"

        # Check that a path is added correctly
        # Add the path
        path = "support:support/run"
        alias = "support_run"
        self.add_custom_path(path, alias)

        # Query the new state and check that the path is there
        result = self.gc.get(path=["support"], encoding=enc)
        assert "files" in _get_val(result), "No paths found in state"
        assert len(_get_val(result)["files"]) == 1, "More than one path found in state"

        res = _get_val(result)["files"][0]
        assert res["path"] == path, "Path not found in state"
        assert res["alias"] == alias, "Path's alias not correct in state"

    def delete_custom_path(self, path):
        self.gc.set(delete=[f"/support/files[path={path}]"])

    def paths_removed_from_state(self):
        self._remove_all_paths()
        path = "support:support/run"
        self.add_custom_path(path, "support_run")
        self.delete_custom_path(path)
        # result = self.gc.get(path=["support"], encoding=enc)
        result = self._query_path("support")
        assert "files" not in result

    def paths_modified_in_state(self):
        self._remove_all_paths()
        path = "support:support/run"
        self.add_custom_path(path, "support_run")
        count = len(_get_val(self.gc.get(path=["support"], encoding=enc))["files"])
        self.gc.set(
            update=[(f"/support/files[path={path}]", {"alias": "support_run2"})],
            encoding=enc,
        )
        files = self._query_path("support")["files"]

        assert len(files) == count, "A new path was added instead of modified"
        assert files[0]["alias"] == "support_run2", "Path was not modified"

    def agent_run_not_in_state(self):
        result = self._query_path("support")
        assert "run" not in result, "run found in state"

    def agent_run_value(self):
        try:
            return self._query_path("support/run", datatype="config")
        except KeyError:
            # If it doesn't exist it means it's false
            return False

    def trigger_agent(self):
        self._remove_all_paths()
        self.gc.set(update=[("/support/run", True)], encoding=enc)


def _get_val(message: dict):
    return message["notification"][0]["update"][0]["val"]
