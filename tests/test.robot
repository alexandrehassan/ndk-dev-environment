*** Settings ***
Library           srl.py
Library           SSHLibrary
Library           String
Library           OperatingSystem

*** Keywords ***
Write SRL Command
    [Arguments]    ${cmd}
    ${tmp}=    Write    ${cmd}
    ${out}=    Read Until    [admin@srl2 ~]$
    [Return]    ${out}

Open SRL Bash
    Open Connection    clab-support-dev-srl1    width=500
    Login    admin    admin
    Write    bash
    Read Until    [admin@srl1 ~]$

Agent Defaults
    ${result}=    get_agent_paths
    ${expected}=    expected_paths
    default_paths_set    ${result}    ${expected}

Agent Should Run
    ${result}=    get_agent_status
    Should Be Equal    ${result}    running

Agent Should Not Run
    ${result}=    get_agent_status
    Should Not Be Equal    ${result}    running

Agent Run False
    ${result}=    agent_run_value
    Should Not Be True    ${result}
*** Test Cases ***
Test agent running
    Wait Until Keyword Succeeds    30x    1s
    ...    Agent Should Run

Test agent stop
    stop_agent
    Wait Until Keyword Succeeds    30x    10s
    ...    Agent Should Not Run
    Sleep    5

Test agent start
    start_agent
    Wait Until Keyword Succeeds    30x    1s
    ...    Agent Should Run
    Sleep    5
    
# Test agent defaults
#    Wait Until Keyword Succeeds    30x    1s
#    ...    Agent Should Run
#    Wait Until Keyword Succeeds    5x    1s
#    ...    Agent Defaults

Test agent initial state
    ${result}=    agent_initial_state
    Should Be True    ${result}

Test add path
    ${result}=    paths_added_to_state
    Should Be True    ${result}

Test remove path
    ${result}=    paths_removed_from_state
    Should Be True    ${result}

Test modify path
    ${result}=    paths_modified_in_state
    Should Be True    ${result}


Test agent archive
    # Clear the output directory
    Empty Directory    output/
    Agent Run False
    trigger_agent
    # Wait for the agent to archive
    Sleep   1s
    # An archive should have been created
    OperatingSystem.File Should exist    output/archive.tar
    # The agent should be ready to run again
    Agent Run False
    # Clear the output directory
    Empty Directory    output/
