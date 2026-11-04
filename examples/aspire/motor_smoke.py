"""Exercise reset sensors, encoder gates and measured-pose convergence.
This is an integration check; it deliberately does not claim pick/place success.
"""
import numpy as np
observation = get_observation()
assert set(observation["cameras"]) == {"front", "wrist", "top", "left", "right", "tray"}
assert observation["proprio"].shape == (16,)
open_gripper()
state = get_robot_state()
position = np.asarray(state["position"]).copy()
position[2] += .015
goto_pose(position, state["quaternion_wxyz"], duration_s=.4)
close_gripper()
open_gripper()
wait(.2)
print("Sensor and motor smoke test completed", get_robot_state()["position"])
