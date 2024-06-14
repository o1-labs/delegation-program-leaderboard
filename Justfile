default:
  @just --list --justfile {{justfile()}}

build-web:
  docker build -t leaderboard-web ./web

build-api:
  docker build -t leaderboard-api ./api
