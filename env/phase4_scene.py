"""P4 scene geometry only. Instrument physics/actions/schema remain in P3 copies.

The hospital is rigidly aligned to the selected table, keeping its support at
Z=0 so the existing object handlers retain their table-relative conventions.
No size changes are applied to the hospital, its furniture, or cameras.
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LAYOUT = json.loads((ROOT/'env'/"scene_layout.json").read_text(encoding="utf-8"))


def write_run_manifest(object_name, forwarded_args):
    """Keep scene provenance beside H5 files without altering the P3 schema."""
    import argparse
    import hashlib
    import os
    from phase4_camera_names import FRONT_PUBLIC, FRONT_SENSOR, FRONT_PRIM, FRONT_DATA
    from phase4_session import load_session
    session_config=load_session()
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--out_dir', default='datasets/phase3_grid_split')
    parser.add_argument('--record_mode', default='both')
    args, _ = parser.parse_known_args(forwarded_args)
    output = Path(args.out_dir)
    output.mkdir(parents=True, exist_ok=True)
    from src.recorder.capture_contract import capture_contract
    contract = capture_contract(os.environ.get('P4_DATASET_PURPOSE','detection'),
                                args.record_mode, int(os.environ.get('P4_CAMERA_SIZE','448')),
                                int(os.environ.get('P4_RANDOMIZATION_SEED','17')),
                                os.environ.get('P4_DATASET_SPLIT','unassigned'))
    (output/'capture_contract.json').write_text(json.dumps(contract,indent=2),encoding='utf-8')
    files = [ROOT/'record.py', ROOT/'env'/'scene_layout.json',
             ROOT/'env'/'camera_layout.json',
             ROOT/'env'/'instrument_preview_geometry.json',
             ROOT/'assets'/'blender_normals'/'love_retractor.usda',
             ROOT/'assets'/LAYOUT['hospital_asset']]
    files.extend(sorted((ROOT/'assets'/'blender_microfiber').glob('*')))
    files.extend(p for p in sorted((ROOT/'assets'/'new_environment').rglob('*')) if p.is_file())
    files.extend(sorted((ROOT/'backends').glob('*recorder.py')))
    files.extend(sorted((ROOT/'src').rglob('*.py')))
    files.extend(sorted((ROOT/'env').glob('*.py')))
    files.extend(sorted((ROOT/'compat').glob('*.py')))
    payload = {
        'project': 'P4', 'object': object_name,
        'capture_contract': contract,
        'feedback_version': '20260916-tray-slots-v1',
        'tray_contract': 'tray_slots_v1',
        'tray_occupancy': (session_config or {}).get('tray_mode',os.environ.get('P4_TRAY_OCCUPANCY','random')),
        'initial_session_config': session_config,
        'control_tcp_offset_m': [0.0, 0.0, 0.1034],
        'tcp_jacobian_contract': 'world_COM_to_base_observed_TCP_v1',
        'approach_controller': 'tcp_frame_correct_bounded_place_integral_v6',
        'storage_contract': 'journaled_episode_v2',
        'max_attempts': int(os.environ.get('P4_MAX_ATTEMPTS', 0)),
        'symmetric_grasp_candidate': os.environ.get('P4_SYMMETRIC_GRASP', '1') == '1',
        'camera_name_mapping': {FRONT_PUBLIC:{'sensor_key':FRONT_SENSOR,'prim_path':FRONT_PRIM,'h5':FRONT_DATA}},
        'scene_layout': LAYOUT,
        'camera_layout': (json.loads(Path(os.environ['P4_RESUME_CAMERA_MANIFEST']).read_text(encoding='utf-8'))['camera_layout']
                          if os.environ.get('P4_RESUME_CAMERA_MANIFEST') else json.loads((ROOT/'env'/'camera_layout.json').read_text(encoding='utf-8'))),
        'asset_and_config_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        'camera_contract': (json.loads(Path(os.environ['P4_RESUME_CAMERA_MANIFEST']).read_text(encoding='utf-8')).get('camera_contract','native_square_wide_table_v2')
                            if os.environ.get('P4_RESUME_CAMERA_MANIFEST') else 'native_square_front_work_v3'),
        'render_contract': 'native_fxaa_no_frame_generation_4spp_v2',
        'material_contract': 'matched_satin_steel_new_env_cloth_v6' if LAYOUT.get('cloth_material') else 'matched_satin_steel_microfiber_drape_v5',
        'cloth_material_contract': LAYOUT.get('cloth_material', 'blender_microfiber_v2'),
        'display_instruments': 'eight_static_satin_tools_on_Table_03' if LAYOUT.get('display_new_instruments') else None,
        'visual_normals_contract': 'blender_weighted_retractor_normals_v1',
        'camera_size': int(os.environ.get('P4_CAMERA_SIZE', '448')),
        'randomization': os.environ.get('P4_RANDOMIZATION', 'train'),
        'randomization_seed': int(os.environ.get('P4_RANDOMIZATION_SEED', '17')),
        'note': 'Native square RGB/depth/semantic; no crop or resize in recorder. New front view focuses on main work grid; resume preserves original camera layout.'
    }
    (output/'scene_manifest.json').write_text(json.dumps(payload, indent=2), encoding='utf-8')


def table_geometry():
    from pxr import Usd, UsdGeom, Gf
    stage = Usd.Stage.Open(str(ROOT / "assets" / LAYOUT["hospital_asset"]))
    if UsdGeom.GetStageUpAxis(stage) != "Z" or UsdGeom.GetStageMetersPerUnit(stage) != 1.0:
        raise ValueError("P4 hospital must be meter/Z-up; explicit conversion required")
    tables = [p for p in stage.GetPrimAtPath("/HospitalScene/Furniture").GetChildren()
              if p.GetName().startswith("Table_")]
    selected = next((p for p in tables if p.GetName() == LAYOUT["selected_table"]), None)
    if selected is None:
        raise ValueError(f"Unknown table; choices: {[p.GetName() for p in tables]}")
    top = next(p for p in Usd.PrimRange(selected) if "Tabletop" in p.GetName())
    matrix = UsdGeom.Xformable(top).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    size = float(UsdGeom.Cube(top).GetSizeAttr().Get())
    center = matrix.Transform(Gf.Vec3d(0))
    axes = [matrix.TransformDir(Gf.Vec3d(*[float(j == i) for j in range(3)])) for i in range(3)]
    dimensions = [float(v.GetLength()) * size for v in axes]
    old_yaw = math.atan2(axes[0][1], axes[0][0])
    yaw = math.radians(LAYOUT["table_yaw_deg"]) - old_yaw
    c, s = math.cos(yaw), math.sin(yaw)
    height = float(center[2]) + dimensions[2] / 2
    room_pos = (LAYOUT["table_center_xy"][0] - c*center[0] + s*center[1],
                LAYOUT["table_center_xy"][1] - s*center[0] - c*center[1], -height)
    result = dict(table=selected.GetName(), choices=[p.GetName() for p in tables],
                  dimensions=dimensions, room_pos=room_pos,
                  room_rot=(math.cos(yaw/2), 0., 0., math.sin(yaw/2)),
                  source_top_height=height)
    validate_layout(result)
    return result


def validate_layout(geometry):
    # Containment in table-local axes, including instrument/tray extents.
    yaw = math.radians(LAYOUT["table_yaw_deg"])
    c, s = math.cos(yaw), math.sin(yaw)
    tx, ty = LAYOUT["table_center_xy"]
    half = [v/2 for v in geometry["dimensions"][:2]]
    def inside(x, y, margin):
        u, v = c*(x-tx)+s*(y-ty), -s*(x-tx)+c*(y-ty)
        return abs(u)+margin <= half[0] and abs(v)+margin <= half[1]
    for x in LAYOUT["grid_x"]:
        for y in LAYOUT["grid_y"]:
            if not inside(x,y,0.04 if LAYOUT.get('fit_objects_to_cells') else 0.085):
                raise ValueError("Grid must retain 8.5 cm instrument clearance from tabletop edges")
    gx, gy = LAYOUT["grid_x"], LAYOUT["grid_y"]
    if not math.isclose((gx[1]-gx[0])/LAYOUT["grid_cols"], (gy[1]-gy[0])/LAYOUT["grid_rows"], abs_tol=1e-6):
        raise ValueError("Grid cells must be square")
    rx, ry = LAYOUT["robot_pos"][:2]
    for x in gx:
        for y in gy:
            if math.hypot(x-rx, y-ry) > 0.80:
                raise ValueError("Grid exceeds conservative 0.80m XY reach check")
    green = LAYOUT.get('green_area_y')
    if green:
        footprint_margin = 0.0 if LAYOUT.get('fit_objects_to_cells') else 0.085
        if gy[0]-footprint_margin < green[0] or gy[1]+footprint_margin > green[1]:
            raise ValueError('Grid instrument footprint crosses the blue-pad boundary')
        if not math.isclose((gy[0]+gy[1])/2, ry, abs_tol=1e-5):
            raise ValueError('Robot and grid must share the green-area centerline')
    dims = LAYOUT.get('tray_dimensions_local_xy', [0.197843, 0.296635])
    tray_yaw = math.radians(LAYOUT['tray_yaw_deg'])
    ct, st = math.cos(tray_yaw), math.sin(tray_yaw)
    px, py = LAYOUT['tray_xy']
    for u in (-dims[0]/2, dims[0]/2):
        for v in (-dims[1]/2, dims[1]/2):
            if not inside(px+ct*u-st*v, py+st*u+ct*v,0.04):
                raise ValueError('Tray footprint must keep 4cm tabletop-edge clearance')
    if math.hypot(px-rx, py-ry) > 0.80:
        raise ValueError('Tray target exceeds conservative 0.80m XY reach check')


def tray_scale_for_layout(usd_path):
    from pxr import Usd, UsdGeom
    stage = Usd.Stage.Open(str(usd_path))
    bounds = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default','render']).ComputeWorldBound(stage.GetDefaultPrim()).ComputeAlignedRange()
    size = bounds.GetSize()
    desired = LAYOUT.get('tray_dimensions_local_xy')
    return (desired[0]/size[0], desired[1]/size[1], 0.0025) if desired else (0.0025,)*3


def apply_workspace(workspace):
    from dataclasses import replace
    # Use the same table-relative Z=0 convention as P3.
    return replace(workspace, offset=(0.,0.,0.), table_surface_z=0.,
                   robot_pos=tuple(LAYOUT["robot_pos"]),
                   robot_rot=tuple(LAYOUT["robot_rot_wxyz"]),
                   table_pos=(0.,0.,0.), table_rot=(1.,0.,0.,0.),
                   grid_x=tuple(LAYOUT["grid_x"]), grid_y=tuple(LAYOUT["grid_y"]),
                   grid_cols=LAYOUT["grid_cols"], grid_rows=LAYOUT["grid_rows"],
                   tray_xy=tuple(LAYOUT["tray_xy"]),
                   tray_z_above_table=LAYOUT["tray_root_z"], tray_yaw_deg=LAYOUT["tray_yaw_deg"])


def spawn_hospital(prim_path, cfg, translation=None, orientation=None, **kwargs):
    from isaaclab.sim.spawners.from_files import spawn_from_usd
    from pxr import Usd, UsdPhysics
    prim = spawn_from_usd(prim_path, cfg, translation=translation, orientation=orientation, **kwargs)
    # The imported file contains its own PhysicsScene; use IsaacLab's scene.
    for child in list(Usd.PrimRange(prim)):
        if child.IsA(UsdPhysics.Scene):
            child.SetActive(False)
    # Author semantics before PhysX tensor views are constructed. Runtime API
    # edits to rigid ancestors can invalidate the simulator's cached views.
    from pxr import Semantics
    def label(node, name):
        api = Semantics.SemanticsAPI.Apply(node, 'P4SceneClass')
        api.CreateSemanticTypeAttr().Set('class')
        api.CreateSemanticDataAttr().Set(name)
    label(prim, 'room')
    for child in Usd.PrimRange(prim):
        if child.GetName().startswith('Table_'):
            label(child, 'table')
        elif 'floor' in child.GetName().lower():
            label(child, 'floor')
    from src.recorder.domain_randomization import apply_background
    if LAYOUT.get('cloth_material') == 'new_env_reference_cloth_v1':
        from env.new_environment import apply_cloth_materials
        apply_cloth_materials(prim)
    if LAYOUT.get('display_new_instruments'):
        from env.new_environment import ASSET_DIR
        from pxr import UsdGeom
        display = UsdGeom.Xform.Define(prim.GetStage(), prim.GetPath().AppendChild('NewInstrumentDisplay'))
        display.GetPrim().GetReferences().AddReference(str(ASSET_DIR / 'instruments.usda'))
    apply_background(prim.GetStage(), LAYOUT,
                     dict(color=[0.045, 0.24, 0.13], roughness=0.82), root=prim)
    return prim


def spawn_centered_tray(prim_path, cfg, translation=None, orientation=None, **kwargs):
    from pxr import Usd, UsdGeom
    from isaaclab.sim.spawners.from_files import spawn_from_usd
    asset = Usd.Stage.Open(cfg.usd_path)
    bounds = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render']).ComputeWorldBound(asset.GetDefaultPrim()).ComputeAlignedRange()
    center = bounds.GetMidpoint()
    x, y = float(center[0])*cfg.scale[0], float(center[1])*cfg.scale[1]
    yaw = math.radians(LAYOUT['tray_yaw_deg'])
    c, s = math.cos(yaw), math.sin(yaw)
    # TRAY_FIXED_POS remains the policy's intended XY center. Correct only the
    # visual/physical asset's offset pivot, not the object handler's target.
    t = list(translation)
    t[0] -= c*x-s*y
    t[1] -= s*x+c*y
    print('[P4 TRAY] center=', translation, 'asset root=', t, flush=True)
    prim = spawn_from_usd(prim_path, cfg, translation=tuple(t), orientation=orientation, **kwargs)
    from env.instrument_materials import tune_steel_materials
    tune_steel_materials(prim, minimum_roughness=0.40)
    return prim


def spawn_sensor_safe_light(prim_path, cfg, translation=None, orientation=None, **kwargs):
    from pxr import Sdf
    from isaaclab.sim.spawners.lights import spawn_light
    prim = spawn_light(prim_path, cfg, translation=translation, orientation=orientation, **kwargs)
    # Preserve illumination, but never render the large soft-light emitter as
    # an opaque white/black surface in front of (or surrounding) a camera.
    prim.CreateAttribute('visibleInPrimaryRay', Sdf.ValueTypeNames.Bool).Set(False)
    return prim


def apply_scene(env_cfg):
    # DLSS rendered the old small sensors below output resolution. Preserve
    # actual native samples; higher-res recordings can be downsampled in export.
    # Spatial AA avoids temporal history/ghosting on moving thin instruments.
    # Native 448 supplies real detail; FXAA only smooths edge stair-stepping.
    env_cfg.sim.render.antialiasing_mode = 'FXAA'
    env_cfg.sim.render.enable_dlssg = False
    env_cfg.sim.render.samples_per_pixel = 4
    # Headless and GUI must provide identical physical tray raycast support.
    env_cfg.sim.enable_scene_query_support = True
    # Upstream IK TCP=107 mm but observed EE TCP=103.4 mm. A hold command
    # would move the observed EE by 3.6 mm unless these definitions agree.
    from phase4_feedback import align_control_tcp
    align_control_tcp(env_cfg)
    from isaaclab.assets import AssetBaseCfg
    import isaaclab.sim as sim_utils
    g = table_geometry()
    for name in ("table", "surgical_table_visual", "surgical_table_visual_2",
                 "surgical_table_collision_2", "hospital_room", "operating_bed"):
        setattr(env_cfg.scene, name, None)
    # Hospital's native furniture colliders supply the tabletop. No hidden P3
    # collision table remains underneath the new visual furniture.
    env_cfg.scene.hospital_room = AssetBaseCfg(
        prim_path="{ENV_REGEX_NS}/HospitalRoom",
        spawn=sim_utils.UsdFileCfg(usd_path=str(ROOT/"assets"/LAYOUT["hospital_asset"]),
                                  func=spawn_hospital, scale=(1.,1.,1.)),
        init_state=AssetBaseCfg.InitialStateCfg(pos=g["room_pos"], rot=g["room_rot"]))
    env_cfg.scene.robot.init_state.pos = tuple(LAYOUT["robot_pos"])
    env_cfg.scene.robot.init_state.rot = tuple(LAYOUT["robot_rot_wxyz"])
    for name in ('ground','plane'):
        ground = getattr(env_cfg.scene, name, None)
        if ground is not None and getattr(ground,'spawn',None) is not None:
            ground.spawn.semantic_tags = [('class','floor')]
    yaw = math.radians(LAYOUT["tray_yaw_deg"])
    env_cfg.scene.shared_surgical_tray.init_state.rot = (math.cos(yaw/2),0.,0.,math.sin(yaw/2))
    env_cfg.scene.shared_surgical_tray.spawn.func = spawn_centered_tray
    env_cfg.scene.shared_surgical_tray.spawn.scale = tray_scale_for_layout(env_cfg.scene.shared_surgical_tray.spawn.usd_path)
    for name in ('shared_key_light', 'shared_fill_light'):
        getattr(env_cfg.scene, name).spawn.func = spawn_sensor_safe_light
    # Keep illumination fixed while tuning the steel finishes and woven drape.
    for name, intensity in LAYOUT.get('lighting', {}).items():
        if name not in ('shared_ambient_light','shared_key_light','shared_fill_light'):
            raise ValueError(f'Unsupported P4 light: {name}')
        if not math.isfinite(float(intensity)) or float(intensity) < 0:
            raise ValueError(f'Invalid light intensity: {name}={intensity}')
        getattr(env_cfg.scene, name).spawn.intensity = float(intensity)
    print('[P4 LIGHTING] shared intensities=', LAYOUT.get('lighting', {}),
          'satin steel finishes; textured woven drape active', flush=True)
    # The imported floor is below table Z=0. Keep task ground at that floor.
    if getattr(env_cfg.scene, "ground", None) is not None:
        env_cfg.scene.ground.init_state.pos = (0.,0.,g["room_pos"][2]-0.01)
    if hasattr(env_cfg, "viewer"):
        env_cfg.viewer.eye = (2.4,-2.5,2.0)
        env_cfg.viewer.lookat = (0.2,0.,0.1)
    print("[P4 HOSPITAL]", g)
    print("[P4 LAYOUT] grid=", LAYOUT["grid_x"],LAYOUT["grid_y"],"tray=",LAYOUT["tray_xy"])
    return env_cfg


if __name__ == "__main__":
    print(json.dumps(table_geometry(), indent=2))
