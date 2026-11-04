# Mirror hand on the UR5

`mirror_hand_1013/mirror_hand_1013.usd` is the supplied five-finger hand.
It includes its geometry, ten driven joints, ten passive tree coordinates and
five passive four-bar closures. The supplied URDF cannot be used alone because
its `meshes/` directory was not included.

Run the replacement-hand preview in the current hospital scene:

```powershell
& C:/isaac-sim-450/python.bat scripts/preview_mirror_hand.py --device cpu
```

The main green work mat contains the five working instruments (scalpel,
scissors, Love retractor, Kelly clamp and type-2 scalpel) at the last hospital
preview's logged XY positions and yaw, saved in `env/mirror_hand_tool_layout.json`.
The recorder's seeded clutter placement adds the nine extra instrument copies;
their exact earlier settled poses were not saved. The surgical
tray is at its configured table location. These are dynamic bodies using the
recorder's assets and steel finishes. The camera shows the workspace and tray.
Instruments retain their original meshes, mesh normals and collision geometry.
Steel adjustments apply only to material shader inputs. The preview uses its
normal real-time renderer.
Love retractors, including clutter copies, bind the material exported directly
from the existing Blender steel study in `assets/blender_retractor_material/`.
Python steel overrides are bypassed for this material.

For a repeatable headless check:

```powershell
& C:/isaac-sim-450/python.bat scripts/preview_mirror_hand.py --headless --device cpu --frames 600
```

The preview loads the bare UR5, adds a 4 mm wrist adapter, and attaches the new
palm with a fixed joint.
The hand's world joint and articulation root are removed from the composed
scene, so the arm and hand form one articulation. The ten active joints receive
position targets; the distal and linkage joints remain passive. Source assets
are referenced and never saved over.

Outputs go to `exports/ur5_mirror_hand/`: `mounted_hand.usda`, `overview.png`,
`hand_closeup.png` and `smoke_test.json`. The scene references the source hand
and NVIDIA's classic UR5 asset, so it requires those assets to remain available.
Use `--standalone` for an empty scene without the hospital, tools or tray.

`env/mirror_hand.py:create_robot_cfg` creates the UR5 and hand `ArticulationCfg`.
It uses `Robots/UniversalRobots/ur5/ur5.usd`, with the six UR5 arm joints and
`wrist_3_link` as the tool flange. The smoke check exercises 0-10 degree flexion and +/-3 degree
abduction, checks all five closure gaps, and measures the palm attachment.
It uses the supplied provisional 0.25 Nm effort and 0.3/0.01 hand drive gains.
The wrist's original geometry and inertia are preserved; a separate 15 g
adapter body carries the hand. The combined articulation has 26 moving joint
coordinates: six arm joints and twenty hand tree coordinates, of which ten
are actively driven.

This preview uses UR5 plus the mirror hand. The existing recording and ASPIRE
tasks still instantiate the Franka two-jaw configuration. Their robot config,
joint mapping, jaw-width observations, grasp poses, collision clearance,
TCP and success checks need hand-specific calibration before collecting new
demonstrations. The 20 mm palm offset, 180 degree X rotation and adapter are a
simulation mount, not a calibrated hardware adapter. Full travel, loaded grasps
and instrument contact have not been validated. Some CAD colliders fall back to
CPU cooking in Isaac Sim 4.5; the verified preview uses CPU physics.
