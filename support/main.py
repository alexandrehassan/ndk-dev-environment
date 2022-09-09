#!/usr/bin/env python
# coding=utf-8

from datetime import datetime
import logging
from support_agent import Support

agent_name = "support"


if __name__ == "__main__":
    formatter = logging.Formatter(
        "%(asctime)s,%(msecs)03d %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    logging.info("START TIME :: {}".format(datetime.now()))

    with Support(name=agent_name) as agent:
        agent.run()

    logging.info("STOP TIME :: {}".format(datetime.now()))
