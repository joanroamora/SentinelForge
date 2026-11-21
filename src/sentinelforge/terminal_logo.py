"""A small extruded SF, projected into terminal cells with a depth buffer."""

import math
import os
import time
from contextvars import ContextVar
from functools import lru_cache

from rich.align import Align
from rich.console import Console
from rich.live import Live
from rich.text import Text

ANIMATION_ENABLED: ContextVar[bool] = ContextVar("animation_enabled", default=True)
FRAMES_PER_TURN = 48
FPS = 20
_LETTERS = (
    ("11111", "10000", "10000", "11111", "00001", "00001", "11111"),
    ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
)
_PALETTE = ("#135565", "#147d88", "#159e9c", "#22c5b1", "#56e7cc", "#b1ffeb")


@lru_cache(maxsize=1)
def _surfaces() -> tuple[tuple[float, ...], ...]:
    cells = {(column + letter * 7, row)
             for letter, rows in enumerate(_LETTERS)
             for row, line in enumerate(rows) for column, bit in enumerate(line) if bit == "1"}
    points = []
    samples = [step / 4 for step in range(5)]
    for column, row in sorted(cells):
        x, y = column - 6, 3.5 - row
        for u in samples:
            for v in samples:
                points.append((x + u, y - v, 0.8, 0, 0, 1))
                points.append((x + u, y - v, -0.8, 0, 0, -1))
                if (column - 1, row) not in cells:
                    points.append((x, y - u, -0.8 + 1.6 * v, -1, 0, 0))
                if (column + 1, row) not in cells:
                    points.append((x + 1, y - u, -0.8 + 1.6 * v, 1, 0, 0))
                if (column, row - 1) not in cells:
                    points.append((x + u, y, -0.8 + 1.6 * v, 0, 1, 0))
                if (column, row + 1) not in cells:
                    points.append((x + u, y - 1, -0.8 + 1.6 * v, 0, -1, 0))
    return tuple(points)


@lru_cache(maxsize=96)
def _frame(index: int, width: int, height: int, ascii_only: bool) -> Text:
    angle = index * math.tau / FRAMES_PER_TURN
    cosine, sine = math.cos(angle), math.sin(angle)
    pitch_c, pitch_s = math.cos(0.18), math.sin(0.18)
    scale = min((width - 6) / 14, (height - 2) / 3.8)
    depth = [-math.inf] * (width * height)
    pixels: list[tuple[str, str] | None] = [None] * (width * height)
    ramp = ".:-=+*#%@" if ascii_only else "░▒▓█"
    for x, y, z, nx, ny, nz in _surfaces():
        rotated_x, rotated_z = x * cosine + z * sine, -x * sine + z * cosine
        normal_x, normal_z = nx * cosine + nz * sine, -nx * sine + nz * cosine
        view_y, view_z = y * pitch_c - rotated_z * pitch_s, y * pitch_s + rotated_z * pitch_c
        normal_y, normal_z = ny * pitch_c - normal_z * pitch_s, ny * pitch_s + normal_z * pitch_c
        if normal_z <= 0:
            continue
        perspective = 26 / (26 - view_z)
        column = round(width / 2 + rotated_x * scale * perspective)
        row = round((height - 1) / 2 - view_y * scale * 0.5 * perspective)
        if not (0 <= column < width and 0 <= row < height):
            continue
        position = row * width + column
        if view_z <= depth[position]:
            continue
        depth[position] = view_z
        illumination = 0.22 + 0.78 * max(0, -0.36 * normal_x + 0.4 * normal_y + 0.84 * normal_z)
        shade = min(1.0, illumination)
        pixels[position] = (ramp[round(shade * (len(ramp) - 1))],
                            _PALETTE[round(shade * (len(_PALETTE) - 1))])
    output = Text(no_wrap=True, overflow="crop")
    for row in range(height):
        for pixel in pixels[row * width:(row + 1) * width]:
            output.append(pixel[0] if pixel else " ", style=pixel[1] if pixel else "")
        if row != height - 1:
            output.append("\n")
    return output


def logo_frame(index: int = 3, *, width: int = 54, height: int = 13,
               ascii_only: bool = False) -> Text:
    """Copies keep callers from modifying cached frames; a full turn is periodic."""
    if not 24 <= width <= 72 or not 9 <= height <= 20:
        raise ValueError("logo_dimensions_out_of_range")
    return _frame(index % FRAMES_PER_TURN, width, height, ascii_only).copy()


def motion_allowed(term: Console) -> bool:
    disabled = os.environ.get("SENTINELFORGE_NO_ANIMATION", "").lower() not in {"", "0", "false", "no"}
    ci = os.environ.get("CI", "").lower() not in {"", "0", "false", "no"}
    return (ANIMATION_ENABLED.get() and not disabled and not ci
            and term.is_terminal and term.is_interactive and not term.is_dumb_terminal
            and term.width >= 40 and term.height >= 18)


def show_logo(term: Console, *, seconds: float = 1.2) -> None:
    """A finite branding animation, never a progress meter or a wait for input."""
    if not math.isfinite(seconds) or not 0.1 <= seconds <= 30:
        raise ValueError("logo_duration_out_of_range")
    if term.width < 40 or term.height < 18:
        term.print(Text(" SF", style="bold cyan"))
        return
    width = min(54, term.width - 4)

    def render(index: int):
        return Align.center(logo_frame(index, width=width, ascii_only=term.options.ascii_only))

    if motion_allowed(term):
        start = time.monotonic()
        turn_seconds = min(seconds, 2.4)
        with Live(render(0), console=term, auto_refresh=False, transient=True,
                  redirect_stdout=False, redirect_stderr=False, vertical_overflow="crop") as live:
            while (elapsed := time.monotonic() - start) < seconds:
                index = int(elapsed / turn_seconds * FRAMES_PER_TURN)
                live.update(render(index), refresh=True)
                time.sleep(min(1 / FPS, max(0, seconds - (time.monotonic() - start))))
    term.print(render(3))
