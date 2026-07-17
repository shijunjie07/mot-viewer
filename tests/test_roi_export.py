import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import cv2
import numpy as np

from mot_viewer.datasets.registry import DatasetRegistry
from mot_viewer.services.export_manager import ExportManager
from mot_viewer.services.viewer import ViewerService


class DummyVideoCache:
    pass


def write_gradient(path: Path, base: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = np.zeros((48, 64, 3), dtype=np.uint8)
    for y in range(image.shape[0]):
        for x in range(image.shape[1]):
            image[y, x] = ((base + x) % 255, (base + y) % 255, (base + x + y) % 255)
    assert cv2.imwrite(str(path), image)


def build_fixture(root: Path) -> Path:
    dataset_root = root / "dataset"
    seq_dir = dataset_root / "train" / "seq001"
    for idx in range(1, 5):
        write_gradient(seq_dir / "img1" / f"{idx:06d}.jpg", idx * 30)

    (seq_dir / "gt").mkdir(parents=True, exist_ok=True)
    (seq_dir / "gt" / "gt.txt").write_text(
        "1,7,12,11,18,14,1,1,1,1\n"
        "2,8,5,8,25,20,1,1,1,1\n"
        "3,9,50,40,5,5,1,1,1,1\n",
        encoding="utf-8",
    )
    (seq_dir / "seqinfo.ini").write_text("frameRate=25\nimWidth=64\nimHeight=48\n", encoding="utf-8")
    config_path = root / "datasets.json"
    config_path.write_text(
        json.dumps(
            {
                "datasets": [
                    {
                        "name": "fixture",
                        "root": str(dataset_root),
                        "splits": ["train"],
                        "image_dir": "img1",
                        "gt_files": ["gt.txt"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return config_path


def png_from_zip(path: Path, member: str):
    with zipfile.ZipFile(path) as archive:
        data = np.frombuffer(archive.read(member), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


class RoiExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        config = build_fixture(root)
        registry = DatasetRegistry(config_path=config, default_dataset="fixture")
        self.viewer = ViewerService(registry)
        self.export_dir = root / "exports"
        self.manager = ExportManager(self.viewer, self.export_dir, DummyVideoCache())

    def tearDown(self):
        self.tmp.cleanup()

    def base_payload(self):
        return {
            "dataset": "fixture",
            "split": "train",
            "sequence": "seq001",
            "roi": {"x": 10, "y": 10, "width": 20, "height": 12},
            "frame_range": {"mode": "custom", "start": 1, "end": 3},
            "content": "both",
            "annotated_rendering": "rerender",
            "outputs": "images",
            "image_format": "png",
            "annotation_mode": "visible",
            "include_annotations": True,
            "custom_prefix": "left/court",
        }

    def test_roi_zip_contains_raw_and_annotated_fixed_size(self):
        result = self.manager.export_roi_batch(self.base_payload())
        self.assertTrue(result["available"])
        zip_path = Path(result["zip_path"])
        with zipfile.ZipFile(zip_path) as archive:
            names = archive.namelist()
        self.assertIn("left-court/raw/left-court_raw_000001.png", names)
        self.assertIn("left-court/annotated/left-court_annotated_000001.png", names)
        self.assertEqual(len([name for name in names if name.endswith(".png")]), 6)

        raw = png_from_zip(zip_path, "left-court/raw/left-court_raw_000001.png")
        annotated = png_from_zip(zip_path, "left-court/annotated/left-court_annotated_000001.png")
        self.assertEqual(raw.shape[:2], (12, 20))
        self.assertEqual(annotated.shape[:2], (12, 20))
        self.assertFalse(np.array_equal(raw, annotated))

    def test_roi_video_outputs_use_real_mp4_dimensions(self):
        payload = self.base_payload()
        payload["outputs"] = "video"
        payload["content"] = "raw"
        result = self.manager.export_roi_batch(payload)
        video_path = Path(result["videos"][0]["path"])
        self.assertEqual(video_path.suffix, ".mp4")
        cap = cv2.VideoCapture(str(video_path))
        self.assertTrue(cap.isOpened())
        self.assertEqual(int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), 20)
        self.assertEqual(int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)), 12)
        self.assertEqual(int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), 3)
        cap.release()


if __name__ == "__main__":
    unittest.main()
