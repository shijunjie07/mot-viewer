# --------------------
# Dataset data models used by the viewer.
# @author: SHI JUNJIE
# 2026-04-25
# --------------------

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class DatasetDefinition:
    """Store normalized dataset settings for the viewer."""
    name: str
    root: Path
    splits: list[str] = field(default_factory=list)
    image_dir: str = "img1"
    gt_files: list[str] = field(default_factory=lambda: ["gt_vis.txt", "gt.txt"])
    seqinfo_filename: str = "seqinfo.ini"
    gameinfo_filename: str = "gameinfo.ini"
    source: str = "custom"

    def to_dict(self, resolved_splits: list[str] | None = None) -> dict:
        """Convert the dataset definition into a JSON-ready dictionary.

        Args:
            resolved_splits: Optional split list to expose instead of stored
                splits.

        Returns:
            dict: A serializable dataset payload.
        """
        return {
            "name": self.name,
            "root": str(self.root),
            "splits": resolved_splits if resolved_splits is not None else list(self.splits),
            "image_dir": self.image_dir,
            "gt_files": list(self.gt_files),
            "seqinfo_filename": self.seqinfo_filename,
            "gameinfo_filename": self.gameinfo_filename,
            "source": self.source,
        }
