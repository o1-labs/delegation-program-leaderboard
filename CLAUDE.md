# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Structure

This is a containerized leaderboard application for Mina's Delegation Program with two main components:

- **`/web`** - PHP frontend (PHP 8.0, Bootstrap 4, PostgreSQL) serving the uptime leaderboard interface
- **`/api`** - Python Flask API backend providing REST endpoints to access the delegation program database

Both components are designed to run as Docker containers and connect to a PostgreSQL database containing SNARK work uptime data.

## Common Commands

### Building and Running Locally

Use `just` commands (defined in `Justfile`) for common operations:

```bash
# List all available commands
just

# Build Docker images
just build-web        # Build web frontend
just build-api        # Build API backend  
just build-all        # Build both components

# Launch services
just launch-web       # Start web frontend (port 80)
just launch-api       # Start API backend (port 5000)
just launch-all       # Start both services

# Stop services
just destroy-web      # Stop web frontend
just destroy-api      # Stop API backend
just destroy-all      # Stop all services
```

### Alternative Docker Commands

Without `just`:
```bash
# Build images manually
docker build -t leaderboard-web ./web
docker build -t leaderboard-api ./api

# Run with docker-compose
docker-compose up -d
```

## Configuration

### Environment Setup

Copy and configure environment variables:
```bash
cp .env.example .env
# Edit .env with proper database credentials and API settings
```

### Key Environment Variables

For API (`/api`):
- `SNARK_HOST`, `SNARK_PORT`, `SNARK_USER`, `SNARK_PASSWORD`, `SNARK_DB` - PostgreSQL connection
- `API_HOST`, `API_PORT` - API server binding
- `CACHE_TIMEOUT` - API response caching duration
- `SWAGGER_HOST` - Swagger documentation host

For Web (`/web`):
- `DB_SNARK_*` - Database connection (mirrors API config)
- `IGNORE_APPLICATION_STATUS=1` - Test mode flag (ignores application_status filtering)

## Architecture

### Web Frontend (`/web`)
- **Technology**: PHP 8.0 with Bootstrap 4 frontend
- **Main files**: `index.php` (main interface), `showDataForTabOne.php` (data display), `getPageDataForSnark.php` (data fetching)
- **Database**: Direct PostgreSQL connection via `connectionsnark.php`
- **Assets**: CSS/JS in `/assets` directory

### API Backend (`/api`) 
- **Technology**: Flask Python application with Swagger documentation
- **Main files**: `minanet_app/flask_api.py` (main API), `config.py` (configuration), `logger_util.py` (logging)
- **Features**: Response caching, comprehensive API documentation, PostgreSQL integration
- **Dependencies**: See `requirements.txt` (Flask, psycopg2, flasgger for Swagger)

### Database Integration
Both components connect to the same PostgreSQL database containing delegation program uptime data. The API provides structured access while the web interface offers direct database queries for the leaderboard display.

## Development Workflow

1. Configure environment variables in `.env`
2. Build appropriate component with `just build-web` or `just build-api`
3. Launch services with `just launch-*` commands
4. Access web interface at `localhost:80` and API docs at `localhost:5000` (Swagger UI)

## Deployment

The project includes GitHub Actions workflow (`.github/workflows/publish.yml`) for automated Docker image builds and ECR deployment on tag pushes or manual workflow dispatch.