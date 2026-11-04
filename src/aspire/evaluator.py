"""Private, stage-independent task verification. Never a policy observation."""
from dataclasses import dataclass
import numpy as np
from .geometry import relative_point


@dataclass
class Measurement:
    tcp_w: np.ndarray
    tcp_quaternion_wxyz: np.ndarray
    target_center_w: np.ndarray
    target_bottom_w: float
    finger_positions: np.ndarray
    slot: dict
    support_z: float
    preloaded_ok: bool = True
    target_speed: float = 0.


class TaskEvaluator:
    """Track lift, hold, release and supported placement from measured state."""
    def reset(self, measurement):
        self.initial_center = np.asarray(measurement.target_center_w).copy()
        self.phase = "ready"
        self.lift_verified = False
        self.place_verified = False
        self.reason = "not_lifted"
        self.anchor = None
        self.release_tcp = None
        self.release_center = None
        self.centers = []
        self.slip_samples = 0
        self.steps = 0

    @property
    def failed(self):
        return self.phase == "failure"

    def fail(self, reason):
        self.phase, self.reason, self.place_verified = "failure", reason, False

    def update(self, m, grip_command):
        self.steps += 1
        values = np.r_[m.tcp_w, m.tcp_quaternion_wxyz, m.target_center_w,
                       m.target_bottom_w, m.finger_positions, m.support_z, m.target_speed]
        slot_values = [m.slot.get(key, float("nan")) for key in ("center_error_m", "axis_error_deg", "bottom_m")]
        if not np.isfinite(values).all() or not np.isfinite(slot_values).all():
            self.fail("nonfinite_measured_state")
        elif m.target_bottom_w < -.02:
            self.fail("target_fell_off_table")
        elif not m.preloaded_ok:
            self.fail("preloaded_instrument_displaced")
        if self.failed or self.place_verified:
            return
        anchor = relative_point(m.target_center_w, m.tcp_w, m.tcp_quaternion_wxyz)
        rise = m.target_center_w[2] - self.initial_center[2]
        if self.phase == "ready" and grip_command < 0 and rise >= .035 and m.target_bottom_w >= .025 and np.linalg.norm(anchor) < .12:
            self.lift_verified = True
            self.phase, self.anchor, self.reason = "held", anchor, "not_released"
        if self.phase == "held":
            shift = float(np.linalg.norm(anchor - self.anchor))
            self.slip_samples = self.slip_samples + 1 if shift > .025 else 0
            if self.slip_samples >= 2:
                self.fail("target_slipped_during_transport")
                return
            if grip_command > 0:
                self.phase, self.reason = "released", "placement_not_verified"
                self.release_tcp = np.asarray(m.tcp_w).copy()
                self.release_center = np.asarray(m.target_center_w).copy()
        if self.phase == "released":
            self.centers.append(np.asarray(m.target_center_w).copy())
            self.centers = self.centers[-6:]
            retreat = m.tcp_w[2] - self.release_tcp[2]
            if retreat >= .045 and m.target_center_w[2] - self.release_center[2] >= .025:
                self.fail("target_still_attached_after_open")
                return
            stable = len(self.centers) == 6 and np.ptp(self.centers, axis=0).max() < .002 and m.target_speed < .003
            supported = abs(m.target_bottom_w-m.support_z) <= .005
            aligned = m.slot["inside_slot"] and m.slot["center_error_m"] <= .008 and m.slot["axis_error_deg"] <= 8.
            open_fingers = float(np.sum(m.finger_positions)) >= .06
            if stable and supported and aligned and open_fingers and retreat >= .045:
                self.phase, self.reason, self.place_verified = "success", "verified_pick_place", True

    def feedback(self):
        """Outcome feedback without object coordinates, mesh data or spawn state."""
        return {"phase": self.phase, "reason": self.reason,
                "lift_verified": self.lift_verified, "place_verified": self.place_verified,
                "measured_steps": self.steps}
