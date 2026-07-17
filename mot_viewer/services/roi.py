from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any


MIN_ROI_SIZE = 2


@dataclass(frozen=True)
class RoiRect:
    x: int
    y: int
    width: int
    height: int

    @property
    def x2(self) -> int:
        return self.x + self.width

    @property
    def y2(self) -> int:
        return self.y + self.height


@dataclass(frozen=True)
class SourceSize:
    width: int
    height: int


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    error: str | None = None


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _to_int(value: Any) -> int:
    return int(round(float(value)))


def validate_size(size: SourceSize) -> ValidationResult:
    if not _finite(size.width) or not _finite(size.height):
        return ValidationResult(False, "Source dimensions must be finite")
    if int(size.width) <= 0 or int(size.height) <= 0:
        return ValidationResult(False, "Source dimensions must be positive")
    return ValidationResult(True)


def validate_rect(rect: RoiRect, source: SourceSize | None = None) -> ValidationResult:
    values = [rect.x, rect.y, rect.width, rect.height]
    if not all(_finite(value) for value in values):
        return ValidationResult(False, "ROI values must be finite numbers")
    if rect.width <= 0 or rect.height <= 0:
        return ValidationResult(False, "ROI width and height must be positive")
    if source is not None:
        size_result = validate_size(source)
        if not size_result.valid:
            return size_result
        if rect.x < 0 or rect.y < 0 or rect.x2 > source.width or rect.y2 > source.height:
            return ValidationResult(False, "ROI must be inside source bounds")
    return ValidationResult(True)


def normalize_drag_rect(start: tuple[float, float], end: tuple[float, float], source: SourceSize) -> RoiRect:
    x1, y1 = start
    x2, y2 = end
    left = math.floor(min(float(x1), float(x2)))
    top = math.floor(min(float(y1), float(y2)))
    right = math.ceil(max(float(x1), float(x2)))
    bottom = math.ceil(max(float(y1), float(y2)))
    return clamp_rect(RoiRect(left, top, right - left, bottom - top), source)


def clamp_rect(rect: RoiRect, source: SourceSize, min_size: int = MIN_ROI_SIZE) -> RoiRect:
    validate_size(source)
    width = max(min_size, min(_to_int(rect.width), int(source.width)))
    height = max(min_size, min(_to_int(rect.height), int(source.height)))
    x = max(0, min(_to_int(rect.x), int(source.width) - width))
    y = max(0, min(_to_int(rect.y), int(source.height) - height))
    return RoiRect(x, y, width, height)


def move_rect(rect: RoiRect, dx: float, dy: float, source: SourceSize) -> RoiRect:
    return clamp_rect(RoiRect(_to_int(rect.x + dx), _to_int(rect.y + dy), rect.width, rect.height), source)


def resize_rect(rect: RoiRect, handle: str, dx: float, dy: float, source: SourceSize) -> RoiRect:
    handle = (handle or "").lower()
    left = rect.x
    top = rect.y
    right = rect.x2
    bottom = rect.y2

    if "w" in handle:
        left += dx
    if "e" in handle:
        right += dx
    if "n" in handle:
        top += dy
    if "s" in handle:
        bottom += dy

    if right - left < MIN_ROI_SIZE:
        if "w" in handle:
            left = right - MIN_ROI_SIZE
        else:
            right = left + MIN_ROI_SIZE
    if bottom - top < MIN_ROI_SIZE:
        if "n" in handle:
            top = bottom - MIN_ROI_SIZE
        else:
            bottom = top + MIN_ROI_SIZE

    return clamp_rect(
        RoiRect(_to_int(left), _to_int(top), _to_int(right - left), _to_int(bottom - top)),
        source,
    )


def _display_scale(viewport: dict[str, Any]) -> tuple[float, float]:
    source_width = float(viewport["source_width"])
    source_height = float(viewport["source_height"])
    display_width = float(viewport["display_width"])
    display_height = float(viewport["display_height"])
    return source_width / display_width, source_height / display_height


def display_to_source_point(display_x: float, display_y: float, viewport: dict[str, Any]) -> tuple[int, int]:
    sx, sy = _display_scale(viewport)
    source_width = int(viewport["source_width"])
    source_height = int(viewport["source_height"])
    x = (float(display_x) - float(viewport.get("offset_x", 0))) * sx
    y = (float(display_y) - float(viewport.get("offset_y", 0))) * sy
    return (
        max(0, min(source_width, _to_int(x))),
        max(0, min(source_height, _to_int(y))),
    )


def source_to_display_rect(rect: RoiRect, viewport: dict[str, Any]) -> dict[str, float]:
    sx, sy = _display_scale(viewport)
    offset_x = float(viewport.get("offset_x", 0))
    offset_y = float(viewport.get("offset_y", 0))
    return {
        "x": offset_x + rect.x / sx,
        "y": offset_y + rect.y / sy,
        "width": rect.width / sx,
        "height": rect.height / sy,
    }


def compare_resolution(left: SourceSize | None, right: SourceSize | None) -> bool:
    if left is None or right is None:
        return False
    return int(left.width) == int(right.width) and int(left.height) == int(right.height)


def should_preserve_roi(
    rect: RoiRect | None,
    previous_size: SourceSize | None,
    next_size: SourceSize | None,
) -> RoiRect | None:
    if rect is None:
        return None
    if compare_resolution(previous_size, next_size):
        return rect
    return None


def resolve_frame_range(
    mode: str,
    current_frame: int,
    first_frame: int,
    last_frame: int,
    custom_start: int | None = None,
    custom_end: int | None = None,
) -> tuple[int, int, int, str | None]:
    first = int(first_frame)
    last = int(last_frame)
    current = int(current_frame)
    if first > last:
        return first, last, 0, "Sequence has no frames"

    mode = mode or "current"
    if mode == "current":
        start = end = current
    elif mode == "currentToEnd":
        start, end = current, last
    elif mode == "wholeSequence":
        start, end = first, last
    elif mode == "custom":
        if custom_start is None or custom_end is None:
            return first, last, 0, "Custom frame range requires start and end"
        raw_start = int(custom_start)
        raw_end = int(custom_end)
        if raw_start > raw_end:
            return raw_start, raw_end, 0, "Start frame must be less than or equal to end frame"
        start, end = raw_start, raw_end
    else:
        return first, last, 0, f"Unsupported frame range mode: {mode}"

    start = max(first, min(last, int(start)))
    end = max(first, min(last, int(end)))
    if start > end:
        return start, end, 0, "Frame range is empty"
    return start, end, end - start + 1, None


def sanitize_prefix(value: str | None, fallback: str = "roi") -> str:
    text = str(value or "").strip()
    text = re.sub(r"[\\/]+", "-", text)
    text = re.sub(r"[\x00-\x1f\x7f<>:\"|?*]+", "", text)
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("._-")
    return text or fallback


def make_frame_filename(prefix: str, content: str, frame_number: int, fmt: str, padding: int = 6) -> str:
    fmt = (fmt or "png").lower().lstrip(".")
    return f"{sanitize_prefix(prefix)}_{sanitize_prefix(content)}_{int(frame_number):0{int(padding)}d}.{fmt}"


def make_video_filename(prefix: str, content: str, start_frame: int, end_frame: int) -> str:
    return f"{sanitize_prefix(prefix)}_{sanitize_prefix(content)}_{int(start_frame)}_{int(end_frame)}.mp4"


def clip_box_to_roi(box: dict[str, Any], roi: RoiRect) -> dict[str, Any] | None:
    x1 = float(box.get("x", box.get("x1", 0)))
    y1 = float(box.get("y", box.get("y1", 0)))
    if "w" in box:
        x2 = x1 + float(box.get("w", 0))
    else:
        x2 = float(box.get("x2", x1))
    if "h" in box:
        y2 = y1 + float(box.get("h", 0))
    else:
        y2 = float(box.get("y2", y1))

    ix1 = max(x1, roi.x)
    iy1 = max(y1, roi.y)
    ix2 = min(x2, roi.x2)
    iy2 = min(y2, roi.y2)
    if ix2 <= ix1 or iy2 <= iy1:
        return None

    clipped = dict(box)
    clipped["x"] = ix1 - roi.x
    clipped["y"] = iy1 - roi.y
    clipped["w"] = ix2 - ix1
    clipped["h"] = iy2 - iy1
    clipped["x1"] = clipped["x"]
    clipped["y1"] = clipped["y"]
    clipped["x2"] = clipped["x"] + clipped["w"]
    clipped["y2"] = clipped["y"] + clipped["h"]
    return clipped
