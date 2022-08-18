# Greeter App

This repo provides a base agent, the Greeter app and a Makefile for setting up a python based [NDK](https://learn.srlinux.dev/ndk/intro/) development environment. Read more about the approach at [learn.srlinux.dev](https://learn.srlinux.dev/ndk/guide/env/python/).

## Features

The Greeter app demonstrates how agent can interact with the whole state and config tree of SR Linux using local gNMI access and the NDK.

- It subscribes to configuration using the NDK.
- It retrieves the "name" from the configuration notification and update the uptime status with a hardcoded value of 8:00 using a telemetry client.
- It gets the uptime using gNMI. The gNMI client is locally connecting using Unix Domain Socket.
- It logs "Hello myname, my uptime is 8:00"​.

## Quickstart

You need [conatinerlab](https://containerlab.dev/install/) to be installed. Minimum version is v0.31.0 to have Unix domain socket enabled.

Clone the `greeter-app-python` branch.

Initialize the NDK project:

```console
make
```

Now you have all the components of an NDK app generated.

Build the lab and deploy the demo application:

```console
make redeploy-all
```

The app named `greeter` is now running the `srl1` and `srl2` containerlab nodes. The `name` configuration parameter defined in the YANG model is available and you can explore the logs of the app by reading the log file:

```console
tail -f logs/srl1/stdout/greeter.log
```

The greeter app logs will show "greeter/name not configured" on startup so you will have to modify the `greeter/name` configuration using the SR Linux CLI.

## Modify Agent Configuration

Connect to the SR Linux CLI:

```console
ssh admin@clab-greeter-dev-srl1
```

Once connected switch to the candiate mode:

```console
enter candidate private
```

Change the configuration:

```console
set greeter name myname
```

Commit the change:

```console
commit now
```

The greeter agent logs will show this: "hello myname, my uptime is 8:00"

## App Deployment

Build a rpm file to deploy the app on hardware or vm by running this command:

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
