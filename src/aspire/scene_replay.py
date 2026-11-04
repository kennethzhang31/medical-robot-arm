"""Private, measured initial-state pairing; never part of model context."""
import numpy as np


def encode_state(state):
    return {group: {name: {field: value.detach().cpu().tolist()
                          for field, value in fields.items()}
                    for name, fields in assets.items()}
            for group, assets in state.items()}


def state_difference(expected, actual, *, tolerance=1e-6):
    if set(expected) != set(actual):
        raise ValueError("Scene state groups differ")
    maximum = 0.
    for group, assets in expected.items():
        if set(assets) != set(actual[group]):
            raise ValueError("Scene assets differ: " + group)
        for name, fields in assets.items():
            if set(fields) != set(actual[group][name]):
                raise ValueError("Scene state fields differ: " + name)
            for field, values in fields.items():
                before = np.asarray(values, dtype=float)
                after = np.asarray(actual[group][name][field], dtype=float)
                if before.shape != after.shape or not before.size:
                    raise ValueError("Scene state shape differs: " + name + "/" + field)
                if not np.isfinite(before).all() or not np.isfinite(after).all():
                    raise ValueError("Nonfinite scene state")
                maximum = max(maximum, float(np.max(np.abs(before-after))))
    if maximum > tolerance:
        raise ValueError(f"Initial scene state mismatch: {maximum} > {tolerance}")
    return dict(matched=True, max_absolute_error=maximum, tolerance=tolerance,
                scope="asset poses, velocities and robot joints; not PhysX contact caches")


def restore_scene(backend, snapshot, seed):
    import torch
    if snapshot.get("contract") != "aspire_initial_state_v1":
        raise ValueError("Unknown initial scene contract")
    if snapshot["seed"] != seed or snapshot["task"] != backend.config.to_dict():
        raise ValueError("Initial scene target/configuration/seed differs")
    current = encode_state(backend.raw.scene.get_state())
    state_difference(snapshot["state"], current, tolerance=float("inf"))
    state = {group: {name: {field: torch.as_tensor(values, device=backend.raw.device,
                                                 dtype=torch.float32)
                           for field, values in fields.items()}
                     for name, fields in assets.items()}
             for group, assets in snapshot["state"].items()}
    with torch.inference_mode():
        backend.raw.scene.reset_to(state)
        backend.raw.scene.reset()
        backend.raw.sim.forward()
        for _ in range(3):
            backend.raw.sim.render()
        backend.raw.scene.update(backend.step_dt)
        return state_difference(snapshot["state"], encode_state(backend.raw.scene.get_state()))


def capture_scene(backend, seed):
    return dict(contract="aspire_initial_state_v1", seed=seed,
                task=backend.config.to_dict(), state=encode_state(backend.raw.scene.get_state()))
