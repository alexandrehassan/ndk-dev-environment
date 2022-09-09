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
    
Test agent initial state
    agent_initial_state

Test add path
    paths_added_to_state

Test remove path
    paths_removed_from_state

Test modify path
    paths_modified_in_state

Test agent run is config only
    agent_run_not_in_state

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
