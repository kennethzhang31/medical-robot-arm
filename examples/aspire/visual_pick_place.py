"""Sensor-only starting candidate for ASPIRE refinement. Uses configured RF-DETR.
Box + calibrated depth supplies foreground; SAM3 is an optional backend.
Scissors require visible handle-and-blade depth. Tune on dev seeds.
"""
import math
import numpy as np
home = get_robot_state()
open_gripper()
# Move the empty hand aside so the top view can see the full instrument.
# This waypoint is relative to the measured robot pose, not a target location.
park = np.asarray(home["position"]).copy(); park[1] += .25
goto_pose(park, home["quaternion_wxyz"], duration_s=1.5)
# Associate all four table views instead of requiring front/top visibility.
# Missing detections are allowed; server/network errors still stop the trial.
detections = []
for view in ("front", "top", "left", "right"):
    for detection in segment_instrument(camera=view, allow_empty=True):
        try:
            center = np.median(mask_to_robot_points(detection["mask"], camera=view), axis=0)
        except ValueError:
            continue
        detections.append(dict(camera=view, mask=detection["mask"], center=center, score=detection["score"]))
group, best = [], (0, 0.)
for detection in detections:
    neighbors = [other for other in detections
                 if np.linalg.norm(other["center"][:2]-detection["center"][:2]) < .06]
    views = set(other["camera"] for other in neighbors)
    confidence = sum(max(other["score"] for other in neighbors if other["camera"] == view) for view in views)
    score = (len(views), confidence)
    if score > best:
        group, best = neighbors, score
if best[0] < 2:
    raise RuntimeError("Requested instrument was not confirmed in two independent camera views")
grasp, selected = None, (-1, -1)
for detection in group:
    try:
        candidate = estimate_grasp(detection["mask"], camera=detection["camera"])
    except ValueError:
        continue
    priority = 2 if detection["camera"] == "top" else 1 if detection["camera"] in ("left", "right") else 0
    score = (priority, candidate["point_count"])
    if score > selected:
        grasp, camera, selected = candidate, detection["camera"], score
if grasp is None:
    raise RuntimeError("Confirmed instrument has no complete, direction-resolvable sensor mask")
print("visual_camera", camera, "confirming_views", best[0])
print("visual_grasp", grasp)
pick = np.asarray(grasp["position"])
q = grasp["quaternion_wxyz"]
# Parallel fingers admit an equivalent half-turn; choose the nearer wrist
# orientation while retaining the instrument's directed handle-to-tip axis.
alternative = np.array([-q[3], -q[2], q[1], q[0]])
current_q = np.asarray(get_robot_state()["quaternion_wxyz"])
if abs(float(np.dot(alternative, current_q))) > abs(float(np.dot(q, current_q))):
    q = alternative
hover = pick.copy(); hover[2] += .12
goto_pose(hover, q)
goto_pose(pick, q, duration_s=1.2)
close_gripper()
goto_pose(hover, q, duration_s=1.5)
# The calibrated destination is allowed; target-object poses are never queried.
slot = get_tray_slot()
yaw = math.atan2(slot["long_axis"][1], slot["long_axis"][0])
delta = yaw-grasp["long_axis_yaw"]
# Apply a base-Z rotation to the measured gripper orientation.
c, s = math.cos(delta/2), math.sin(delta/2)
a = np.asarray(get_robot_state()["quaternion_wxyz"])
place_q = np.array([c*a[0]-s*a[3], c*a[1]-s*a[2], c*a[2]+s*a[1], c*a[3]+s*a[0]])
destination = np.asarray(slot["center"])
above = destination.copy(); above[2] = max(hover[2], slot["rim_z"]+.12)
# Avoid crossing the base at low height; refine visual waypoints for distant cells.
goto_pose(above, place_q, duration_s=2., precision="place")
release = destination.copy(); release[2] += .014
goto_pose(release, place_q, duration_s=1.5, precision="place")
open_gripper()
goto_pose(above, place_q, precision="place")
# Clear the tray camera and allow the released body to settle. Home is a
# measured robot pose from this episode, not instrument ground truth.
goto_pose(home["position"], home["quaternion_wxyz"], duration_s=2.)
wait(2.)
