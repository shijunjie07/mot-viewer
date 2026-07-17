# MOTScope ROI Batch Export v1 Execution Report

## Branch

- Branch: `feature/roi-batch-export`
- Base branch: local `master`
- Base commit: `a97027784df61b74c114a37d4adaa87d1d87d12c`
- Final implementation commit before report: `1fa4be06afa09271b9de7e59654914f4322151ce`
- Final branch tip: this execution-report commit
- Repository path: `/home/junja/mot_viewer`
- Conda environment: `occrl`
- Master status: not changed, not merged.

## Commit List

```text
1fa4be0 fix: preserve ROI export completion status
b0ea255 docs: add ROI browser verification artifacts
7189818 docs: document ROI batch export
66ca0fa test: add ROI job cancellation coverage
fb395b0 feat: refine ROI export UI state
a0a39c1 feat: add ROI selection and export UI
152eb57 feat: add ROI export job cancellation
9da6c6c feat: add ROI batch export backend
147836c test: add ROI export coverage
708cafa feat: add source-coordinate ROI geometry
775b682 test: add ROI geometry coverage
```

## Resolved Repository Manifest

- Application entry point: `app.py`
- Flask app factory: `mot_viewer/__init__.py`
- Top toolbar: `templates/index.html`, `.app-toolbar`
- Frame viewer/canvas: `templates/index.html` (`#frameCanvas`, `#videoStage`, `#sequenceVideo`, `#videoOverlayCanvas`), `static/app.js`, `static/style.css`
- Image loading and frame navigation: `mot_viewer/services/viewer.py`, `/api/render_raw`, `/api/frame_boxes`, `loadFrameImageAndBoxes`, `stepFrame`
- Sequence metadata/native resolution: `mot_viewer/services/viewer.py` (`sequence_meta`, `frame_info`, `annotation_payload`)
- Annotation state/renderer: `static/app.js`, `mot_viewer/services/annotations.py`, `mot_viewer/services/export_manager.py`
- Export dialog/menu: `templates/index.html` (`#exportModal`), `static/app.js`
- Existing image/video export: `mot_viewer/services/export_manager.py`
- Job/progress API: `mot_viewer/services/jobs.py`, `mot_viewer/routes/api.py`
- Unit test command: `/home/junja/miniconda3/envs/occrl/bin/python -m unittest discover -s tests`
- Smoke command: `PYTHONPATH=. /home/junja/miniconda3/envs/occrl/bin/python scripts/smoke_check.py`
- Lint/type/format/build configs: none discovered
- Development command: `PORT=5000 /home/junja/miniconda3/envs/occrl/bin/python app.py`
- Compile command: `/home/junja/miniconda3/envs/occrl/bin/python -m compileall .`

## Files Created Or Modified

- `mot_viewer/services/roi.py`
- `mot_viewer/services/export_manager.py`
- `mot_viewer/services/jobs.py`
- `mot_viewer/routes/api.py`
- `templates/index.html`
- `static/app.js`
- `static/style.css`
- `scripts/smoke_check.py`
- `tests/test_roi_core.py`
- `tests/test_roi_export.py`
- `tests/test_jobs.py`
- `README.md`
- `docs/assets/roi_batch_export/*.png`
- `docs/superpowers/reports/MOTScope_ROI_Batch_Export_v1_execution_report.md`

Plan documents were copied/read locally but not committed.

## Architecture Summary

The feature reuses the existing Flask service/export architecture. ROI geometry, frame-range resolution, naming, and annotation clipping live in `mot_viewer/services/roi.py`. `ExportManager.export_roi_batch` renders fixed source-coordinate crops one frame at a time, supports raw and annotated outputs, creates ZIP image sequences, creates optional server-side image files for browser folder saving, and encodes real MP4 files through ffmpeg. The existing in-process job manager now supports cancellation and exposes `/api/jobs/<job_id>/cancel`.

The UI remains in the existing plain JavaScript bundle. One active ROI is stored in native source-image pixels, drawn on the viewer canvas, synchronized with numeric fields, preserved across same-resolution sequences, and cleared when source resolution changes. The existing export dialog now includes ROI batch settings.

## Verification Commands And Results

```text
/home/junja/miniconda3/envs/occrl/bin/python -m pip install -r requirements.txt
Result: passed; requirements already satisfied.

/home/junja/miniconda3/envs/occrl/bin/python -m pip check
Result: passed; no broken requirements found.

/home/junja/miniconda3/envs/occrl/bin/python -m unittest discover -s tests
Result: passed; 17 tests.

PYTHONPATH=. /home/junja/miniconda3/envs/occrl/bin/python scripts/smoke_check.py
Result: passed.

/home/junja/miniconda3/envs/occrl/bin/python -m compileall .
Result: passed.

node.exe --check static/app.js
Result: passed.

ffmpeg -version / ffprobe -version
Result: available; version 6.1.1-3ubuntu5.

curl http://127.0.0.1:5023/
Result: HTTP 200.

git diff --check master...HEAD
Result: passed; no whitespace errors.
```

No lint, type-check, formatting-check, or production-build commands are configured in this repository.

## Manual Verification

Manual/browser verification used SportsMOT:

- Dataset: `sportsmot`
- Split: `train`
- Sequence: `v_1LwtoLPw2TU_c006`
- ROI: `x=320`, `y=180`, `width=256`, `height=144`
- Frame range: `1` to `3`, inclusive

Verified:

- ROI mode entry from the toolbar.
- Mouse drag creates an ROI.
- Numeric X/Y/Width/Height editing synchronizes to source pixels.
- Custom inclusive range displays `Frames: 3 (1 to 3, inclusive)`.
- Raw crop dimensions are `256 x 144`.
- Annotated Mode A crop dimensions are `256 x 144`.
- Annotated Mode B crop dimensions are `256 x 144`.
- Short raw MP4 dimensions are `256 x 144`, 3 frames.
- Short annotated Mode A MP4 dimensions are `256 x 144`, 3 frames.
- Short annotated Mode B MP4 dimensions are `256 x 144`, 3 frames.
- Browser-triggered ROI ZIP export downloaded successfully.
- Completion status now preserves the `Download again` link.
- Existing smoke coverage still verifies ordinary non-ROI frame/image/video export and smooth-video cache generation.

## Verification Artifacts

- `docs/assets/roi_batch_export/browser_roi_overlay.png`
- `docs/assets/roi_batch_export/browser_export_dialog.png`
- `docs/assets/roi_batch_export/roi_overlay.png`
- `docs/assets/roi_batch_export/roi_export_configuration.png`
- `docs/assets/roi_batch_export/raw_crop.png`
- `docs/assets/roi_batch_export/annotated_mode_a_crop.png`
- `docs/assets/roi_batch_export/annotated_mode_b_crop.png`

Generated large exports, ZIPs, videos, cache files, and temp files were left under ignored local `instance/` paths and were not committed.

## Browser And Directory Access

The headless Chromium verification reported `showDirectoryPicker` support. The implementation always generates ZIP output as a fallback and can write individual ROI image files to a selected browser directory when the File System Access API is available. The OS directory picker itself was not opened during the automated headless run.

## Video Encoder

ROI video export uses real ffmpeg MP4 encoding with `libx264` and `yuv444p`; output dimensions are the ROI dimensions. Raw and annotated videos are separate files.

## Known Limitations And Deviations

- The plan asked to commit the in-repository plan file, but the user instruction said not to commit plan-related documents, so the copied plan remained local and ignored.
- Browser folder saving depends on the File System Access API and is unavailable in unsupported browsers.
- Headless verification did not exercise the native OS directory chooser.
- No lint, type-check, formatting, component, end-to-end, or production-build command exists in the repository.

## Final Confirmation

- Current branch: `feature/roi-batch-export`
- `master` was not modified, force-pushed, merged, or checked out for changes.
- Plan Markdown files are not tracked.
- Unrelated local `ChatGPT Image ... :Zone.Identifier` files remain untracked and untouched.

Not merged into master; awaiting user verification.
