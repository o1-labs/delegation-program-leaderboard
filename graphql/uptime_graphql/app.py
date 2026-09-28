"""ASGI app: /graphql (with GraphiQL), /healthz (liveness), /readyz (DB check)."""

import logging
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from strawberry.asgi import GraphQL

from uptime_graphql.config import Settings
from uptime_graphql.db import Database
from uptime_graphql.schema import Context, build_schema

log = logging.getLogger("uptime_graphql")


class UptimeGraphQL(GraphQL):
    def __init__(self, schema, db, settings):
        super().__init__(schema)
        self.db = db
        self.settings = settings

    async def get_context(self, request, response):
        return Context(db=self.db, settings=self.settings)


def create_app(settings=None, db=None):
    settings = settings or Settings.from_env()
    db = db or Database(settings)

    @asynccontextmanager
    async def lifespan(app):
        await db.open()
        try:
            yield
        finally:
            await db.close()

    async def healthz(request):
        return JSONResponse({"status": "ok"})

    async def readyz(request):
        try:
            await db.ping()
        except Exception as exc:  # noqa: BLE001 - report any DB failure as not ready
            log.warning("readiness check failed: %s", exc)
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return JSONResponse({"status": "ready"})

    return Starlette(
        routes=[
            Route("/healthz", healthz),
            Route("/readyz", readyz),
            Route("/graphql", UptimeGraphQL(build_schema(settings), db, settings)),
        ],
        lifespan=lifespan,
    )


def app():
    """uvicorn factory: `uvicorn --factory uptime_graphql.app:app`."""
    logging.basicConfig(level=logging.INFO)
    return create_app()
