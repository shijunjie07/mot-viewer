# --------------------
# Application configuration values and environment overrides.
# @author: SHI JUNJIE
# 2026-04-25
# --------------------

import os
from pathlib import Path


class AppConfig:
    """Application-level configuration values for the Flask app."""
    BASE_DIR = Path(__file__).resolve().parent.parent
    INSTANCE_DIR = BASE_DIR / "instance"

    DEFAULT_DATASET = os.environ.get("MOT_VIEWER_DEFAULT_DATASET", "soccernet")
    DATASETS_CONFIG_PATH = os.environ.get(
        "MOT_VIEWER_DATASETS_CONFIG",
        str(INSTANCE_DIR / "datasets.json"),
    )
