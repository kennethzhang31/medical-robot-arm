# Environment & cameras

[Overview](../README.md) · [Recorder](../docs/RECORDER.md)

```mermaid
flowchart LR
    A["Scene JSON"] --> B["Shared environment"]
    C["Camera layout JSON"] --> D["Camera tuning"]
    D --> B
    E["Assets"] --> B
    B --> F["Simulator + recorder"]
    G["Original session manifest"] -->|Resume| D
```

| File | Purpose |
| --- | --- |
| `scene_layout.json` | Table, robot, grid, tray, lighting |
| `camera_layout.json` | Camera poses and focal length; active front view |
| `phase4_scene.py` | Scene assembly and provenance manifest |
| `phase3_shared_env_cfg.py` | Isaac environment builder; the legacy name remains active |
| `instrument_materials.py` | Steel finishes, surface-normal repair, and scissor material fallback |
| `new_environment.py` | Incoming cloth materials and seeded colour variation |
| `phase3_camera_tuning.py` | Native resolution, FOV, layout loading |
| `phase3_recorder_camera_patch.py` | Applying cameras to the recorder |
| `phase4_camera_names.py` | Sensor / public name mapping |
| `instrument_preview_geometry.json` | Panel preview geometry |
| `shared_layout.json` | Compatibility configuration |
| `camera_layout_front_tray_candidate.json` | Historical candidate, not the active layout |

Root JSON aliases are hard links in this organized workspace. Do not treat them as independent configurations.
Run `python scripts/check_structure.py` after layout changes.

See [Simulation material realism](../docs/SIMULATION_REALISM.md) for finish values,
textured tabletop variation, validation, and matching workspace photographs.
See [New environment transfer](../docs/NEW_ENVIRONMENT_TRANSFER.md) for the active
cloth replacement and eight satin tools displayed on background Table_03.

| Change | Rule |
| --- | --- |
| New resolution or framing | Start a new session and restart the simulator |
| Resume | Preserve the original configuration and manifest layout |
| Frozen benchmark | Do not change the layout while it is running |
