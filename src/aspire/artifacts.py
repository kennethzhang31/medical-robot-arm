"""Failure-preserving trial artifacts, with no simulator dependency."""
import json
from pathlib import Path
import numpy as np
from PIL import Image


def serializable(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(type(value).__name__)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, default=serializable, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


class Artifacts:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.actions = (self.directory / "actions.jsonl").open("a", encoding="utf-8", buffering=1)

    def action(self, step, action, feedback):
        self.actions.write(json.dumps(dict(step=step, action=action, feedback=feedback), default=serializable)+"\n")

    def frame(self, step, front, wrist):
        directory = self.directory / "frames"
        directory.mkdir(exist_ok=True)
        for name, rgb in (("front", front), ("wrist", wrist)):
            Image.fromarray(rgb).save(directory / f"{step:06d}_{name}.jpg", quality=85)

    def observation(self, label, obs):
        directory = self.directory / label
        directory.mkdir(exist_ok=True)
        calibration = {}
        for name, camera in obs["cameras"].items():
            Image.fromarray(camera["images"]["rgb"]).save(directory / f"{name}.png")
            np.save(directory / f"{name}_depth.npy", camera["images"]["depth"], allow_pickle=False)
            calibration[name] = dict(intrinsics=camera["intrinsics"], pose_mat=camera["pose_mat"])
        write_json(directory / "observation.json", dict(cameras=calibration, robot=obs["robot"],
                                                       proprio=obs["proprio"], task_target=obs["task_target"]))

    def close(self):
        self.actions.close()
