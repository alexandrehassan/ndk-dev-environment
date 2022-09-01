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

*** Test Cases ***
# Test agent running
#     Wait Until Keyword Succeeds    30x    1s
#     ...    Agent Should Run

# Test agent stop
#     stop_agent
#     Wait Until Keyword Succeeds    30x    10s
#     ...    Agent Should Not Run
#     Sleep    5

# Test agent start
#     start_agent
#     Wait Until Keyword Succeeds    30x    1s
#     ...    Agent Should Run
#     Sleep    5
    
Test agent defaults
   Wait Until Keyword Succeeds    30x    1s
   ...    Agent Should Run
   Wait Until Keyword Succeeds    5x    1s
   ...    Agent Defaults

Test agent archive
    Wait Until Keyword Succeeds    30x    1s
    ...    Agent Should Run
    OperatingSystem.File Should not exist    output/archive.tar
    trigger_agent
    Sleep   5
    OperatingSystem.File Should exist    output/archive.tar
    