# --------------------
# REST API routes for dataset and viewer operations.
# @author: SHI JUNJIE
# 2026-04-25
# --------------------

from io import BytesIO

import cv2
from flask import Blueprint, abort, current_app, jsonify, request, send_file

api_bp = Blueprint("api", __name__)


def _viewer():
    """Return the shared viewer service from the Flask app."""
    return current_app.extensions["viewer_service"]


def _registry():
    """Return the shared dataset registry from the Flask app."""
    return current_app.extensions["dataset_registry"]


@api_bp.get("/datasets")
def api_datasets():
    """Return dataset definitions for the frontend selector."""
    registry = _registry()
    return jsonify(
        {
            "datasets": registry.list_datasets(),
            "default": registry.resolve_name(current_app.config["DEFAULT_DATASET"]),
        }
    )


@api_bp.post("/datasets")
def api_add_dataset():
    """Create a new custom dataset entry from client-provided settings."""
    payload = request.get_json(silent=True) or {}
    try:
        dataset = _registry().add_dataset(payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({"dataset": dataset.to_dict(resolved_splits=_registry().list_splits(dataset.name))}), 201


@api_bp.get("/splits")
def api_splits():
    """Return available splits for a dataset."""
    dataset = request.args.get("dataset")
    return jsonify(_registry().list_splits(dataset))


@api_bp.get("/sequences")
def api_sequences():
    """Return sequences for the requested dataset split."""
    dataset = request.args.get("dataset")
    split = request.args.get("split", "")
    return jsonify(_viewer().list_sequences(dataset, split))


@api_bp.get("/frame_info")
def api_frame_info():
    """Return frame count and frame range for a sequence."""
    dataset = request.args.get("dataset")
    split = request.args.get("split", "")
    seq = request.args.get("seq", "")
    return jsonify(_viewer().frame_info(dataset, split, seq))


@api_bp.get("/annotation_files")
def api_annotation_files():
    """Return available GT and DET files for a sequence."""
    dataset = request.args.get("dataset")
    split = request.args.get("split", "")
    seq = request.args.get("seq", "")
    return jsonify(_viewer().list_annotation_files(dataset, split, seq))


@api_bp.get("/vis_not1_frames")
def api_vis_not1_frames():
    """Return frames whose visibility differs from 1."""
    dataset = request.args.get("dataset")
    split = request.args.get("split", "")
    seq = request.args.get("seq", "")
    annotation_type = request.args.get("annotation_type", "gt")
    annotation_file = request.args.get("annotation_file", "").strip() or None
    return jsonify(
        _viewer().vis_not1_frames(
            dataset, split, seq, annotation_type=annotation_type, annotation_file=annotation_file
        )
    )


@api_bp.get("/seq_meta")
def api_seq_meta():
    """Return selected metadata fields for a sequence."""
    dataset = request.args.get("dataset")
    split = request.args.get("split", "")
    seq = request.args.get("seq", "")
    return jsonify(_viewer().sequence_meta(dataset, split, seq))


@api_bp.get("/render_raw")
def api_render_raw():
    """Render a raw frame image for the requested sequence position."""
    dataset = request.args.get("dataset")
    split = request.args.get("split", "")
    seq = request.args.get("seq", "")
    if not seq:
        abort(400, "Missing seq")

    frame_idx = int(request.args.get("frame_idx", "0"))
    frame_mode = request.args.get("frame_mode", "idx")
    frame_value = request.args.get("frame_value", "").strip()

    try:
        image = _viewer().render_raw(dataset, split, seq, frame_idx, frame_mode, frame_value)
    except FileNotFoundError as exc:
        abort(404, str(exc))
    if image is None:
        abort(404, "failed to read image")

    ok, buf = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        abort(500, "encode failed")
    return send_file(BytesIO(buf.tobytes()), mimetype="image/jpeg")


@api_bp.get("/frame_boxes")
def api_frame_boxes():
    """Return detection boxes for one selected frame."""
    dataset = request.args.get("dataset")
    split = request.args.get("split", "")
    seq = request.args.get("seq", "")
    if not seq:
        abort(400, "Missing seq")

    frame_idx = int(request.args.get("frame_idx", "0"))
    frame_mode = request.args.get("frame_mode", "idx")
    frame_value = request.args.get("frame_value", "").strip()
    annotation_type = request.args.get("annotation_type", "gt")
    annotation_file = request.args.get("annotation_file", "").strip() or None
    try:
        payload = _viewer().frame_boxes(
            dataset,
            split,
            seq,
            frame_idx,
            frame_mode,
            frame_value,
            annotation_type=annotation_type,
            annotation_file=annotation_file,
        )
    except FileNotFoundError as exc:
        abort(404, str(exc))
    return jsonify(payload)
