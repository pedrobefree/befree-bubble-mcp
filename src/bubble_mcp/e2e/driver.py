"""Browser-side plumbing shared by every case, so no case carries a copy of it.

The three Kaimia scripts this replaces each held their own copy of the demo cursor, the
"keep the recording alive" wait, the pointer move and the hardcoded path to Playwright's
bundled ffmpeg. All four live here once. The cursor and the recording are optional because a
scheduled regression run wants neither.
"""

from __future__ import annotations

import math
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

CURSOR_SCRIPT = """
(() => {
  const draw = () => {
    if (document.getElementById('e2e-cursor')) return;
    const dot = document.createElement('div');
    dot.id = 'e2e-cursor';
    dot.style.cssText = [
      'position:fixed', 'z-index:2147483647', 'width:22px', 'height:22px',
      'margin:-11px 0 0 -11px', 'border-radius:50%',
      'background:rgba(255,64,96,.35)', 'border:2px solid rgba(255,64,96,.9)',
      'box-shadow:0 0 12px rgba(255,64,96,.7)', 'pointer-events:none',
      'transition:transform .12s ease', 'left:-100px', 'top:-100px'
    ].join(';');
    document.body.appendChild(dot);
    document.addEventListener('mousemove', (e) => {
      dot.style.left = e.clientX + 'px';
      dot.style.top = e.clientY + 'px';
    }, true);
    document.addEventListener('mousedown', () => { dot.style.transform = 'scale(.6)'; }, true);
    document.addEventListener('mouseup', () => { dot.style.transform = 'scale(1)'; }, true);
  };
  if (document.body) draw(); else document.addEventListener('DOMContentLoaded', draw);
})();
"""

ZOOM_ON_SCRIPT = """(el, scale) => {
    const overlay = document.createElement('div');
    overlay.id = 'e2e-zoom';
    overlay.style.cssText = [
      'position:fixed', 'inset:0', 'z-index:2147483646',
      'background:rgba(15,23,42,.55)', 'display:flex',
      'align-items:center', 'justify-content:center',
      'opacity:0', 'transition:opacity .5s ease'
    ].join(';');
    const box = document.createElement('div');
    box.style.cssText = [
      'background:#fff', 'border-radius:10px', 'padding:8px',
      'box-shadow:0 24px 60px rgba(0,0,0,.35)',
      `width:${el.offsetWidth}px`,
      `transform:scale(${scale})`, 'transform-origin:center center'
    ].join(';');
    box.innerHTML = el.outerHTML;
    overlay.appendChild(box);
    document.body.appendChild(overlay);
    void box.offsetWidth;
    requestAnimationFrame(() => { overlay.style.opacity = '1'; });
}"""

ZOOM_OFF_SCRIPT = """() => {
    const overlay = document.getElementById('e2e-zoom');
    if (!overlay) return;
    overlay.style.opacity = '0';
    setTimeout(() => overlay.remove(), 500);
}"""


def browsers_root() -> Path:
    """Where Playwright keeps its downloaded browsers and its bundled ffmpeg."""

    configured = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    if configured and configured != "0":
        return Path(configured).expanduser()
    system = platform.system()
    if system == "Windows":
        local = os.environ.get("LOCALAPPDATA", "").strip()
        base = Path(local) if local else Path.home() / "AppData" / "Local"
        return base / "ms-playwright"
    if system == "Darwin":
        return Path.home() / "Library" / "Caches" / "ms-playwright"
    return Path.home() / ".cache" / "ms-playwright"


def find_ffmpeg() -> Path | None:
    """Playwright's own ffmpeg, if it was installed. Absent means video trimming is skipped.

    The scripts this replaces pinned ``ffmpeg-1010/ffmpeg-win64.exe``, which breaks on the next
    Playwright release and on any machine that is not Windows.
    """

    root = browsers_root()
    if not root.is_dir():
        return None
    candidates = sorted(root.glob("ffmpeg-*/ffmpeg-*"), reverse=True)
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK | os.R_OK):
            return candidate
    return candidates[0] if candidates else None


def trim_video(video: Path, skip_seconds: float, *, destination: Path | None = None) -> Path:
    """Drop the blank head of a recording - the seconds the app spends booting.

    A failure here is never a test failure: the untrimmed video is still evidence, so the
    original path comes back unchanged rather than raising.
    """

    if skip_seconds < 1 or not video.exists():
        return video
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        return video
    target = destination or video.with_name(f"{video.stem}-trimmed{video.suffix}")
    try:
        subprocess.run(
            [
                str(ffmpeg),
                "-loglevel",
                "error",
                "-ss",
                f"{skip_seconds:.1f}",
                "-i",
                str(video),
                "-c",
                "copy",
                str(target),
                "-y",
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return video
    if not target.exists() or target.stat().st_size == 0:
        return video
    try:
        video.unlink()
    except OSError:
        pass
    return target


def nudge_pointer(page: Any, elapsed_index: int, *, centre: tuple[int, int] = (720, 450)) -> None:
    """Trace a small circle so a recorded wait does not look like a frozen frame."""

    x, y = centre
    page.mouse.move(
        x + 60 * math.cos(elapsed_index / 2),
        y + 40 * math.sin(elapsed_index / 2),
        steps=6,
    )


def wait_alive(page: Any, ms: int, *, step: int = 700, animate: bool = True) -> None:
    """Wait ``ms`` milliseconds, keeping the pointer moving when a video is being recorded."""

    waited = 0
    index = 0
    while waited < ms:
        page.wait_for_timeout(min(step, ms - waited))
        waited += step
        index += 1
        if animate:
            nudge_pointer(page, index)


def move_to(page: Any, locator: Any, *, steps: int = 30, settle_ms: int = 700) -> None:
    """Walk the pointer onto an element so a viewer sees where the next click lands."""

    locator.scroll_into_view_if_needed()
    page.wait_for_timeout(400)
    box = locator.bounding_box()
    if not box:
        return
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=steps)
    page.wait_for_timeout(settle_ms)


def latest_video(directory: Path) -> Path | None:
    videos = [item for item in directory.glob("*.webm") if item.is_file()]
    return max(videos, key=lambda item: item.stat().st_mtime) if videos else None


def unique_label(prefix: str, *, moment: float | None = None) -> str:
    """A value a case can type into a field now and assert on a screen later."""

    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(moment or time.time()))
    return f"{prefix} {stamp}".strip()


def install_error_note() -> str:
    """One sentence that tells the caller how to get a browser, wherever they are running."""

    return (
        f"Playwright is not installed for {Path(sys.executable).name}. Install the browser "
        "extra with: pip install 'befree-bubble-mcp[browser]' && python -m playwright install "
        "chromium"
    )
