# MOT Viewer

A lightweight MOT dataset viewer built with Flask.

![MOT Viewer demo](docs/assets/mot_viewer.gif)

## Installation

1. Clone the repository:

```bash
git clone <your-repo-url>
cd mot_viewer
```

2. Create and activate a Miniconda environment:

```bash
conda create -n mot-viewer python=3.11 -y
conda activate mot-viewer
```

If `conda` is not available yet, install Miniconda first:

https://docs.conda.io/en/latest/miniconda.html

3. Install the project dependencies:

```bash
pip install -e .
```

## Features

- Browse frames, boxes, IDs, and visibility values.
- Switch between multiple datasets from the UI.
- Register additional datasets without editing Python source.
- Support dataset-specific settings such as split names, image directory, metadata filenames, and GT filename priority.

## Supported Datasets

| Dataset | Description | URL |
| --- | --- | --- |
| SoccerNet-Tracking | Multi-object tracking dataset for soccer broadcast videos from the SoccerNet challenge. | https://github.com/SoccerNet/sn-tracking |
| DanceTrack | Multi-human tracking dataset with uniform appearance and diverse motion. | https://dancetrack.github.io/ |

## Run

```bash
python app.py
```

The viewer stores custom dataset definitions in `instance/datasets.json` by default.

The `instance/` folder is used for local, user-specific runtime data. In this project, it is the default place where users define their own datasets without modifying the source code. It is meant for local configuration and is usually ignored by git.

You can override that path with:

```bash
export MOT_VIEWER_DATASETS_CONFIG=/path/to/datasets.json
```

## Custom Datasets

Users can define their own datasets in either of these ways:

1. From the viewer UI:  
   Use the `Add Dataset` button and fill in the dataset root, splits, and optional file-layout fields.

2. Directly in the dataset config file:  
   Edit `instance/datasets.json` by default, or edit the file pointed to by `MOT_VIEWER_DATASETS_CONFIG` if you override it.

Custom datasets are loaded from that JSON file when the app starts, and datasets added from the UI are saved back into the same file.

Example `instance/datasets.json`:

```json
{
  "datasets": [
    {
      "name": "my_dataset",
      "root": "/path/to/my_dataset",
      "splits": ["train", "val", "test"],
      "image_dir": "img1",
      "gt_files": ["gt_vis.txt", "gt.txt"],
      "seqinfo_filename": "seqinfo.ini",
      "gameinfo_filename": "gameinfo.ini"
    }
  ]
}
```

## Dataset Shape

The generic viewer expects a structure like:

```text
<dataset-root>/
  <split>/
    <sequence>/
      img1/
      gt/
      seqinfo.ini      # optional
      gameinfo.ini     # optional
```

Notes:

- `img1/` and `gt/` are the common defaults, but different filenames and folder names can be configured when adding a dataset.
- `seqinfo.ini` is optional.
- `gameinfo.ini` is optional.
- GT files are resolved by priority order, defaulting to `gt_vis.txt` first and then `gt.txt`.
