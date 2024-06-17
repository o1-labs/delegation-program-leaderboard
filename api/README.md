# Delegation Program Leaderboard API

An API to browse Uptime Service database.

## Description

Flask python application serving API endpoints to browse Delegation Program Uptime Service database.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)
- just(optional)

## Configuration

The following environment variables need to be set to successfully launch the docker container:

```bash
# Delegation Program postgres db details  
SNARK_HOST=
SNARK_PORT=
SNARK_USER=
SNARK_PASSWORD=
SNARK_DB=
# API host:port details to start listening to 
API_HOST=
API_PORT=
SWAGGER_HOST=

# Misc
CACHE_TIMEOUT=
LOGGING_LOCATION=
```
 
## Running locally

This example assumes that you will use `just` to spin up resources using docker-compose executing from the root of the repository

1. If you have `just` installed, check available just recipes(from the root of git repo). You can inspect recipe definitions in `Justfile`.

```bash
$ just
Available recipes:
    default     # List available recipes
    build-api   # Build leaderboard api docker image
    destroy-api # Stop leaderboard-api
    launch-api  # Start leaderboard-api locally
	<..>
```

2.  Copy and edit `.env` file
```bash
$ cp ./api/config_variables.env  ./api/.env
```

3. Try running and accessing it
```bash
$ just build-api
$ just launch-api
```
