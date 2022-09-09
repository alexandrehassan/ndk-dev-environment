# Support Agent

When srl users encounter an issue and seek support from peers, they usually are asked to provide config/state information from the node. Given that srl has a very extensive config/state regions, it is cumbersome to extract that information from a lab node and share with a peer. With the support agent we can simplify extraction and sharing parts by having an agent that does it automatically.

## Features

The Support Agent allows an archive containing the state data of given paths automatically.

- Allows the user to set paths that the agent will query and write the output to a file.
- Comes with default paths that can be disabled by the user.
- Paths can be given a alias that will be used as the file name (combined with the timestamp of the query)
- All the files will be added to an archive. (Further archival methods will be added in the future)
- Paths that come enabled by default:
  - `running:/`
  - `state:/`
  - `show:/interface`

## Quickstart

You need [conatinerlab](https://containerlab.dev/install/) to be installed. Minimum version is v0.31.0 to have Unix domain socket enabled.

Clone the `greeter-app-python` branch.

Build the lab and deploy the agent in it:

```console
make redeploy-all
```

The app named `support` is now running the `srl1` and `srl2` containerlab nodes.

## Modify Agent Configuration

Connect to the SR Linux CLI:

```console
ssh admin@clab-greeter-dev-srl1
```

Once connected switch to the candidate mode:

```console
enter candidate
```

To add a path to be queried:

```console
set support files <filepath> alias <alias for path>
```

To disable using default paths:

````console
set support use_default_paths false
```

Commit the changes:

```console
commit now
````

## To run the agent

Connect to the SR Linux CLI and enter candidate mode:

```console
ssh admin@clab-greeter-dev-srl1
enter candidate
```

Set the run parameter to true

```console
set support run true
```

## App Deployment

To build the agent:

```console
make build-app
```

The rpm file is located in /build. Copy the rpm on the SR Linux host and run:

```console
sudo rpm -U myrpm.rpm
```

The app is deployed and the last step is to reload the app-mgr by running this command in the SR Linux CLI:

```console
tools system app-management application app_mgr reload
```

## Test using Robot Framework

[Robot Framework](https://robotframework.org/) can be used to test the agent by running those commands:

### Build Robot Framework docker image

```console
make build-automated-test
```

### Test with dev lab already deployed

```console
make deploy-test-lab
```

```console
make test
```

### Test by deploying dev and test labs

```console
make redeploy_all_and_test
```
