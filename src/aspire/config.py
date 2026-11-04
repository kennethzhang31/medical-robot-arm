"""Local task contract, distinct from ASPIRE's paper benchmark protocols."""
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path

INSTRUMENTS = ("scalpel", "scissor", "love_retractor", "kelly", "scalpel_type2")


@dataclass(frozen=True)
class TaskConfig:
    target: str = "scissor"
    camera_size: int = 448
    max_steps: int = 2400
    target_cell: int | None = None
    yaw_deg: float | None = None
    tray_mode: str = "empty"
    distractor_min: int = 4
    distractor_max: int = 4
    randomization: str = "off"
    video_stride: int = 4
    sam3_url: str | None = None
    perception_backend: str = "rfdetr"
    rfdetr_url: str | None = None
    motion_timeout_s: float = 8.0
    solver_position_iterations: int | None = None
    solver_velocity_iterations: int | None = None
    allow_evaluator_feedback: bool = True
    sam3_target_prompt: str | None = None

    def __post_init__(self):
        if self.perception_backend not in ("rfdetr", "sam3"):
            raise ValueError("perception_backend must be rfdetr or sam3")
        if self.sam3_target_prompt is not None:
            if (self.perception_backend != "sam3" or not isinstance(self.sam3_target_prompt, str)
                    or not 1 <= len(self.sam3_target_prompt.strip()) <= 256
                    or self.sam3_target_prompt != self.sam3_target_prompt.strip()):
                raise ValueError("sam3_target_prompt must be a nonempty trimmed SAM3 text prompt")
        if self.target not in INSTRUMENTS:
            raise ValueError(f"Unknown instrument: {self.target}")
        if self.camera_size not in (224, 448):
            raise ValueError("camera_size must be 224 or 448")
        if self.max_steps < 1 or self.video_stride < 1:
            raise ValueError("Step budgets and video_stride must be positive")
        if self.target_cell is not None and not 0 <= self.target_cell < 10:
            raise ValueError("target_cell must be 0..9 in the current 2x5 layout")
        if self.yaw_deg is not None and not math.isfinite(self.yaw_deg):
            raise ValueError("yaw_deg must be finite")
        if self.tray_mode not in ("empty", "random", "full"):
            raise ValueError("tray_mode must be empty, random or full")
        if not 4 <= self.distractor_min <= self.distractor_max <= 30:
            raise ValueError("Distractors must satisfy 4 <= min <= max <= 30")
        if self.randomization not in ("off", "train"):
            raise ValueError("randomization must be off or train")
        if not math.isfinite(self.motion_timeout_s) or self.motion_timeout_s <= 0:
            raise ValueError("motion_timeout_s must be finite and positive")
        for name, maximum in (("solver_position_iterations", 64), ("solver_velocity_iterations", 32)):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or not 1 <= value <= maximum):
                raise ValueError(f"{name} must be None or an integer in 1..{maximum}")

    def to_dict(self):
        result = asdict(self)
        if self.sam3_target_prompt is None:
            result.pop("sam3_target_prompt")
        return result


def load_protocol(filename):
    data = json.loads(Path(filename).read_text(encoding="utf-8"))
    if data.get("contract") != "surgical_aspire_v1":
        raise ValueError("Expected surgical_aspire_v1 protocol")
    development, evaluation = data["development_seeds"], data["evaluation_seeds"]
    partitions = [development, evaluation]
    if "validation_seeds" in data:
        partitions.append(data["validation_seeds"])
    for seeds in partitions:
        if not seeds or any(type(s) is not int or s < 0 for s in seeds) or len(set(seeds)) != len(seeds):
            raise ValueError("Seed partitions must contain unique nonnegative integers")
    for index, seeds in enumerate(partitions):
        if any(set(seeds) & set(other) for other in partitions[index+1:]):
            raise ValueError("Development, validation and evaluation seeds must be disjoint")
    config = TaskConfig(**data["task"])
    return data, config
