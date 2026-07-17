import math
import unittest

from mot_viewer.services.roi import (
    RoiRect,
    SourceSize,
    clamp_rect,
    clip_box_to_roi,
    compare_resolution,
    display_to_source_point,
    make_frame_filename,
    make_video_filename,
    move_rect,
    normalize_drag_rect,
    resize_rect,
    resolve_frame_range,
    sanitize_prefix,
    should_preserve_roi,
    source_to_display_rect,
    validate_rect,
)


class RoiGeometryTests(unittest.TestCase):
    def setUp(self):
        self.source = SourceSize(width=640, height=480)
        self.display = {
            "source_width": 640,
            "source_height": 480,
            "display_width": 320,
            "display_height": 240,
            "offset_x": 10,
            "offset_y": 20,
        }

    def test_drag_top_left_to_bottom_right(self):
        rect = normalize_drag_rect((10, 20), (110, 70), self.source)
        self.assertEqual(rect, RoiRect(10, 20, 100, 50))

    def test_drag_bottom_right_to_top_left(self):
        rect = normalize_drag_rect((110, 70), (10, 20), self.source)
        self.assertEqual(rect, RoiRect(10, 20, 100, 50))

    def test_display_to_source_with_scale_and_offsets(self):
        point = display_to_source_point(170, 140, self.display)
        self.assertEqual(point, (320, 240))

    def test_display_to_source_letterboxed_clamps(self):
        point = display_to_source_point(0, 0, self.display)
        self.assertEqual(point, (0, 0))
        point = display_to_source_point(500, 500, self.display)
        self.assertEqual(point, (640, 480))

    def test_source_to_display_rect(self):
        rect = source_to_display_rect(RoiRect(320, 240, 64, 48), self.display)
        self.assertEqual(rect, {"x": 170.0, "y": 140.0, "width": 32.0, "height": 24.0})

    def test_clamping_boundaries(self):
        rect = clamp_rect(RoiRect(-5, -6, 700, 600), self.source)
        self.assertEqual(rect, RoiRect(0, 0, 640, 480))
        rect = clamp_rect(RoiRect(630, 470, 40, 30), self.source)
        self.assertEqual(rect, RoiRect(600, 450, 40, 30))

    def test_move_against_boundaries(self):
        rect = RoiRect(100, 100, 50, 60)
        self.assertEqual(move_rect(rect, -999, 0, self.source), RoiRect(0, 100, 50, 60))
        self.assertEqual(move_rect(rect, 999, 0, self.source), RoiRect(590, 100, 50, 60))
        self.assertEqual(move_rect(rect, 0, -999, self.source), RoiRect(100, 0, 50, 60))
        self.assertEqual(move_rect(rect, 0, 999, self.source), RoiRect(100, 420, 50, 60))

    def test_resize_each_handle_and_minimum_size(self):
        rect = RoiRect(100, 100, 80, 60)
        self.assertEqual(resize_rect(rect, "nw", -30, -20, self.source), RoiRect(70, 80, 110, 80))
        self.assertEqual(resize_rect(rect, "ne", 30, -20, self.source), RoiRect(100, 80, 110, 80))
        self.assertEqual(resize_rect(rect, "sw", -30, 20, self.source), RoiRect(70, 100, 110, 80))
        self.assertEqual(resize_rect(rect, "se", 30, 20, self.source), RoiRect(100, 100, 110, 80))
        self.assertEqual(resize_rect(rect, "se", -999, -999, self.source), RoiRect(100, 100, 2, 2))

    def test_invalid_values_are_rejected(self):
        for bad in [
            RoiRect(0, 0, 0, 10),
            RoiRect(0, 0, 10, -1),
            RoiRect(math.nan, 0, 10, 10),
            RoiRect(0, math.inf, 10, 10),
        ]:
            self.assertFalse(validate_rect(bad, self.source).valid)

    def test_sequence_resolution_rules(self):
        self.assertTrue(compare_resolution(SourceSize(640, 480), SourceSize(640, 480)))
        self.assertFalse(compare_resolution(SourceSize(640, 480), SourceSize(1280, 720)))
        self.assertEqual(
            should_preserve_roi(RoiRect(0, 0, 10, 10), SourceSize(640, 480), SourceSize(640, 480)),
            RoiRect(0, 0, 10, 10),
        )
        self.assertIsNone(
            should_preserve_roi(RoiRect(0, 0, 10, 10), SourceSize(640, 480), SourceSize(1280, 720))
        )


class RoiRangeNamingTests(unittest.TestCase):
    def test_frame_range_modes_are_inclusive(self):
        self.assertEqual(resolve_frame_range("current", 300, 1, 450), (300, 300, 1, None))
        self.assertEqual(resolve_frame_range("currentToEnd", 300, 1, 450), (300, 450, 151, None))
        self.assertEqual(resolve_frame_range("wholeSequence", 300, 1, 450), (1, 450, 450, None))
        self.assertEqual(resolve_frame_range("custom", 1, 1, 500, 300, 450), (300, 450, 151, None))

    def test_frame_range_clamps_and_rejects_invalid(self):
        self.assertEqual(resolve_frame_range("custom", 1, 10, 20, -5, 50), (10, 20, 11, None))
        result = resolve_frame_range("custom", 1, 1, 20, 18, 9)
        self.assertIsNotNone(result[3])
        result = resolve_frame_range("wholeSequence", 1, 0, -1)
        self.assertIsNotNone(result[3])

    def test_filename_prefix_sanitization_and_fallback(self):
        self.assertEqual(sanitize_prefix(" left/court:*? "), "left-court")
        self.assertEqual(sanitize_prefix("\x00\t"), "roi")
        self.assertEqual(make_frame_filename("left-court", "raw", 300, "png", 6), "left-court_raw_000300.png")
        self.assertEqual(
            make_frame_filename("left-court", "annotated", 300, "jpg", 4),
            "left-court_annotated_0300.jpg",
        )
        self.assertEqual(make_video_filename("left-court", "raw", 300, 450), "left-court_raw_300_450.mp4")


class RoiAnnotationClipTests(unittest.TestCase):
    def test_clip_box_full_partial_and_omitted(self):
        roi = RoiRect(10, 20, 100, 80)
        full = clip_box_to_roi({"x": 20, "y": 30, "w": 10, "h": 12, "id": 1}, roi)
        self.assertEqual(full["x"], 10)
        self.assertEqual(full["y"], 10)
        self.assertEqual(full["w"], 10)
        self.assertEqual(full["h"], 12)

        partial = clip_box_to_roi({"x": 5, "y": 10, "w": 20, "h": 20, "id": 2}, roi)
        self.assertEqual(partial["x"], 0)
        self.assertEqual(partial["y"], 0)
        self.assertEqual(partial["w"], 15)
        self.assertEqual(partial["h"], 10)

        self.assertIsNone(clip_box_to_roi({"x": 200, "y": 200, "w": 10, "h": 10}, roi))


if __name__ == "__main__":
    unittest.main()
