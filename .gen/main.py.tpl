#!/usr/bin/env python
# coding=utf-8

from datetime import datetime

import logging
from logging.handlers import RotatingFileHandler

from {{ getenv "APPNAME" }}_agent import {{ getenv "CLASSNAME" }}

agent_name = "{{ getenv "APPNAME" }}"


if __name__ == "__main__":

    log_filename = f"/var/log/srlinux/stdout/{agent_name}.log"
    logging.basicConfig(
        handlers=[RotatingFileHandler(log_filename, maxBytes=3000000, backupCount=5)],
        format="%(asctime)s,%(msecs)03d %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
        level=logging.INFO,
    )
    logging.info("START TIME :: {}".format(datetime.now()))

    with {{ getenv "CLASSNAME" }}(name=agent_name) as agent:
        agent.run()

    logging.info("STOP TIME :: {}".format(datetime.now()))
    