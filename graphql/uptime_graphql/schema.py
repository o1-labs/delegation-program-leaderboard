"""GraphQL schema: block producer uptime and liveness."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import Enum

import strawberry
from strawberry.dataloader import DataLoader
from strawberry.extensions import QueryDepthLimiter
from strawberry.types import Info

from uptime_graphql.db import epoch_to_utc, percent


@strawberry.enum(description="Length of the uptime window, ending at the latest batch.")
class UptimeWindow(Enum):
    DAY = 1
    WEEK = 7
    MONTH = 30


@dataclass
class Context:
    db: object
    settings: object
    last_submission: DataLoader = field(init=False)
    nodes: DataLoader = field(init=False)
    _uptime: dict = field(default_factory=dict, init=False)

    def __post_init__(self):
        self.last_submission = DataLoader(load_fn=self.db.last_submission)
        self.nodes = DataLoader(load_fn=self.db.nodes)

    def uptime(self, window):
        if window not in self._uptime:
            days = window.value
            self._uptime[window] = DataLoader(load_fn=lambda keys: self.db.uptime(keys, days))
        return self._uptime[window]


@strawberry.type(description="Uptime of one block producer over one window.")
class Uptime:
    window: UptimeWindow
    percent: float | None = strawberry.field(
        description="trunc(points * 100 / batches, 2), as in the official score. "
        "Null if the window has no batches."
    )
    points: int = strawberry.field(description="Batches in which the BP earned its point.")
    batches: int = strawberry.field(description="Batches in the window (excluded batches do not count).")
    window_start: datetime | None
    window_end: datetime | None = strawberry.field(description="End of the latest batch.")
    last_point_at: datetime | None = strawberry.field(
        description="End of the last batch in this window in which the BP earned its point."
    )


@strawberry.type(description="The 90-day score that the coordinator stores in `nodes`.")
class OfficialScore:
    score: int | None
    score_percent: float | None
    updated_at: datetime | None
    application_status: bool | None


@strawberry.type
class BlockProducer:
    public_key: str

    @strawberry.field(description="Time of the last submission received from the BP (UTC).")
    async def last_submission_at(self, info: Info) -> datetime | None:
        return await info.context.last_submission.load(self.public_key)

    @strawberry.field(
        description="True if the BP sent a submission in the last `withinMinutes` "
        "minutes (default IS_UP_WINDOW_MINUTES, 40). The submission is not "
        "necessarily verified yet; see uptime.lastPointAt for scored activity."
    )
    async def is_up(self, info: Info, within_minutes: int | None = None) -> bool:
        minutes = info.context.settings.is_up_minutes if within_minutes is None else within_minutes
        if not 1 <= minutes <= 1440:
            raise ValueError("withinMinutes must be between 1 and 1440")
        last = await info.context.last_submission.load(self.public_key)
        return last is not None and last >= datetime.now(UTC) - timedelta(minutes=minutes)

    @strawberry.field
    async def uptime(self, info: Info, window: UptimeWindow) -> Uptime:
        points, batches, last_point_end, window_end = await info.context.uptime(window).load(self.public_key)
        return Uptime(
            window=window,
            percent=percent(points, batches),
            points=points,
            batches=batches,
            window_start=epoch_to_utc(None if window_end is None else window_end - window.value * 86400),
            window_end=epoch_to_utc(window_end),
            last_point_at=epoch_to_utc(last_point_end),
        )

    @strawberry.field
    async def official_score(self, info: Info) -> OfficialScore | None:
        row = await info.context.nodes.load(self.public_key)
        if row is None:
            return None
        score, score_percent, updated_at, application_status = row
        return OfficialScore(
            score=score,
            score_percent=float(score_percent) if isinstance(score_percent, Decimal) else score_percent,
            updated_at=updated_at,
            application_status=application_status,
        )


@strawberry.type
class BlockProducerPage:
    items: list[BlockProducer]
    next_cursor: str | None = strawberry.field(
        description="Pass as `after` to get the next page. Null on the last page."
    )


@strawberry.type
class Meta:
    last_batch_end: datetime | None = strawberry.field(
        description="End of the latest batch. Uptime data is fresh up to this time."
    )
    is_up_window_minutes: int


@strawberry.type
class Query:
    @strawberry.field(description="A BP known from its submissions or its score. Null if the key is unknown.")
    async def block_producer(self, info: Info, public_key: str) -> BlockProducer | None:
        last = await info.context.last_submission.load(public_key)
        node = await info.context.nodes.load(public_key)
        if last is None and node is None:
            return None
        return BlockProducer(public_key=public_key)

    @strawberry.field(description="Scored BPs (rows of `nodes`), ordered by public key.")
    async def block_producers(
        self,
        info: Info,
        first: int = 100,
        after: str | None = None,
        application_status: bool | None = None,
    ) -> BlockProducerPage:
        limit = info.context.settings.max_page_size
        if not 1 <= first <= limit:
            raise ValueError(f"first must be between 1 and {limit}")
        keys = await info.context.db.list_keys(after, first + 1, application_status)
        next_cursor = keys[first - 1] if len(keys) > first else None
        return BlockProducerPage(
            items=[BlockProducer(public_key=key) for key in keys[:first]],
            next_cursor=next_cursor,
        )

    @strawberry.field
    async def meta(self, info: Info) -> Meta:
        return Meta(
            last_batch_end=epoch_to_utc(await info.context.db.last_batch_end()),
            is_up_window_minutes=info.context.settings.is_up_minutes,
        )


def build_schema(settings):
    return strawberry.Schema(
        query=Query,
        extensions=[lambda: QueryDepthLimiter(max_depth=settings.max_query_depth)],
    )
