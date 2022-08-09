name: "{{ getenv "APPNAME" }}-dev"

topology:
  defaults:
    kind: srl
    image: ghcr.io/nokia/srlinux:22.6.2

  nodes:
    srl1:
      binds:
        - "../{{ getenv "APPNAME" }}:/opt/{{ getenv "APPNAME" }}" # mount dir with agent code
        - "../logs/srl1:/var/log/srlinux" # expose srlinux logs to a dev machine
        - "../{{ getenv "APPNAME" }}.yml:/tmp/{{ getenv "APPNAME" }}.yml" # put agent config file in the tmp directory and move it to appmgr directory after deployment
    srl2:
      binds:
        - "../{{ getenv "APPNAME" }}:/opt/{{ getenv "APPNAME" }}" # mount dir with agent code
        - "../logs/srl2:/var/log/srlinux" # expose srlinux logs to a dev machine
        - "../{{ getenv "APPNAME" }}.yml:/tmp/{{ getenv "APPNAME" }}.yml" # put agent config file in the tmp directory and move it to appmgr directory after deployment 
  links:
    - endpoints:
        - "srl1:e1-1"
        - "srl2:e1-1"