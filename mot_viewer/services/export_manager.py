from __future__ import annotations

import base64
import copy
import html
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Callable

import cv2

from .roi import (
    RoiRect,
    SourceSize,
    clamp_rect,
    clip_box_to_roi,
    make_frame_filename,
    make_video_filename,
    resolve_frame_range,
    sanitize_prefix,
    validate_rect,
)

IMAGE_FORMATS = {"jpg", "jpeg", "png", "svg"}
VIDEO_FORMATS = {"mp4"}
EXPORT_FORMATS = {
    "frame": IMAGE_FORMATS,
    "images": IMAGE_FORMATS,
    "video": VIDEO_FORMATS,
}


def validate_export_request(target: str, fmt: str) -> str:
    """Validate an export target/format combination."""
    target = (target or "").strip().lower()
    fmt = (fmt or "").strip().lower().lstrip(".")
    if target not in EXPORT_FORMATS:
        raise ValueError(f"Unsupported export target: {target}")
    if fmt not in EXPORT_FORMATS[target]:
        allowed = ", ".join(sorted(EXPORT_FORMATS[target]))
        raise ValueError(f"Invalid format '{fmt}' for {target}. Allowed: {allowed}")
    return fmt


def safe_name(value: str) -> str:
    """Return a filesystem-safe filename segment."""
    out = []
    for char in str(value):
        out.append(char if char.isalnum() or char in {"-", "_"} else "_")
    text = "".join(out).strip("_")
    return text or "item"


def selected_layer_names(payload: dict, request_payload: dict) -> list[str]:
    """Resolve export layer selection from request settings."""
    if not request_payload.get("include_annotations", True):
        return []
    mode = request_payload.get("annotation_mode", "visible")
    layers = payload.get("layers", [])
    if mode == "none":
        return []
    if mode == "custom":
        selected = {str(name) for name in request_payload.get("selected_layers", [])}
        known = {layer["name"] for layer in layers}
        missing = selected - known
        if missing:
            raise ValueError(f"Invalid layer name(s): {', '.join(sorted(missing))}")
        return [layer["name"] for layer in layers if layer["name"] in selected]
    return [layer["name"] for layer in layers if layer.get("visible", True)]


def apply_layer_overrides(annotation_payload: dict, request_payload: dict) -> dict:
    """Apply client-side layer display settings before export rendering."""
    overrides = request_payload.get("layer_overrides") or {}
    if not isinstance(overrides, dict):
        return annotation_payload
    known = {layer.get("name"): layer for layer in annotation_payload.get("layers", [])}
    for name, patch in overrides.items():
        layer = known.get(name)
        if not layer or not isinstance(patch, dict):
            continue
        color = str(patch.get("color") or "").strip()
        if re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            layer["color"] = color
        for key in ("visible", "draw_id", "draw_score"):
            if key in patch:
                layer[key] = bool(patch[key])
        if "score_threshold" in patch:
            try:
                layer["score_threshold"] = max(0.0, min(1.0, float(patch["score_threshold"])))
            except (TypeError, ValueError):
                pass
    return annotation_payload


def boxes_for_frame(payload: dict, frame_number: int, selected_layers: list[str]) -> list[dict]:
    """Flatten selected layer boxes for one MOT frame."""
    layer_settings = {layer["name"]: layer for layer in payload.get("layers", [])}
    frame_layers = payload.get("frames", {}).get(str(frame_number), {})
    boxes: list[dict] = []
    for layer_name in selected_layers:
        settings = layer_settings.get(layer_name)
        if not settings:
            continue
        threshold = float(settings.get("score_threshold", 0.0) or 0.0)
        for box in frame_layers.get(layer_name, []):
            if float(box.get("score", 1.0)) < threshold:
                continue
            item = dict(box)
            item["layer"] = layer_name
            item["color"] = settings.get("color", "#35e6fd")
            item["draw_id"] = bool(settings.get("draw_id", True))
            item["draw_score"] = bool(settings.get("draw_score", False))
            boxes.append(item)
    return boxes


def draw_boxes(image, boxes: list[dict]):
    """Draw annotation boxes onto an OpenCV BGR image."""
    for box in boxes:
        color = hex_to_bgr(box.get("color", "#35e6fd"))
        x = int(round(float(box.get("x", box.get("x1", 0)))))
        y = int(round(float(box.get("y", box.get("y1", 0)))))
        w = int(round(float(box.get("w", box.get("x2", 0) - box.get("x1", 0)))))
        h = int(round(float(box.get("h", box.get("y2", 0) - box.get("y1", 0)))))
        cv2.rectangle(image, (x, y), (x + w, y + h), color, 2)
        labels = []
        if box.get("draw_id", True):
            labels.append(f"id:{box.get('id')}")
        if box.get("draw_score", False):
            labels.append(f"{float(box.get('score', 1.0)):.2f}")
        if labels:
            cv2.putText(
                image,
                " ".join(labels),
                (x, max(14, y - 5)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                1,
                cv2.LINE_AA,
            )
    return image


def hex_to_bgr(value: str) -> tuple[int, int, int]:
    text = (value or "#35e6fd").strip().lstrip("#")
    if len(text) != 6:
        text = "35e6fd"
    r = int(text[0:2], 16)
    g = int(text[2:4], 16)
    b = int(text[4:6], 16)
    return b, g, r


def encode_raster(image, fmt: str) -> bytes:
    ext = ".jpg" if fmt == "jpeg" else f".{fmt}"
    params = [int(cv2.IMWRITE_JPEG_QUALITY), 92] if fmt in {"jpg", "jpeg"} else []
    ok, buf = cv2.imencode(ext, image, params)
    if not ok:
        raise RuntimeError(f"Failed to encode {fmt}")
    return buf.tobytes()


def render_svg(frame_path: Path, boxes: list[dict]) -> bytes:
    image = cv2.imread(str(frame_path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(f"Failed to read image: {frame_path}")
    height, width = image.shape[:2]
    mime = "image/png" if frame_path.suffix.lower() == ".png" else "image/jpeg"
    embedded = base64.b64encode(frame_path.read_bytes()).decode("ascii")
    items = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<image href="data:{mime};base64,{embedded}" x="0" y="0" width="{width}" height="{height}"/>',
    ]
    for box in boxes:
        color = html.escape(box.get("color", "#35e6fd"))
        x = float(box.get("x", box.get("x1", 0)))
        y = float(box.get("y", box.get("y1", 0)))
        w = float(box.get("w", box.get("x2", 0) - box.get("x1", 0)))
        h = float(box.get("h", box.get("y2", 0) - box.get("y1", 0)))
        items.append(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
            f'stroke="{color}" fill="none" stroke-width="2"/>'
        )
        labels = []
        if box.get("draw_id", True):
            labels.append(f"ID {box.get('id')}")
        if box.get("draw_score", False):
            labels.append(f"{float(box.get('score', 1.0)):.2f}")
        if labels:
            label = html.escape(" ".join(labels))
            items.append(
                f'<text x="{x:.2f}" y="{max(14.0, y - 5):.2f}" '
                f'fill="{color}" stroke="black" stroke-width="0.5" font-size="14">{label}</text>'
            )
    items.append("</svg>")
    return "\n".join(items).encode("utf-8")


def render_svg_from_image(image, boxes: list[dict]) -> bytes:
    """Create an SVG that embeds an already-rendered BGR image."""
    ok, buf = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError("Failed to encode SVG image payload")
    height, width = image.shape[:2]
    embedded = base64.b64encode(buf.tobytes()).decode("ascii")
    items = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<image href="data:image/png;base64,{embedded}" x="0" y="0" width="{width}" height="{height}"/>',
    ]
    for box in boxes:
        color = html.escape(box.get("color", "#35e6fd"))
        x = float(box.get("x", box.get("x1", 0)))
        y = float(box.get("y", box.get("y1", 0)))
        w = float(box.get("w", box.get("x2", 0) - box.get("x1", 0)))
        h = float(box.get("h", box.get("y2", 0) - box.get("y1", 0)))
        items.append(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
            f'stroke="{color}" fill="none" stroke-width="2"/>'
        )
    items.append("</svg>")
    return "\n".join(items).encode("utf-8")


class ExportManager:
    """Create frame, image ZIP, and MP4 exports."""

    def __init__(self, viewer, export_dir: Path, video_cache):
        self.viewer = viewer
        self.export_dir = export_dir
        self.video_cache = video_cache

    def _ensure_dir(self) -> None:
        self.export_dir.mkdir(parents=True, exist_ok=True)
        if not self.export_dir.is_dir():
            raise RuntimeError(f"Export directory is not writable: {self.export_dir}")

    def _context(self, payload: dict) -> tuple[dict, list[str]]:
        annotation_payload = self.viewer.annotation_payload(
            payload.get("dataset"),
            payload.get("split", ""),
            payload.get("sequence", ""),
        )
        annotation_payload = copy.deepcopy(annotation_payload)
        annotation_payload = apply_layer_overrides(annotation_payload, payload)
        return annotation_payload, selected_layer_names(annotation_payload, payload)

    def export_frame(self, payload: dict, progress: Callable[[int, str], None] | None = None) -> Path:
        if progress:
            progress(10, "Rendering frame")
        fmt = validate_export_request("frame", payload.get("format", "png"))
        annotation_payload, selected_layers = self._context(payload)
        frame_number = int(payload.get("frame", annotation_payload.get("first_frame", 1)))
        frame_path = self.viewer.frame_path_for_mot_frame(
            payload.get("dataset"), payload.get("split", ""), payload.get("sequence", ""), frame_number
        )
        boxes = boxes_for_frame(annotation_payload, frame_number, selected_layers)
        self._ensure_dir()
        layer_key = "raw" if not selected_layers else safe_name("_".join(selected_layers))
        filename = (
            f"{safe_name(payload.get('dataset'))}_{safe_name(payload.get('split'))}_"
            f"{safe_name(payload.get('sequence'))}_frame_{frame_number:06d}_{layer_key}.{fmt}"
        )
        out_path = self._unique_path(filename)
        if fmt == "svg":
            out_path.write_bytes(render_svg(frame_path, boxes))
            if progress:
                progress(100, "Frame export ready")
            return out_path
        image = cv2.imread(str(frame_path), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(f"Failed to read image: {frame_path}")
        if selected_layers:
            draw_boxes(image, boxes)
        out_path.write_bytes(encode_raster(image, fmt))
        if progress:
            progress(100, "Frame export ready")
        return out_path

    def export_images_zip(self, payload: dict, progress: Callable[[int, str], None] | None = None) -> Path:
        fmt = validate_export_request("images", payload.get("format", "png"))
        annotation_payload, selected_layers = self._context(payload)
        files = self.viewer.sequence_frame_files(
            payload.get("dataset"), payload.get("split", ""), payload.get("sequence", "")
        )
        self._ensure_dir()
        layer_key = "raw" if not selected_layers else safe_name("_".join(selected_layers))
        filename = (
            f"{safe_name(payload.get('dataset'))}_{safe_name(payload.get('split'))}_"
            f"{safe_name(payload.get('sequence'))}_images_{layer_key}_{fmt}.zip"
        )
        out_path = self._unique_path(filename)
        total = len(files)
        with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for idx, frame_path in enumerate(files, start=1):
                frame_number = self.viewer.parse_frame_num_from_name(frame_path.name) or 1
                boxes = boxes_for_frame(annotation_payload, frame_number, selected_layers)
                arcname = f"{frame_path.stem}.{fmt}"
                if fmt == "svg":
                    archive.writestr(arcname, render_svg(frame_path, boxes))
                elif selected_layers:
                    image = cv2.imread(str(frame_path), cv2.IMREAD_COLOR)
                    if image is None:
                        raise FileNotFoundError(f"Failed to read image: {frame_path}")
                    archive.writestr(arcname, encode_raster(draw_boxes(image, boxes), fmt))
                else:
                    if fmt in {"jpg", "jpeg"} and frame_path.suffix.lower() in {".jpg", ".jpeg"}:
                        archive.write(frame_path, arcname)
                    elif fmt == "png" and frame_path.suffix.lower() == ".png":
                        archive.write(frame_path, arcname)
                    else:
                        image = cv2.imread(str(frame_path), cv2.IMREAD_COLOR)
                        if image is None:
                            raise FileNotFoundError(f"Failed to read image: {frame_path}")
                        archive.writestr(arcname, encode_raster(image, fmt))
                if progress and (idx == 1 or idx == total or idx % 25 == 0):
                    progress(int((idx / total) * 100), f"Rendering frame {idx} / {total}")
        return out_path

    def export_video(self, payload: dict, progress: Callable[[int, str], None] | None = None) -> Path:
        validate_export_request("video", payload.get("format", "mp4"))
        annotation_payload, selected_layers = self._context(payload)
        self._ensure_dir()
        layer_key = "raw" if not selected_layers else safe_name("_".join(selected_layers))
        filename = (
            f"{safe_name(payload.get('dataset'))}_{safe_name(payload.get('split'))}_"
            f"{safe_name(payload.get('sequence'))}_video_{layer_key}.mp4"
        )
        out_path = self._unique_path(filename)
        fps = float(payload.get("fps") or annotation_payload.get("fps") or 25)
        if not selected_layers:
            cache = self.video_cache.ensure_video(
                payload.get("dataset"),
                payload.get("split", ""),
                payload.get("sequence", ""),
                progress=progress,
            )
            if cache.get("available") and cache.get("path"):
                shutil.copyfile(cache["path"], out_path)
                if progress:
                    progress(100, "Video export ready")
                return out_path
        files = self.viewer.sequence_frame_files(
            payload.get("dataset"), payload.get("split", ""), payload.get("sequence", "")
        )
        self._encode_rendered_video(files, annotation_payload, selected_layers, fps, out_path, progress)
        return out_path

    def export_roi_batch(
        self,
        payload: dict,
        progress: Callable[[int, str], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> dict:
        """Export a fixed source-coordinate ROI as images, video, or both."""
        annotation_payload, selected_layers = self._context(payload)
        files = self.viewer.sequence_frame_files(
            payload.get("dataset"), payload.get("split", ""), payload.get("sequence", "")
        )
        roi = self._resolve_roi(payload, files[0])
        frame_records = self._resolve_roi_frame_records(payload, annotation_payload, files)
        if not frame_records:
            raise ValueError("ROI frame range produced no frames")

        content_modes = self._roi_content_modes(payload)
        outputs = self._roi_outputs(payload)
        image_format = validate_export_request("images", payload.get("image_format") or payload.get("format") or "png")
        prefix = sanitize_prefix(payload.get("custom_prefix") or payload.get("sequence") or "roi")
        annotated_mode = payload.get("annotated_rendering") or payload.get("annotation_rendering") or "rerender"
        fps = float(payload.get("fps") or annotation_payload.get("fps") or 25)

        self._ensure_dir()
        result: dict = {
            "available": True,
            "roi": roi.__dict__,
            "frame_range": {
                "start": frame_records[0][0],
                "end": frame_records[-1][0],
                "total": len(frame_records),
            },
            "outputs": [],
            "images": [],
            "videos": [],
            "directory_files": [],
        }

        if "images" in outputs:
            zip_path, directory_files = self._export_roi_images(
                frame_records,
                annotation_payload,
                selected_layers,
                roi,
                prefix,
                content_modes,
                annotated_mode,
                image_format,
                progress,
                is_cancelled,
            )
            result["zip_path"] = str(zip_path)
            result["download_url"] = self._download_path(zip_path)
            result["images"].append({"path": str(zip_path), "download_url": self._download_path(zip_path), "format": "zip"})
            result["directory_files"] = directory_files
            result["outputs"].append("images")

        if "video" in outputs:
            videos = []
            for content in content_modes:
                if content not in {"raw", "annotated"}:
                    continue
                video_path = self._export_roi_video(
                    frame_records,
                    annotation_payload,
                    selected_layers,
                    roi,
                    prefix,
                    content,
                    annotated_mode,
                    fps,
                    progress,
                    is_cancelled,
                )
                videos.append(
                    {
                        "path": str(video_path),
                        "download_url": self._download_path(video_path),
                        "content": content,
                        "format": "mp4",
                    }
                )
            result["videos"] = videos
            if "download_url" not in result and videos:
                result["download_url"] = videos[0]["download_url"]
            result["outputs"].append("video")

        if progress:
            progress(100, "ROI export ready")
        return result

    def _resolve_roi(self, payload: dict, sample_frame: Path) -> RoiRect:
        roi_payload = payload.get("roi") or {}
        image = cv2.imread(str(sample_frame), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(f"Failed to read image: {sample_frame}")
        height, width = image.shape[:2]
        roi = RoiRect(
            int(round(float(roi_payload.get("x", 0)))),
            int(round(float(roi_payload.get("y", 0)))),
            int(round(float(roi_payload.get("width", 0)))),
            int(round(float(roi_payload.get("height", 0)))),
        )
        valid = validate_rect(roi)
        if not valid.valid:
            raise ValueError(valid.error or "Invalid ROI")
        return clamp_rect(roi, SourceSize(width, height))

    def _resolve_roi_frame_records(self, payload: dict, annotation_payload: dict, files: list[Path]) -> list[tuple[int, Path]]:
        first = int(annotation_payload.get("first_frame") or 1)
        last = first + len(files) - 1
        frame_range = payload.get("frame_range") or {}
        mode = frame_range.get("mode") or payload.get("range_mode") or "current"
        current = int(payload.get("frame") or frame_range.get("current") or first)
        start, end, _, error = resolve_frame_range(
            mode,
            current,
            first,
            last,
            frame_range.get("start") or payload.get("custom_start"),
            frame_range.get("end") or payload.get("custom_end"),
        )
        if error:
            raise ValueError(error)
        records = []
        for idx, frame_path in enumerate(files):
            frame_number = self.viewer.parse_frame_num_from_name(frame_path.name) or (first + idx)
            if start <= frame_number <= end:
                records.append((frame_number, frame_path))
        return records

    def _roi_content_modes(self, payload: dict) -> list[str]:
        content = (payload.get("content") or "raw").strip().lower()
        if content in {"both", "raw+annotated", "raw_annotated"}:
            return ["raw", "annotated"]
        if content in {"raw", "annotated"}:
            return [content]
        raise ValueError(f"Unsupported ROI content: {content}")

    def _roi_outputs(self, payload: dict) -> set[str]:
        outputs = (payload.get("outputs") or payload.get("output") or "images").strip().lower()
        if outputs in {"both", "images+video", "image_sequence+video"}:
            return {"images", "video"}
        if outputs in {"images", "image_sequence", "zip"}:
            return {"images"}
        if outputs == "video":
            return {"video"}
        raise ValueError(f"Unsupported ROI output: {outputs}")

    def _export_roi_images(
        self,
        frame_records: list[tuple[int, Path]],
        annotation_payload: dict,
        selected_layers: list[str],
        roi: RoiRect,
        prefix: str,
        content_modes: list[str],
        annotated_mode: str,
        image_format: str,
        progress: Callable[[int, str], None] | None,
        is_cancelled: Callable[[], bool] | None,
    ) -> tuple[Path, list[dict]]:
        export_name = prefix
        zip_path = self._unique_path(f"{export_name}_roi_images_{image_format}.zip")
        directory = self._unique_dir(f"{export_name}_roi_images")
        directory_files: list[dict] = []
        total = len(frame_records) * len(content_modes)
        done = 0
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for frame_number, frame_path in frame_records:
                for content in content_modes:
                    self._raise_if_cancelled(is_cancelled)
                    rendered, local_boxes = self._render_roi_image(
                        frame_path,
                        annotation_payload,
                        selected_layers,
                        frame_number,
                        roi,
                        content,
                        annotated_mode,
                    )
                    filename = make_frame_filename(prefix, content, frame_number, image_format)
                    arcname = f"{export_name}/{content}/{filename}"
                    if image_format == "svg":
                        data = render_svg_from_image(rendered, local_boxes if content == "annotated" else [])
                    else:
                        data = encode_raster(rendered, image_format)
                    archive.writestr(arcname, data)
                    out_file = directory / content / filename
                    out_file.parent.mkdir(parents=True, exist_ok=True)
                    out_file.write_bytes(data)
                    directory_files.append(
                        {
                            "path": str(out_file),
                            "relative_path": f"{content}/{filename}",
                            "download_url": self._download_path(out_file),
                            "content": content,
                        }
                    )
                    done += 1
                    if progress:
                        progress(max(1, min(90, int(done / total * 90))), f"Rendering ROI frame {done} / {total}")
        return zip_path, directory_files

    def _export_roi_video(
        self,
        frame_records: list[tuple[int, Path]],
        annotation_payload: dict,
        selected_layers: list[str],
        roi: RoiRect,
        prefix: str,
        content: str,
        annotated_mode: str,
        fps: float,
        progress: Callable[[int, str], None] | None,
        is_cancelled: Callable[[], bool] | None,
    ) -> Path:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("ffmpeg not found")
        out_path = self._unique_path(make_video_filename(prefix, content, frame_records[0][0], frame_records[-1][0]))
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            total = len(frame_records)
            for idx, (frame_number, frame_path) in enumerate(frame_records, start=1):
                self._raise_if_cancelled(is_cancelled)
                rendered, _ = self._render_roi_image(
                    frame_path,
                    annotation_payload,
                    selected_layers,
                    frame_number,
                    roi,
                    content,
                    annotated_mode,
                )
                cv2.imwrite(str(tmp_dir / f"{idx:06d}.png"), rendered)
                if progress:
                    progress(max(1, min(85, int(idx / total * 85))), f"Rendering ROI video frame {idx} / {total}")
            if progress:
                progress(92, f"Encoding {content} MP4")
            command = [
                ffmpeg,
                "-y",
                "-framerate",
                str(fps),
                "-i",
                str(tmp_dir / "%06d.png"),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv444p",
                "-movflags",
                "+faststart",
                str(out_path),
            ]
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                raise RuntimeError(f"ffmpeg ROI video export failed: {result.stderr.strip()}")
        return out_path

    def _render_roi_image(
        self,
        frame_path: Path,
        annotation_payload: dict,
        selected_layers: list[str],
        frame_number: int,
        roi: RoiRect,
        content: str,
        annotated_mode: str,
    ) -> tuple:
        image = cv2.imread(str(frame_path), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(f"Failed to read image: {frame_path}")
        height, width = image.shape[:2]
        safe_roi = clamp_rect(roi, SourceSize(width, height))
        boxes = boxes_for_frame(annotation_payload, frame_number, selected_layers)

        if content == "raw" or not boxes:
            return image[safe_roi.y : safe_roi.y2, safe_roi.x : safe_roi.x2].copy(), []

        mode = (annotated_mode or "rerender").strip().lower()
        if mode in {"rendered", "current", "crop-rendered", "crop_current_rendered", "crop-current-rendered"}:
            full = image.copy()
            draw_boxes(full, boxes)
            return full[safe_roi.y : safe_roi.y2, safe_roi.x : safe_roi.x2].copy(), []

        crop = image[safe_roi.y : safe_roi.y2, safe_roi.x : safe_roi.x2].copy()
        local_boxes = []
        for box in boxes:
            clipped = clip_box_to_roi(box, safe_roi)
            if clipped:
                local_boxes.append(clipped)
        if local_boxes:
            draw_boxes(crop, local_boxes)
        return crop, local_boxes

    def _raise_if_cancelled(self, is_cancelled: Callable[[], bool] | None) -> None:
        if is_cancelled and is_cancelled():
            raise RuntimeError("Export cancelled")

    def _download_path(self, path: Path) -> str:
        try:
            relative = path.resolve().relative_to(self.export_dir.resolve())
            return f"/downloads/exports/{relative.as_posix()}"
        except ValueError:
            return f"/downloads/exports/{path.name}"

    def _unique_dir(self, dirname: str) -> Path:
        base = self.export_dir / safe_name(dirname)
        candidate = base
        counter = 1
        while candidate.exists():
            candidate = self.export_dir / f"{base.name}_{counter}"
            counter += 1
        candidate.mkdir(parents=True, exist_ok=False)
        return candidate

    def _encode_rendered_video(
        self,
        files: list[Path],
        annotation_payload: dict,
        selected_layers: list[str],
        fps: float,
        out_path: Path,
        progress: Callable[[int, str], None] | None = None,
    ) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("ffmpeg not found")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            total = len(files)
            for idx, frame_path in enumerate(files, start=1):
                image = cv2.imread(str(frame_path), cv2.IMREAD_COLOR)
                if image is None:
                    raise FileNotFoundError(f"Failed to read image: {frame_path}")
                frame_number = self.viewer.parse_frame_num_from_name(frame_path.name) or idx
                boxes = boxes_for_frame(annotation_payload, frame_number, selected_layers)
                if selected_layers:
                    draw_boxes(image, boxes)
                cv2.imwrite(str(tmp_dir / f"{idx:06d}.jpg"), image)
                if progress and (idx == 1 or idx == total or idx % 25 == 0):
                    percent = max(1, min(85, int((idx / total) * 85)))
                    progress(percent, f"Rendering frame {idx} / {total}")
            if progress:
                progress(90, "Encoding MP4")
            command = [
                ffmpeg,
                "-y",
                "-framerate",
                str(fps),
                "-i",
                str(tmp_dir / "%06d.jpg"),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(out_path),
            ]
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                raise RuntimeError(f"ffmpeg video export failed: {result.stderr.strip()}")
            if progress:
                progress(100, "Video export ready")

    def _unique_path(self, filename: str) -> Path:
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        candidate = self.export_dir / filename
        if not candidate.exists():
            return candidate
        return self.export_dir / f"{stem}_{int(time.time())}{suffix}"
