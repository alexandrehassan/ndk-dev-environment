#!/bin/bash
###########################################################################
# Description:
#     This script will launch the python script of the support agent
#     (forwarding any arguments passed to this script).
###########################################################################


_term (){
    echo "Caugth signal SIGTERM !! "
    kill -TERM "$child" 2>/dev/null
}

function main()
{
    trap _term SIGTERM
    local virtual_env="/opt/support/.venv/bin/activate"
    local main_module="/opt/support/main.py"

    # source the virtual-environment, which is used to ensure the correct python packages are installed,
    # and the correct python version is used
    source "${virtual_env}"

    python3 ${main_module} &

    child=$!
    wait "$child"
}

main "$@"