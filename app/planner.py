"""Offline e-paper refresh planning.

Given an initial screen and 1..20 target screens (0/1 string grids of equal
size, 1..4 rows/columns), find the minimum-cost per-frame refresh plan.

For every changed frame either:

* ``full``    - cost ``full_cost``; all per-cell partial counts reset to 0.
* ``partial`` - cost ``area * cell_cost`` for the minimal axis-aligned
                bounding rectangle of the changed cells; every cell inside
                the rectangle (changed or not) has its count incremented and
                no count may exceed ``max_partial``.

Unchanged frames can only be skipped.

The state of the dynamic program is the per-cell partial counter grid.
Two states with the same grid are merged keeping the lower cost (and the
mode-sequence tie-break key). In addition, at every step counter-grid A
*dominates* counter-grid B when every cell count in A is <= the count in B:
from A there is always an equally good or better continuation (it survives
strictly more future partial rectangles), so B may be discarded. The
dominated Pareto frontier stays tiny (at most one state per possible last
full-refresh position), which makes even the 4x4 / 20-frame corner cases
trivial.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Mode ranks used both for transitions and for lexicographic tie-breaking:
# at equal total cost, a frame choosing full outranks partial, which
# outranks skip (skip is only legal on unchanged frames).
RANK_FULL = 0
RANK_PARTIAL = 1
RANK_SKIP = 2

MODE_BY_RANK = {RANK_FULL: "full", RANK_PARTIAL: "partial", RANK_SKIP: "skip"}


class ValidationError(ValueError):
    """Raised when the request payload is not a valid planning input."""


@dataclass(frozen=True)
class FrameDecision:
    mode: str
    rect: tuple[int, int, int, int] | None  # (top, left, bottom, right), closed


@dataclass(frozen=True)
class Plan:
    decisions: tuple[FrameDecision, ...]
    total_cost: int


def _is_int(value: Any) -> bool:
    # bool is a subclass of int; True/False are not accepted as integers.
    return isinstance(value, int) and not isinstance(value, bool)


def _as_grid(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or not value or len(value) > 4:
        raise ValidationError(f"{name} must be a list of 1 to 4 rows")
    width: int | None = None
    rows: list[str] = []
    for row in value:
        if not isinstance(row, str):
            raise ValidationError(f"{name} rows must be strings")
        if not (1 <= len(row) <= 4):
            raise ValidationError(f"{name} rows must have 1 to 4 columns")
        if width is None:
            width = len(row)
        elif len(row) != width:
            raise ValidationError(f"{name} rows must have equal length")
        if any(ch not in "01" for ch in row):
            raise ValidationError(f"{name} may only contain the characters 0 and 1")
        rows.append(row)
    return rows


def validate_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValidationError("request body must be a JSON object")

    allowed = {"initial", "frames", "max_partial", "full_cost", "cell_cost"}
    unknown = set(payload) - allowed
    if unknown:
        raise ValidationError(f"unexpected fields: {', '.join(sorted(unknown))}")

    for field in allowed:
        if field not in payload:
            raise ValidationError(f"missing required field: {field}")

    initial = _as_grid(payload["initial"], "initial")
    raw_frames = payload["frames"]
    if not isinstance(raw_frames, list) or not (1 <= len(raw_frames) <= 20):
        raise ValidationError("frames must be a list of 1 to 20 grids")
    frames = [_as_grid(grid, "frames") for grid in raw_frames]

    height, width = len(initial), len(initial[0])
    for i, grid in enumerate(frames):
        if len(grid) != height or len(grid[0]) != width:
            raise ValidationError(f"frames[{i}] must match the initial grid size")

    max_partial = payload["max_partial"]
    if not _is_int(max_partial) or not (0 <= max_partial <= 3):
        raise ValidationError("max_partial must be an integer in [0, 3]")

    full_cost = payload["full_cost"]
    cell_cost = payload["cell_cost"]
    if not _is_int(full_cost) or full_cost < 1:
        raise ValidationError("full_cost must be a positive integer")
    if not _is_int(cell_cost) or cell_cost < 1:
        raise ValidationError("cell_cost must be a positive integer")

    return {
        "initial": initial,
        "frames": frames,
        "max_partial": max_partial,
        "full_cost": full_cost,
        "cell_cost": cell_cost,
    }


def _bounding_rect(prev: list[str], cur: list[str], height: int, width: int):
    """Return (top, left, bottom, right, changed cell indexes) or None."""
    top, bottom = height, -1
    left, right = width, -1
    changed: list[int] = []
    for r in range(height):
        base = r * width
        for c in range(width):
            if prev[r][c] != cur[r][c]:
                changed.append(base + c)
                if r < top:
                    top = r
                if r > bottom:
                    bottom = r
                if c < left:
                    left = c
                if c > right:
                    right = c
    if not changed:
        return None
    return top, left, bottom, right, changed


def _rect_indexes(rect, width: int) -> range | list[int]:
    top, left, bottom, right = rect
    return [
        r * width + c
        for r in range(top, bottom + 1)
        for c in range(left, right + 1)
    ]


def solve(
    initial: list[str],
    frames: list[list[str]],
    max_partial: int,
    full_cost: int,
    cell_cost: int,
) -> Plan:
    height = len(initial)
    width = len(initial[0])
    n = len(frames)

    rects: list[tuple[int, int, int, int] | None] = []
    rect_cells: list[tuple[int, ...]] = []
    prev_grid = initial
    for grid in frames:
        found = _bounding_rect(prev_grid, grid, height, width)
        if found is None:
            rects.append(None)
            rect_cells.append(())
        else:
            top, left, bottom, right, _changed = found
            rect = (top, left, bottom, right)
            rects.append(rect)
            rect_cells.append(tuple(_rect_indexes(rect, width)))
        prev_grid = grid

    zero = (0,) * (height * width)

    # DP frontier: counters tuple -> (cost, mode-rank key tuple)
    # Frontier states are pairwise non-dominating after each prune.
    frontier: dict[tuple[int, ...], tuple[int, tuple[int, ...]]] = {
        zero: (0, ())
    }

    for frame_idx in range(n):
        rect = rects[frame_idx]
        cells = rect_cells[frame_idx]
        candidates: dict[tuple[int, ...], tuple[int, tuple[int, ...]]] = {}

        def offer(counters, cost, key):
            old = candidates.get(counters)
            if old is None or (cost, key) < old:
                candidates[counters] = (cost, key)

        for counters, (cost, key) in frontier.items():
            if rect is None:
                # Unchanged frame: skipping is the only legal action.
                offer(counters, cost, key + (RANK_SKIP,))
                continue

            # Full refresh: counters clear to zero.
            offer(zero, cost + full_cost, key + (RANK_FULL,))

            # Partial refresh of the changed cells' bounding rectangle.
            if all(counters[i] < max_partial for i in cells):
                updated = list(counters)
                for i in cells:
                    updated[i] += 1
                area = (rect[2] - rect[0] + 1) * (rect[3] - rect[1] + 1)
                offer(
                    tuple(updated),
                    cost + area * cell_cost,
                    key + (RANK_PARTIAL,),
                )

        # Dominance pruning: drop a state when another state is component-wise
        # no larger on every cell and strictly better on (cost, mode key).
        items = list(candidates.items())
        survivors: dict[tuple[int, ...], tuple[int, tuple[int, ...]]] = {}
        for counters, value in items:
            dominated = False
            for other_counters, other_value in items:
                if other_counters == counters:
                    continue
                if all(a <= b for a, b in zip(other_counters, counters)) and (
                    other_value <= value
                ):
                    dominated = True
                    break
            if not dominated:
                survivors[counters] = value
        frontier = survivors

    best_counters = min(frontier, key=lambda c: frontier[c])
    best_cost, best_key = frontier[best_counters]

    decisions = tuple(
        FrameDecision(mode=MODE_BY_RANK[rank], rect=rects[i] if rank == RANK_PARTIAL else None)
        for i, rank in enumerate(best_key)
    )
    return Plan(decisions=decisions, total_cost=best_cost)


def plan_payload(payload: Any) -> dict[str, Any]:
    """Validate a raw JSON payload and build the response body."""
    data = validate_payload(payload)
    plan = solve(
        data["initial"],
        data["frames"],
        data["max_partial"],
        data["full_cost"],
        data["cell_cost"],
    )
    return {
        "modes": [d.mode for d in plan.decisions],
        "plan": [
            {
                "index": i,
                "mode": d.mode,
                **(
                    {"rect": {"top": d.rect[0], "left": d.rect[1],
                              "bottom": d.rect[2], "right": d.rect[3]}}
                    if d.rect is not None
                    else {}
                ),
            }
            for i, d in enumerate(plan.decisions)
        ],
        "total_cost": plan.total_cost,
    }
