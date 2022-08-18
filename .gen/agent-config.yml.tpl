# {{ getenv "APPNAME" }} agent configuration file
{{ getenv "APPNAME" }}:
  path: /opt/{{ getenv "APPNAME" }}
  launch-command: /opt/{{ getenv "APPNAME" }}/run.sh
  search-command: python3 /opt/{{ getenv "APPNAME" }}/main.py
  yang-modules:
    names: ["{{ getenv "APPNAME" }}"]
    source-directories:
      - "/opt/{{ getenv "APPNAME" }}/yang"