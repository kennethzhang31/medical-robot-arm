"""Sensor geometry only: optical camera frame -> robot-base frame."""
import math
import numpy as np


def vector(value, size, name):
    result = np.asarray(value, dtype=np.float64)
    if result.shape != (size,) or not np.isfinite(result).all():
        raise ValueError(f"{name} must have {size} finite values")
    return result.copy()


def unit_quaternion(value):
    q = vector(value, 4, "WXYZ quaternion")
    norm = np.linalg.norm(q)
    if norm < 1e-8:
        raise ValueError("Zero quaternion")
    return q / norm


def rotate(q, points):
    q = unit_quaternion(q)
    points = np.asarray(points, dtype=np.float64)
    cross = 2 * np.cross(q[1:], points)
    return points + q[0] * cross + np.cross(q[1:], cross)


def quat_matrix(q):
    return rotate(q, np.eye(3)).T


def relative_point(position, origin, orientation):
    inverse = unit_quaternion(orientation)
    inverse[1:] *= -1
    return rotate(inverse, np.asarray(position) - origin)


def quaternion_multiply(a, b):
    a, b = unit_quaternion(a), unit_quaternion(b)
    return np.r_[a[0]*b[0]-np.dot(a[1:], b[1:]),
                 a[0]*b[1:]+b[0]*a[1:]+np.cross(a[1:], b[1:])]


def interpolate_quaternion(a, b, fraction):
    a, b = unit_quaternion(a), unit_quaternion(b)
    dot = float(np.dot(a, b))
    if dot < 0:
        b, dot = -b, -dot
    if dot > .9995:
        return unit_quaternion(a + fraction * (b-a))
    angle = math.acos(np.clip(dot, -1., 1.))
    return (math.sin((1-fraction)*angle)*a + math.sin(fraction*angle)*b) / math.sin(angle)


def orientation_error(a, b):
    return 2 * math.acos(min(1., abs(float(np.dot(unit_quaternion(a), unit_quaternion(b))))))


def topdown_quaternion(long_axis_yaw):
    """Panda TCP points down; the finger closing axis crosses the long axis."""
    # The Panda fingers close along hand-local Y. The P4 reference quaternion
    # maps that axis to base X, so a measured long-axis yaw needs a 90-degree
    # offset to make the fingers close across the instrument.
    angle = long_axis_yaw-math.pi/2
    yaw = [math.cos(angle/2), 0., 0., math.sin(angle/2)]
    return quaternion_multiply(yaw, [0., math.sqrt(.5), math.sqrt(.5), 0.])


def mask_to_points(mask, depth, intrinsics, camera_to_base):
    depth = np.asarray(depth, dtype=np.float64)
    if depth.ndim == 3 and depth.shape[-1] == 1:
        depth = depth[..., 0]
    mask = np.asarray(mask, dtype=bool)
    if mask.shape != depth.shape or depth.ndim != 2:
        raise ValueError("Mask and metric image-plane depth must be matching HxW arrays")
    k = np.asarray(intrinsics, dtype=float)
    transform = np.asarray(camera_to_base, dtype=float)
    if k.shape != (3, 3) or transform.shape != (4, 4) or not np.isfinite(k).all() or not np.isfinite(transform).all():
        raise ValueError("Invalid camera calibration")
    if k[0, 0] <= 0 or k[1, 1] <= 0:
        raise ValueError("Camera focal lengths must be positive")
    v, u = np.where(mask & np.isfinite(depth) & (depth > .001) & (depth < 3.))
    if len(u) < 8:
        raise ValueError("Insufficient valid depth pixels in target mask")
    pixels = np.column_stack((u, v, np.ones(len(u))))
    points = (pixels @ np.linalg.inv(k).T) * depth[v, u, None]
    return (np.column_stack((points, np.ones(len(points)))) @ transform.T)[:, :3]


def box_depth_mask(box, depth, intrinsics, camera_to_base, table_z_base):
    """Depth foreground inside a detector XYXY box, not a learned pixel mask.

    Reject intersecting detections before calling: nearby objects inside the
    same box cannot reliably be separated by their height above the table.
    """
    depth = np.asarray(depth, dtype=float)
    if depth.ndim == 3 and depth.shape[-1] == 1:
        depth = depth[..., 0]
    if depth.ndim != 2 or not math.isfinite(table_z_base):
        raise ValueError("Need metric HxW depth and finite table calibration")
    x1, y1, x2, y2 = vector(box, 4, "XYXY box")
    height, width = depth.shape
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        raise ValueError("Detector box must be inside the source image")
    region = np.zeros(depth.shape, dtype=bool)
    region[math.floor(y1):math.ceil(y2), math.floor(x1):math.ceil(x2)] = True
    valid = region & np.isfinite(depth) & (depth > .001) & (depth < 3.)
    points = mask_to_points(valid, depth, intrinsics, camera_to_base)
    foreground = (points[:, 2] > table_z_base + .0005) & (points[:, 2] < table_z_base + .045)
    mask = np.zeros(depth.shape, dtype=bool)
    v, u = np.where(valid)
    mask[v[foreground], u[foreground]] = True
    if np.count_nonzero(mask) < 8:
        raise ValueError("Detector box has insufficient foreground depth above the table")
    return mask


def tabletop_candidates(depth, intrinsics, camera_to_base, table_z_base, *, min_points=12, max_candidates=16):
    """Class-agnostic RGB-D foreground components with no simulator identity."""
    if type(min_points) is not int or min_points < 8:
        raise ValueError("min_points must be an integer of at least eight")
    if type(max_candidates) is not int or not 1 <= max_candidates <= 64:
        raise ValueError("max_candidates must be an integer from 1 to 64")
    depth = np.asarray(depth, dtype=float)
    if depth.ndim == 3 and depth.shape[-1] == 1:
        depth = depth[..., 0]
    if depth.ndim != 2 or not math.isfinite(table_z_base):
        raise ValueError("Need metric HxW depth and finite table calibration")
    valid = np.isfinite(depth) & (depth > .001) & (depth < 3.)
    if valid.sum() < 8:
        return []
    points = mask_to_points(valid, depth, intrinsics, camera_to_base)
    foreground = (points[:, 2] > table_z_base + .0005) & (points[:, 2] < table_z_base + .045)
    height, width = depth.shape
    cloud = np.full((height, width, 3), np.nan)
    cloud[valid] = points
    mask = np.zeros(depth.shape, dtype=bool)
    mask[valid] = foreground
    # Bridge up to two missing pixels when proposing regions; retain only real depth samples.
    padded = np.pad(mask, 1)
    expanded = np.zeros_like(mask)
    for dy in range(3):
        for dx in range(3):
            expanded |= padded[dy:dy+height, dx:dx+width]
    visited = np.zeros_like(mask)
    candidates = []
    for sy, sx in zip(*np.where(expanded)):
        if visited[sy, sx]:
            continue
        stack, pixels = [(int(sy), int(sx))], []
        visited[sy, sx] = True
        while stack:
            y, x = stack.pop()
            if mask[y, x]:
                pixels.append((y, x))
            for ny, nx in ((y-1, x), (y+1, x), (y, x-1), (y, x+1)):
                if 0 <= ny < height and 0 <= nx < width and expanded[ny, nx] and not visited[ny, nx]:
                    visited[ny, nx] = True
                    stack.append((ny, nx))
        if len(pixels) < min_points:
            continue
        ys, xs = np.asarray(pixels).T
        region = np.zeros_like(mask)
        region[ys, xs] = True
        values = cloud[ys, xs]
        extent = np.ptp(values[:, :2], axis=0)
        if not .015 < np.linalg.norm(extent) < .30:
            continue
        candidates.append(dict(box=[max(0, int(xs.min())-3), max(0, int(ys.min())-3),
                                    min(width, int(xs.max())+4), min(height, int(ys.max())+4)],
                               mask=region, point_count=len(pixels), center=np.median(values, axis=0),
                               extent_xy=extent, mask_source='depth_component'))
    return sorted(candidates, key=lambda row: -row['point_count'])[:max_candidates]


def estimate_topdown_grasp(points, table_z_base, *, ring_handles=False):
    """Return a starting grasp candidate from a segmented sensor point cloud.

    PCA supplies an axis, not a guarantee of a graspable handle. Skills can
    choose a subset of their mask for scissors/retractors or refine this pose.
    """
    points = np.asarray(points, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all() or len(points) < 8:
        raise ValueError("Need at least eight finite 3D points")
    points = points[(points[:, 2] > table_z_base + .0005) & (points[:, 2] < table_z_base + .045)]
    if len(points) < 8:
        raise ValueError("Target mask has too few points above the calibrated table")
    center = np.median(points, axis=0)
    covariance = np.cov(points[:, :2], rowvar=False)
    values, axes = np.linalg.eigh(covariance)
    if values[-1] < 1e-8:
        raise ValueError("Degenerate grasp point cloud")
    axis = axes[:, -1]
    if ring_handles:
        # Scissors have a broad ring-handle end and a narrower blade tip.
        # Resolve the PCA sign using visible shape, never an object pose.
        across = np.array([-axis[1], axis[0]])
        along = points[:, :2] @ axis
        lateral = points[:, :2] @ across
        low, high = float(along.min()), float(along.max())
        span = high-low
        if span < .04:
            raise ValueError("Scissor mask does not show enough length to resolve its direction")
        low_end = lateral[along <= low+.3*span]
        high_end = lateral[along >= high-.3*span]
        if min(len(low_end), len(high_end)) < 3:
            raise ValueError("Scissor mask must show both handle and blade ends")
        low_width, high_width = float(np.ptp(low_end)), float(np.ptp(high_end))
        if abs(low_width-high_width) < .002:
            raise ValueError("Scissor handle direction is ambiguous in this sensor mask")
        center[:2] = axis*((low+high)/2) + across*((lateral.min()+lateral.max())/2)
        if high_width > low_width:
            axis = -axis
    yaw = math.atan2(axis[1], axis[0])
    center[2] = max(table_z_base + .005, min(table_z_base + .015, float(center[2])))
    return {"position": center, "quaternion_wxyz": topdown_quaternion(yaw),
            "long_axis_yaw": yaw, "point_count": len(points)}
