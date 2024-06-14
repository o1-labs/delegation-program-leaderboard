# List available recipes
default:
  @just --list --justfile {{justfile()}}

# Recipes
# Build leaderboard web docker image
build-web:
  docker build -t leaderboard-web ./web

# Build leaderboard api docker image
build-api:
  docker build -t leaderboard-api ./api

# Build all leaderboard docker images
build-all: build-web build-api

# Start leaderboard-web locally
launch-web:
  docker-compose up -d leaderboard-web

# Start leaderboard-api locally
launch-api:
  docker-compose up -d leaderboard-api

# Start leaderboard api and web images locally
launch-all: launch-web launch-api

# Stop leaderboard-web
destroy-web:
  docker-compose down leaderboard-web

# Stop leaderboard-api
destroy-api:
  docker-compose down leaderboard-api

# Stop leaderboard api and web
destroy-all:
  docker-compose down
