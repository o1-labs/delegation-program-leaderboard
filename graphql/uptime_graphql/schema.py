"""GraphQL schema: block producer uptime and liveness."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Annotated

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


@strawberry.enum(description="Bucket size of an activity histogram.")
class BucketSize(Enum):
    BATCH = 1200  # one coordinator batch (20 min)
    HOUR = 3600
    DAY = 86400


@dataclass(frozen=True)
class Span:
    """Histogram range in epoch seconds: [start, end), buckets of `size`."""

    start: int
    end: int
    size: int


@dataclass
class Context:
    db: object
    settings: object
    last_submission: DataLoader = field(init=False)
    nodes: DataLoader = field(init=False)
    _loaders: dict = field(default_factory=dict, init=False)
    _buckets: int = field(default=0, init=False)

    def __post_init__(self):
        self.last_submission = DataLoader(load_fn=self.db.last_submission)
        self.nodes = DataLoader(load_fn=self.db.nodes)

    def uptime(self, window):
        return self._loader(("uptime", window), lambda keys: self.db.uptime(keys, window.value))

    def activity(self, span):
        return self._loader(
            ("activity", span), lambda keys: self.db.activity(keys, span.start, span.end, span.size)
        )

    def silences(self, start, end, min_minutes):
        return self._loader(
            ("silences", start, end, min_minutes),
            lambda keys: self.db.silences(keys, start, end, min_minutes),
        )

    def spend_buckets(self, count):
        self._buckets += count
        limit = self.settings.max_request_buckets
        if self._buckets > limit:
            raise ValueError(
                f"the request asks for more than {limit} activity buckets in total; "
                "ask for fewer BPs per page or use a larger bucket"
            )

    def _loader(self, cache_key, load_fn):
        # One DataLoader per distinct argument set, so that the same field on
        # many BPs is one SQL query.
        if cache_key not in self._loaders:
            self._loaders[cache_key] = DataLoader(load_fn=load_fn)
        return self._loaders[cache_key]


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


@strawberry.type(description="Activity of one BP in one histogram bucket (or over the whole range).")
class ActivityCounts:
    submissions: int = strawberry.field(description="Submissions received.")
    accepted_submissions: int = strawberry.field(
        description="Submissions verified without error: the ones the coordinator scores."
    )
    failed_submissions: int = strawberry.field(
        description="Submissions that failed verification (verified false or a validation error). "
        "submissions - accepted - failed are not verified yet."
    )
    batches: int = strawberry.field(description="Coordinator batches that start in the bucket.")
    points: int = strawberry.field(description="Batches in which the BP earned its point.")
    percent: float | None = strawberry.field(
        description="trunc(points * 100 / batches, 2); null if no batches."
    )


@strawberry.type
class ActivityBucket(ActivityCounts):
    start: datetime
    end: datetime


@strawberry.type
class ActivityTotals(ActivityCounts):
    buckets_with_submissions: int = strawberry.field(
        description="Buckets with at least one submission, of `bucketCount`."
    )
    bucket_count: int


@strawberry.type(description="A period without any submission from the BP.")
class Silence:
    start: datetime = strawberry.field(description="Last submission before the silence, or the range start.")
    end: datetime = strawberry.field(description="First submission after the silence, or the range end.")
    minutes: int
    open_ended: bool = strawberry.field(
        description="True if the silence lasts until the end of the range: no submission came back."
    )


def _counts(cls, row, **extra):
    submissions, accepted, failed, batches, points = row
    return cls(
        submissions=submissions,
        accepted_submissions=accepted,
        failed_submissions=failed,
        batches=batches,
        points=points,
        percent=percent(points, batches),
        **extra,
    )


@strawberry.type(
    description="Activity of one BP over a custom range. The range is widened to whole "
    "buckets and ends at most at the current time."
)
class Activity:
    public_key: strawberry.Private[str]
    span: strawberry.Private[Span]
    from_: datetime = strawberry.field(name="from")
    to: datetime
    bucket: BucketSize

    @strawberry.field(description="One entry per bucket, oldest first.")
    async def buckets(self, info: Info) -> list[ActivityBucket]:
        rows = await info.context.activity(self.span).load(self.public_key)
        start, size = self.span.start, self.span.size
        return [
            _counts(
                ActivityBucket,
                row,
                start=epoch_to_utc(start + i * size),
                end=epoch_to_utc(start + (i + 1) * size),
            )
            for i, row in enumerate(rows)
        ]

    @strawberry.field(description="Sums over the whole range.")
    async def totals(self, info: Info) -> ActivityTotals:
        rows = await info.context.activity(self.span).load(self.public_key)
        sums = [sum(column) for column in zip(*rows, strict=True)] if rows else [0] * 5
        return _counts(
            ActivityTotals,
            sums,
            buckets_with_submissions=sum(1 for row in rows if row[0]),
            bucket_count=len(rows),
        )

    @strawberry.field(
        description="Periods of at least `minMinutes` without a submission, oldest first. "
        "A shut-down node shows one long silence, usually open-ended; a node with "
        "problems shows short silences, failed submissions or missing points."
    )
    async def silences(self, info: Info, min_minutes: int = 60) -> list[Silence]:
        if not 1 <= min_minutes <= (self.span.end - self.span.start) // 60:
            raise ValueError("minMinutes must be between 1 and the length of the range")
        gaps = await self._gaps(info, min_minutes)
        limit = timedelta(minutes=min_minutes)
        return [gap for gap, _ in gaps if gap.end - gap.start >= limit]

    @strawberry.field(description="The longest period without a submission in the range.")
    async def longest_silence(self, info: Info) -> Silence | None:
        gaps = await self._gaps(info, 60)
        return next((gap for gap, longest in gaps if longest), None)

    async def _gaps(self, info, min_minutes):
        start = epoch_to_utc(self.span.start)
        end = self.to
        rows = await info.context.silences(start, end, min_minutes).load(self.public_key)
        return [
            (
                Silence(
                    start=gap_start,
                    end=gap_end,
                    minutes=int((gap_end - gap_start).total_seconds() // 60),
                    open_ended=gap_end == end,
                ),
                longest,
            )
            for gap_start, gap_end, longest in rows
        ]


def _utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


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

    @strawberry.field(
        description="Histogram of submissions and points over a custom range (UTC if no "
        "time zone is given), to tell a node that was shut down from a node with problems."
    )
    def activity(
        self,
        info: Info,
        from_: Annotated[datetime, strawberry.argument(name="from")],
        to: datetime,
        bucket: BucketSize = BucketSize.HOUR,
    ) -> Activity:
        settings = info.context.settings
        from_, to = _utc(from_), min(_utc(to), datetime.now(UTC))
        if from_ >= to:
            raise ValueError("from must be before to (and before the current time)")
        if to - from_ > timedelta(days=settings.max_activity_days):
            raise ValueError(f"the range must be at most {settings.max_activity_days} days")
        size = bucket.value
        start = int(from_.timestamp()) // size * size
        end = -(-int(to.timestamp()) // size) * size
        if (end - start) // size > settings.max_activity_buckets:
            raise ValueError(
                f"the range has more than {settings.max_activity_buckets} buckets; use a larger bucket"
            )
        info.context.spend_buckets((end - start) // size)
        return Activity(
            public_key=self.public_key,
            span=Span(start, end, size),
            from_=epoch_to_utc(start),
            to=to,
            bucket=bucket,
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
