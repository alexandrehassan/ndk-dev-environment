*** Settings ***
Library     srl.py
Library     SSHLibrary
Library     String

*** Keywords ***

Write SRL Command
    [Arguments]         ${cmd}

    ${tmp}=             Write               ${cmd}
    ${out}=             Read Until          [admin@srl2 ~]$
    [return]            ${out}

Open SRL Bash
    Open Connection     clab-support-dev-srl1    width=500
    Login               admin      admin
    Write               bash
    Read Until          [admin@srl1 ~]$

Agent Should Run
    ${result}=              get_agent_status
    Should Be Equal         ${result}   running

Agent Should Not Run
    ${result}=              get_agent_status
    Should Not Be Equal     ${result}   running

*** Test Cases ***
Test agent running
    Wait Until Keyword Succeeds     30x     1s  
    ...    Agent Should Run

Test agent stop
    stop_agent
    Wait Until Keyword Succeeds     30x     1s  
    ...    Agent Should Not Run
    Sleep   5

Test agent start
    start_agent
    Wait Until Keyword Succeeds     30x     1s  
    ...    Agent Should Run
    Sleep   5
