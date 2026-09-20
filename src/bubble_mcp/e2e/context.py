"""The object a case module receives: everything a case needs, and nothing it must set up.

A case module declares exactly one thing::

    def run(ctx):
        with ctx.step("notes-tab"):
            ctx.click(ctx.page.get_by_text("Notes", exact=True).first)

By the time ``run`` is called the browser is open, the impersonated session is loaded, the
base URL already points at the right branch, and the recording - if any - is running. What is
left in the module is the behaviour under test, which is the only part a reader should have to
think about.

``ctx.step`` is what turns a run into a report: each block is timed, screenshotted on the way
out, and named in the result, so a failure says *which* step broke instead of only that the
case did.
"""

from __future__ import annotations

import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from bubble_mcp.e2e import driver
from bubble_mcp.e2e.paths import safe_slug
from bubble_mcp.e2e.target import ResolvedTarget


@dataclass
class StepRecord:
    """One ``with ctx.step(...)`` block, as the result will describe it."""

    index: int
    name: str
    status: str = "running"
    duration_ms: int = 0
    screenshot: str | None = None
    message: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "index": self.index,
            "name": self.name,
            "status": self.status,
            "duration_ms": self.duration_ms,
        }
        if self.screenshot:
            payload["screenshot"] = self.screenshot
        if self.message:
            payload["message"] = self.message
        return payload


@dataclass
class CaseOptions:
    """Per-run switches a case may read but should rarely need to."""

    video: bool = False
    cursor: bool = False
    animate_waits: bool = True
    screenshot_steps: bool = True
    default_timeout_ms: int = 30_000


@dataclass
class E2EContext:
    """The stable surface a case module is written against."""

    page: Any
    target: ResolvedTarget
    case_id: str
    artifact_dir: Path
    fixtures_dir: Path
    params: dict[str, Any] = field(default_factory=dict)
    options: CaseOptions = field(default_factory=CaseOptions)
    data: dict[str, Any] = field(default_factory=dict)
    steps: list[StepRecord] = field(default_factory=list)
    started_at: float = field(default_factory=time.monotonic)
    ready_at: float | None = None
    _shot_index: int = 0

    # -- addressing ----------------------------------------------------------------

    @property
    def base_url(self) -> str:
        return self.target.base_url

    def url(self, path: str = "", **query: Any) -> str:
        """Build an app URL from a path and query parameters, never a hardcoded host."""

        url = self.target.url(path)
        pairs = {key: value for key, value in query.items() if value is not None}
        return f"{url}?{urlencode(pairs)}" if pairs else url

    def goto(self, path: str = "", *, wait_until: str = "domcontentloaded", **query: Any) -> None:
        self.page.goto(self.url(path, **query), wait_until=wait_until)

    def wait_for_url(self, pattern: str, *, timeout: int | None = None) -> None:
        """Wait until the address bar matches a regular expression.

        Playwright's Python API wants a compiled pattern here and treats a plain string as a
        glob, which silently never matches something like ``section=notes``. Compiling it here
        keeps that trap out of every case.
        """

        self.page.wait_for_url(
            re.compile(pattern), timeout=timeout or self.options.default_timeout_ms
        )

    def url_param(self, name: str, *, pattern: str = r"[0-9]+x[0-9]+") -> str:
        """Pull a value out of the current URL - how a case learns the id it just opened."""

        match = re.search(rf"{re.escape(name)}=({pattern})", self.page.url)
        if not match:
            raise AssertionError(
                f"No {name!r} matching {pattern!r} in the current URL: {self.page.url}"
            )
        return match.group(1)

    # -- locating ------------------------------------------------------------------

    def locator(self, target: Any) -> Any:
        """Accept either a CSS selector or an already-built locator, so cases can mix both."""

        return self.page.locator(target) if isinstance(target, str) else target

    def expect(self, target: Any) -> Any:
        from playwright.sync_api import expect as playwright_expect

        return playwright_expect(self.locator(target))

    def fixture(self, name: str) -> Path:
        """A file the suite ships alongside its cases, for uploads."""

        path = self.fixtures_dir / name
        if not path.exists():
            raise FileNotFoundError(
                f"Fixture {name!r} not found at {path}. Put the file in the profile's "
                "fixtures directory."
            )
        return path

    def unique(self, prefix: str) -> str:
        """A timestamped value, so a case can assert later on exactly what it typed."""

        return driver.unique_label(prefix)

    # -- acting --------------------------------------------------------------------

    def move_to(self, target: Any, *, steps: int = 30) -> None:
        driver.move_to(self.page, self.locator(target), steps=steps)

    def click(self, target: Any, *, settle_ms: int = 900) -> None:
        locator = self.locator(target)
        self.move_to(locator)
        locator.click()
        self.page.wait_for_timeout(settle_ms)

    def type(self, target: Any, text: str, *, delay: int = 45, clear: bool = False) -> None:
        locator = self.locator(target)
        self.move_to(locator)
        locator.click()
        if clear:
            locator.fill("")
        locator.type(text, delay=delay)
        self.page.wait_for_timeout(300)

    def fill(self, target: Any, text: str) -> None:
        locator = self.locator(target)
        self.move_to(locator)
        locator.click()
        locator.fill(text)
        self.page.wait_for_timeout(300)

    def upload(self, target: Any, fixture_name: str) -> None:
        self.locator(target).set_input_files(str(self.fixture(fixture_name)))

    def wait(self, ms: int) -> None:
        driver.wait_alive(self.page, ms, animate=self.options.animate_waits)

    def mark_ready(self) -> None:
        """Note the moment the app finished booting, so the recording can be trimmed to it."""

        if self.ready_at is None:
            self.ready_at = time.monotonic()

    # -- presentation --------------------------------------------------------------

    def zoom_on(self, target: Any, *, scale: float = 1.6, hold_ms: int = 3500) -> None:
        """Blow an element up on a dimmed backdrop - for demo recordings, not for assertions."""

        locator = self.locator(target)
        locator.scroll_into_view_if_needed()
        self.page.wait_for_timeout(400)
        locator.evaluate(driver.ZOOM_ON_SCRIPT, scale)
        self.page.wait_for_timeout(hold_ms)

    def zoom_off(self) -> None:
        self.page.evaluate(driver.ZOOM_OFF_SCRIPT)
        self.page.wait_for_timeout(900)

    # -- recording -----------------------------------------------------------------

    def shot(self, name: str = "", *, target: Any = None) -> Path:
        """Save a numbered screenshot of the page, or of one element."""

        self._shot_index += 1
        label = safe_slug(name) or "shot"
        path = self.artifact_dir / f"{self._shot_index:02d}-{label}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        if target is None:
            self.page.screenshot(path=str(path))
        else:
            self.locator(target).screenshot(path=str(path))
        return path

    @contextmanager
    def step(self, name: str) -> Iterator[StepRecord]:
        """Name, time and screenshot a slice of the case; a failure is attributed to it."""

        record = StepRecord(index=len(self.steps) + 1, name=name)
        self.steps.append(record)
        started = time.monotonic()
        try:
            yield record
        except BaseException as error:
            record.status = "failed"
            record.duration_ms = int((time.monotonic() - started) * 1000)
            record.message = f"{type(error).__name__}: {error}"
            record.screenshot = self._safe_shot(f"{name}-failed")
            raise
        record.status = "passed"
        record.duration_ms = int((time.monotonic() - started) * 1000)
        if self.options.screenshot_steps:
            record.screenshot = self._safe_shot(name)

    def _safe_shot(self, name: str) -> str | None:
        """A screenshot that cannot itself fail the case - a dead page is not the assertion."""

        try:
            return str(self.shot(name))
        except Exception:  # noqa: BLE001 - evidence capture must never mask the real failure
            return None
