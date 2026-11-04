"""Shared scene configuration for all Phase-3 recorders.

Recorder files declare only a :class:`RecorderEnvRequest`.  Asset paths,
physics, cameras, and optional room furniture live here so a scene-wide change
does not have to be repeated in five large trajectory scripts.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
import json
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent
ASSET_DIR = ROOT / "assets"


@dataclass(frozen=True)
class WorkspaceCfg:
    """One-place transforms for the shared robot workspace.

    Keep ``robot_pos``/``table_pos`` as ``None`` to preserve the base IsaacLab
    task transform. Set them explicitly when replacing/repositioning hardware.
    All Z offsets below are relative to ``table_surface_z``.
    """

    table_surface_z: float = 0.0
    robot_pos: tuple[float, float, float] | None = None
    robot_rot: tuple[float, float, float, float] | None = None
    table_pos: tuple[float, float, float] | None = None
    table_rot: tuple[float, float, float, float] | None = None
    # Tray sits on the near edge of surgical table 2 while remaining inside
    # Franka's practical reach envelope.
    tray_xy: tuple[float, float] = (0.3680401892, 0.5927763309)
    # Seat the rendered tray about 2.2 mm into the visual cloth so it cannot
    # appear to float because of cloth relief, shadows, or bounding-box slack.
    # The tray USD origin sits below its visible underside. A small negative
    # root offset makes the visible tray rest on the surgical-table cloth.
    tray_z_above_table: float = -0.0040
    tray_yaw_deg: float = 90.0
    # A centered 5x3 square grid based on the measured flat tabletop. Each
    # cell is ~0.122 m square and all four outer margins are ~0.085 m.
    grid_x: tuple[float, float] = (0.2476694576, 0.8577602546)
    grid_y: tuple[float, float] = (-0.1663356954, 0.1997197826)
    grid_cols: int = 5
    grid_rows: int = 3
    # Translation of the complete validated workspace. Rotation is deliberately
    # unsupported because the legacy recorders contain axis-aligned XY ranges.
    offset: tuple[float, float, float] = (0.0, 0.0, 0.0)


# Edit this single object to move the shared robot/table/tray/spawn workspace.
WORKSPACE = WorkspaceCfg()


@dataclass(frozen=True)
class LightingCfg:
    """Shared recorder lighting; local light positions follow the workspace."""

    ambient_intensity: float = 1800.0
    ambient_color: tuple[float, float, float] = (0.82, 0.88, 1.0)
    key_intensity: float = 45000.0
    key_color: tuple[float, float, float] = (1.0, 0.93, 0.82)
    key_pos: tuple[float, float, float] = (0.52, 0.08, 1.55)
    key_radius: float = 0.65
    fill_intensity: float = 22000.0
    fill_color: tuple[float, float, float] = (0.82, 0.90, 1.0)
    fill_pos: tuple[float, float, float] = (0.20, -0.35, 1.05)
    fill_radius: float = 0.45


# Edit these values once to tune illumination for every recorder.
LIGHTING = LightingCfg()


@dataclass(frozen=True)
class MotionTimingCfg:
    """Shared fast recorder timing used by every object backend."""

    close_steps: int = 32
    open_steps: int = 24
    lower_min_steps: int = 24
    lower_grasp_min_steps: int = 20
    lower_extra_min_steps: int = 16
    lower_grasp_dist_thresh: float = 0.010
    open_hover_profile: tuple[int, int, int] = (7, 50, 2)
    lower_grasp_profile: tuple[int, int, int] = (9, 80, 4)
    lift_clear_profile: tuple[int, int, int] = (7, 50, 3)
    move_to_target_profile: tuple[int, int, int] = (8, 75, 2)
    retreat_profile: tuple[int, int, int] = (7, 50, 2)


# One timing source for all five recorders. Object-specific grasp/yaw/lower
# geometry remains inside each handler; only stage speed/duration is shared.
MOTION_TIMING = MotionTimingCfg()


@dataclass(frozen=True)
class AssetSpec:
    usd: str
    prim_name: str
    scale: tuple[float, float, float]
    mass: float
    initial_pos: tuple[float, float, float]
    contact_offset: float = 0.003
    rest_offset: float = 0.0


INSTRUMENTS = {
    "scalpel": AssetSpec("knife_centered.usd", "Scalpel", (1.0, 1.0, 1.0), 0.12, (0.55, 0.20, 0.0664)),
    "scissor": AssetSpec("my_scissor_clean.usd", "Scissor", (0.01, 0.01, 0.01), 0.12, (0.45, 0.28, 0.0025)),
    "love_retractor": AssetSpec("love_centered_root_at_center.usd", "LoveRetractor", (0.00075,) * 3, 0.10, (0.45, 0.28, 0.002)),
    "kelly": AssetSpec("kelly_root_at_center.usd", "Kelly", (0.60,) * 3, 0.10, (0.45, 0.30, 0.002)),
    "scalpel_type2": AssetSpec("scalpel_type2_root.usd", "ScalpelType2", (0.00715074,) * 3, 0.10, (0.62, 0.30, 0.006)),
}

from env.instrument_materials import INSTRUMENT_MATERIAL_OVERRIDES, spawn_satin_instrument

# Optional static environment assets. Disabled by default to preserve the
# original dataset scene. Add their names to RecorderEnvRequest.environment.
@dataclass(frozen=True)
class EnvironmentAssetSpec:
    usd: str
    prim_name: str
    pos: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rot: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0)
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)


# Add future room/furniture USD(Z) files here, then select their registry names
# in each recorder's ENV_REQUEST.environment.
ENVIRONMENT_ASSETS = {
    # These USDZ assets were authored at centimeter-like scale. Start at 0.01
    # relative to Isaac's meter workspace; fine-tune and save through the GUI.
    "hospital_room": EnvironmentAssetSpec(
        "hospital_room.usdz", "HospitalRoom", scale=(0.01, 0.01, 0.01)),
    "operating_bed": EnvironmentAssetSpec(
        "operating_bed.usdz", "OperatingBed", scale=(0.01, 0.01, 0.01)),
}

# One global switch for every recorder. Keep empty for the validated plain
# workspace; enable later with ("hospital_room", "operating_bed").
ACTIVE_ENVIRONMENT_ASSETS: tuple[str, ...] = ()

# Replacement tabletop visual. The original Franka table stays loaded as an
# invisible collision asset, preserving all validated physics and coordinates.
SURGICAL_TABLE_USD = ASSET_DIR / "surgical_instrument_table_normalized.usda"
SURGICAL_TABLE_SCALE = (0.875, 0.875, 0.875)
# Normalized source footprint is 1.066463 x 1.175078 m. Since the saved table
# pose rotates it 90 degrees around Z, its world X width is the scaled 1.175078
# side. Offset table 2 by exactly that width so both tabletops touch edge-to-edge.
SURGICAL_TABLE_WORLD_SIZE = (1.0281931528, 0.9331551246, 1.0492938659)
# Measured from vertices at the actual flat top, excluding hanging cloth.
SURGICAL_TABLETOP_WORLD_SIZE = (0.7793843890, 0.5353477511, 0.05)
SURGICAL_TABLETOP_CENTER_OFFSET = (0.0527144058, 0.0166919440, -0.025)
SECOND_SURGICAL_TABLE_OFFSET = (0.0, SURGICAL_TABLETOP_WORLD_SIZE[1], 0.0)

LAYOUT_FILE = ROOT/'env'/"shared_layout.json"


def _load_saved_gui_layout() -> None:
    """Apply transforms captured by the GUI layout tuner, when present."""
    global WORKSPACE, ACTIVE_ENVIRONMENT_ASSETS
    if not LAYOUT_FILE.exists():
        return
    data = json.loads(LAYOUT_FILE.read_text(encoding="utf-8"))
    def unit_quat(values):
        q = tuple(float(v) for v in values)
        norm = sum(v * v for v in q) ** 0.5
        if norm < 1.0e-8:
            return (1.0, 0.0, 0.0, 0.0)
        return tuple(v / norm for v in q)

    robot = data.get("robot")
    table = data.get("table")
    WORKSPACE = replace(
        WORKSPACE,
        robot_pos=tuple(robot["pos"]) if robot else WORKSPACE.robot_pos,
        robot_rot=unit_quat(robot["rot"]) if robot else WORKSPACE.robot_rot,
        table_pos=tuple(table["pos"]) if table else WORKSPACE.table_pos,
        table_rot=unit_quat(table["rot"]) if table else WORKSPACE.table_rot,
        offset=tuple(data.get("workspace_offset", WORKSPACE.offset)),
    )
    for name, pose in data.get("environment", {}).items():
        if name in ENVIRONMENT_ASSETS:
            ENVIRONMENT_ASSETS[name] = replace(
                ENVIRONMENT_ASSETS[name],
                pos=tuple(pose["pos"]),
                rot=unit_quat(pose["rot"]),
                scale=tuple(pose.get("scale", ENVIRONMENT_ASSETS[name].scale)),
            )
    ACTIVE_ENVIRONMENT_ASSETS = tuple(data.get("active_environment", ACTIVE_ENVIRONMENT_ASSETS))
    print(f"[SHARED LAYOUT LOADED] {LAYOUT_FILE}")


_load_saved_gui_layout()

# P4 changes only scene placement. Keep the shared instrument registry and
# motion timing exactly as copied from P3.
from phase4_scene import apply_workspace as _p4_workspace
WORKSPACE = _p4_workspace(WORKSPACE)
ACTIVE_ENVIRONMENT_ASSETS = ()


@dataclass(frozen=True)
class RecorderEnvRequest:
    target: str
    distractors: tuple[str, ...] = ()
    environment: tuple[str, ...] | None = None
    use_canonical_target_only: bool = False

    @property
    def instruments(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((self.target, *self.distractors)))

    @property
    def resolved_environment(self) -> tuple[str, ...]:
        return ACTIVE_ENVIRONMENT_ASSETS if self.environment is None else self.environment


def _validate_names(names: Iterable[str], registry: dict, kind: str) -> None:
    unknown = sorted(set(names) - set(registry))
    if unknown:
        raise ValueError(f"Unknown {kind}: {unknown}; available={sorted(registry)}")


def apply_workspace_globals(namespace: dict, workspace: WorkspaceCfg = WORKSPACE) -> None:
    """Inject shared workspace constants used by legacy trajectory helpers."""
    dx, dy, dz = (float(v) for v in workspace.offset)
    z = float(workspace.table_surface_z) + dz
    def shifted(values, delta):
        return tuple(float(v) + delta for v in values)

    namespace.update({
        "TABLE_Z": z,
        "TRAY_FIXED_POS": (workspace.tray_xy[0] + dx, workspace.tray_xy[1] + dy,
                           z + workspace.tray_z_above_table),
        "TRAY_FIXED_YAW_DEG": float(workspace.tray_yaw_deg),
        "GRID_X_RANGE": shifted(workspace.grid_x, dx),
        "GRID_Y_RANGE": shifted(workspace.grid_y, dy),
        "VIS_GRID_X_RANGE": shifted(workspace.grid_x, dx),
        "VIS_GRID_Y_RANGE": shifted(workspace.grid_y, dy),
        "GRID_COLS": int(workspace.grid_cols),
        "GRID_ROWS": int(workspace.grid_rows),
        "SCISSOR_SPAWN_ROOT_Z": z + 0.0025,
        "LOVE_SPAWN_ROOT_Z": z + 0.0010,
        "KELLY_SPAWN_ROOT_Z": z + 0.0140,
        "SCALPEL_TYPE2_SPAWN_ROOT_Z": z + 0.0120,
    })
    # Preserve recorder-specific narrower spawn ranges, tray random ranges, and
    # visualization bounds while translating all of them by the same amount.
    for key, value in list(namespace.items()):
        if not isinstance(value, tuple) or len(value) != 2:
            continue
        if key in {"GRID_X_RANGE", "GRID_Y_RANGE", "VIS_GRID_X_RANGE", "VIS_GRID_Y_RANGE"}:
            continue
        if key != "TRAY_RANDOM_X_RANGE" and (
            key.endswith("_RANDOM_X_RANGE") or key.endswith("_RANDOM_CENTER_X_RANGE")
        ):
            namespace[key] = shifted(workspace.grid_x, dx)
            continue
        if key != "TRAY_RANDOM_Y_RANGE" and (
            key.endswith("_RANDOM_Y_RANGE") or key.endswith("_RANDOM_CENTER_Y_RANGE")
        ):
            namespace[key] = shifted(workspace.grid_y, dy)
            continue
        if key.endswith("_X_RANGE"):
            namespace[key] = shifted(value, dx)
        elif key.endswith("_Y_RANGE"):
            namespace[key] = shifted(value, dy)
    print("[SHARED WORKSPACE]", workspace)
    from phase4_runtime import install_runtime_hooks
    install_runtime_hooks(namespace)


def apply_shared_env_cfg(env_cfg, request: RecorderEnvRequest, *, camera_width: int,
                         camera_height: int, grip_camera_prim: str,
                         grip_pos, grip_rot):
    """Apply the authoritative Phase-3 scene config before ``gym.make``.

    Imports are intentionally local: this module can be inspected and edited
    without launching Isaac Sim.
    """
    _validate_names(request.instruments, INSTRUMENTS, "instrument")
    _validate_names(request.resolved_environment, ENVIRONMENT_ASSETS, "environment asset")

    from isaaclab.assets import AssetBaseCfg, RigidObjectCfg
    from isaaclab.sensors import CameraCfg
    import isaaclab.sim as sim_utils

    def offset_pos(pos):
        return tuple(float(pos[i]) + float(WORKSPACE.offset[i]) for i in range(3))

    # Replace only the table appearance. The hidden Franka table continues to
    # provide the exact collision surface used by the proven pick/place logic.
    base_table = getattr(env_cfg.scene, "table", None)
    if base_table is not None:
        table_pos = WORKSPACE.table_pos or tuple(base_table.init_state.pos)
        table_rot = WORKSPACE.table_rot or tuple(base_table.init_state.rot)
        second_table_pos = tuple(
            float(table_pos[i]) + SECOND_SURGICAL_TABLE_OFFSET[i] for i in range(3)
        )
        base_table.spawn.visible = False
        env_cfg.scene.surgical_table_visual = AssetBaseCfg(
            prim_path="{ENV_REGEX_NS}/SurgicalInstrumentTable",
            spawn=sim_utils.UsdFileCfg(
                usd_path=str(SURGICAL_TABLE_USD),
                scale=SURGICAL_TABLE_SCALE,
            ),
            init_state=AssetBaseCfg.InitialStateCfg(pos=table_pos, rot=table_rot),
        )
        env_cfg.scene.surgical_table_visual_2 = AssetBaseCfg(
            prim_path="{ENV_REGEX_NS}/SurgicalInstrumentTable2",
            spawn=sim_utils.UsdFileCfg(
                usd_path=str(SURGICAL_TABLE_USD),
                scale=SURGICAL_TABLE_SCALE,
            ),
            init_state=AssetBaseCfg.InitialStateCfg(pos=second_table_pos, rot=table_rot),
        )
        # The second table is outside the original Franka collision asset. A
        # hidden thin cuboid provides a stable tabletop at the same Z=0 plane.
        env_cfg.scene.surgical_table_collision_2 = AssetBaseCfg(
            prim_path="{ENV_REGEX_NS}/SurgicalInstrumentTable2Collision",
            spawn=sim_utils.CuboidCfg(
                size=SURGICAL_TABLETOP_WORLD_SIZE,
                visible=False,
                collision_props=sim_utils.CollisionPropertiesCfg(),
            ),
            init_state=AssetBaseCfg.InitialStateCfg(
                pos=tuple(
                    second_table_pos[i] + SURGICAL_TABLETOP_CENTER_OFFSET[i]
                    for i in range(3)
                )
            ),
        )

    def rigid_cfg(name: str, *, prim_name: str | None = None, canonical: bool = False):
        spec = INSTRUMENTS[name]
        material = INSTRUMENT_MATERIAL_OVERRIDES.get(name)
        return RigidObjectCfg(
            prim_path=f"{{ENV_REGEX_NS}}/{prim_name or spec.prim_name}",
            spawn=sim_utils.UsdFileCfg(
                usd_path=str(ASSET_DIR / spec.usd),
                func=spawn_satin_instrument,
                scale=spec.scale,
                semantic_tags=[("class", name)],
                visual_material=(
                    sim_utils.PreviewSurfaceCfg(
                        diffuse_color=material.diffuse_color,
                        metallic=material.metallic,
                        roughness=material.roughness,
                    )
                    if material is not None else None
                ),
                rigid_props=sim_utils.RigidBodyPropertiesCfg(
                    disable_gravity=False,
                    linear_damping=0.0 if canonical else 0.8,
                    angular_damping=0.0 if canonical else 4.0),
                collision_props=sim_utils.CollisionPropertiesCfg(
                    contact_offset=0.008 if canonical else spec.contact_offset,
                    rest_offset=0.0002 if canonical else spec.rest_offset),
                mass_props=sim_utils.MassPropertiesCfg(mass=0.10 if canonical else spec.mass),
            ),
            init_state=RigidObjectCfg.InitialStateCfg(
                pos=(spec.initial_pos[0] + WORKSPACE.offset[0],
                     spec.initial_pos[1] + WORKSPACE.offset[1],
                     spec.initial_pos[2] + WORKSPACE.table_surface_z + WORKSPACE.offset[2]),
                rot=(1.0, 0.0, 0.0, 0.0)),
        )

    # Authoritative runtime asset configuration. Any legacy definitions made
    # earlier by a recorder are replaced here before gym.make.
    env_cfg.scene.object = rigid_cfg(request.target, prim_name="Object", canonical=True)
    for name in INSTRUMENTS:
        if name == request.target and request.use_canonical_target_only:
            # The task already owns this target as `scene.object`; do not spawn
            # a second rigid body with the same semantic role.
            setattr(env_cfg.scene, name, None)
        elif name not in request.instruments:
            setattr(env_cfg.scene, name, None)
        else:
            setattr(env_cfg.scene, name, rigid_cfg(name))

    from src.recorder.scene_clutter import add_to_scene
    add_to_scene(env_cfg.scene, request.target, rigid_cfg)

    if hasattr(env_cfg, "events") and hasattr(env_cfg.events, "reset_object_position"):
        reset_params = env_cfg.events.reset_object_position.params
        body_name = {
            "scalpel": "Surgical_Knife_fbx",
        }.get(request.target, "Object")
        reset_params["asset_cfg"].body_names = [body_name]
        if "pose_range" in reset_params:
            reset_params["pose_range"]["yaw"] = (-3.1416, 3.1416)

    env_cfg.scene.camera = CameraCfg(
        prim_path="{ENV_REGEX_NS}/cam_front",
        spawn=sim_utils.PinholeCameraCfg(
            focal_length=16.0, horizontal_aperture=20.955,
            clipping_range=(0.01, 10.0)),
        width=camera_width, height=camera_height,
        data_types=["rgb", "distance_to_image_plane", "semantic_segmentation"],
        update_period=0,
        offset=CameraCfg.OffsetCfg(
            pos=(0.88 + WORKSPACE.offset[0],
                 0.00 + WORKSPACE.offset[1],
                 0.50 + WORKSPACE.offset[2]),
            rot=(0.27131, -0.64716, -0.65462, 0.28115)),
    )
    env_cfg.scene.grip_cam_b = CameraCfg(
        prim_path=grip_camera_prim,
        spawn=sim_utils.PinholeCameraCfg(
            focal_length=14.0, horizontal_aperture=20.955,
            clipping_range=(0.001, 2.0)),
        width=camera_width, height=camera_height,
        data_types=["rgb", "distance_to_image_plane", "semantic_segmentation"],
        update_period=0,
        offset=CameraCfg.OffsetCfg(pos=grip_pos, rot=grip_rot),
    )

    # Shared illumination for all RGB cameras. Local lights illuminate the
    # tabletop even when the imported hospital shell blocks environment light.
    env_cfg.scene.shared_ambient_light = AssetBaseCfg(
        prim_path="/World/SharedAmbientLight",
        spawn=sim_utils.DomeLightCfg(
            intensity=LIGHTING.ambient_intensity,
            color=LIGHTING.ambient_color),
    )
    env_cfg.scene.shared_key_light = AssetBaseCfg(
        prim_path="{ENV_REGEX_NS}/SharedKeyLight",
        spawn=sim_utils.SphereLightCfg(
            intensity=LIGHTING.key_intensity,
            color=LIGHTING.key_color,
            radius=LIGHTING.key_radius),
        init_state=AssetBaseCfg.InitialStateCfg(pos=offset_pos(LIGHTING.key_pos)),
    )
    env_cfg.scene.shared_fill_light = AssetBaseCfg(
        prim_path="{ENV_REGEX_NS}/SharedFillLight",
        spawn=sim_utils.SphereLightCfg(
            intensity=LIGHTING.fill_intensity,
            color=LIGHTING.fill_color,
            radius=LIGHTING.fill_radius),
        init_state=AssetBaseCfg.InitialStateCfg(pos=offset_pos(LIGHTING.fill_pos)),
    )

    # The tray is part of the shared scene so it is visible immediately when
    # the environment launches. Recorder episodes reuse this exact prim.
    env_cfg.scene.shared_surgical_tray = AssetBaseCfg(
        prim_path="/World/RandomTray",
        spawn=sim_utils.UsdFileCfg(
            usd_path=str(ASSET_DIR / "SurgicalTray.usd"),
            scale=(0.0025, 0.0025, 0.0025),
            semantic_tags=[("class", "surgical_tray")],
        ),
        init_state=AssetBaseCfg.InitialStateCfg(
            pos=(WORKSPACE.tray_xy[0] + WORKSPACE.offset[0],
                 WORKSPACE.tray_xy[1] + WORKSPACE.offset[1],
                 WORKSPACE.table_surface_z + WORKSPACE.offset[2] + WORKSPACE.tray_z_above_table),
        ),
    )

    for name, spec in ENVIRONMENT_ASSETS.items():
        setattr(
            env_cfg.scene,
            name,
            AssetBaseCfg(
                prim_path=f"{{ENV_REGEX_NS}}/{spec.prim_name}",
                spawn=sim_utils.UsdFileCfg(
                    usd_path=str(ASSET_DIR / spec.usd), scale=spec.scale),
                init_state=AssetBaseCfg.InitialStateCfg(pos=spec.pos, rot=spec.rot),
            ) if name in request.resolved_environment else None,
        )

    if WORKSPACE.robot_pos is not None:
        env_cfg.scene.robot.init_state.pos = WORKSPACE.robot_pos
    if WORKSPACE.robot_rot is not None:
        env_cfg.scene.robot.init_state.rot = WORKSPACE.robot_rot
    if hasattr(env_cfg.scene, "table") and getattr(env_cfg.scene, "table", None) is not None:
        if WORKSPACE.table_pos is not None:
            env_cfg.scene.table.init_state.pos = WORKSPACE.table_pos
        if WORKSPACE.table_rot is not None:
            env_cfg.scene.table.init_state.rot = WORKSPACE.table_rot

    if hasattr(env_cfg, "terminations"):
        if hasattr(env_cfg.terminations, "time_out"):
            env_cfg.terminations.time_out = None
        if hasattr(env_cfg.terminations, "object_dropping"):
            env_cfg.terminations.object_dropping = None
    if getattr(env_cfg.scene.robot, "spawn", None) is not None:
        env_cfg.scene.robot.spawn.semantic_tags = [("class", "robot")]

    print("[SHARED ENV CFG] target=", request.target,
          "distractors=", request.distractors,
          "environment=", request.resolved_environment)
    from phase4_scene import apply_scene
    return apply_scene(env_cfg)
