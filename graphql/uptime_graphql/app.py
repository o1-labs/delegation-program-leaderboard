"""ASGI app: /graphql (with GraphiQL), /healthz (liveness), /readyz (DB check)."""

import asyncio
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

READY_TIMEOUT_S = 5


async def ping_within(db, timeout, background):
    """db.ping(), or TimeoutError after `timeout` seconds.

    The pool timeout bounds only the wait for a connection; a peer that stops
    answering would hang SELECT 1 until TCP gives up. asyncio.wait_for is not
    enough: on cancel, psycopg first tries to cancel the query on the server
    and waits for it (up to 10 s more). So answer at the timeout and let the
    cancellation finish in the background.
    """
    ping = asyncio.ensure_future(db.ping())
    done, _ = await asyncio.wait({ping}, timeout=timeout)
    if not done:
        ping.cancel()
        background.add(ping)
        ping.add_done_callback(background.discard)
        raise TimeoutError(f"no answer from the database in {timeout} s")
    ping.result()


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
    background = set()

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
            await ping_within(db, READY_TIMEOUT_S, background)
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
