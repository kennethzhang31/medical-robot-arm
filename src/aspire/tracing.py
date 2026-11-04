"""Adapt upstream ASPIRE tracing to the surgical sensor/API schema."""
import time
from functools import wraps
from .control import SurgicalControlApi
from aspire.sim.cap.integrations.trace_logger import TraceLogger


class SurgicalTraceLogger(TraceLogger):
    def capture(self, name, when):
        from PIL import Image
        obs = self._env.get_observation()
        step = len(self.entries) if when == 'before' else self.entries[-1]['step']
        files = []
        for camera in ('top', 'front', 'wrist'):
            filename = f'step_{step:03d}_{name}_{when}_{camera}.jpg'
            self._buffered_keyframes.append((filename, Image.fromarray(obs['cameras'][camera]['images']['rgb'])))
            files.append('keyframes/'+filename)
        return files

    def log_call(self, name, args, kwargs, result, duration_ms, error=None):
        logged_name, logged_args, logged_result = name, args, result
        if name == 'get_observation' and isinstance(result, dict):
            cameras = result['cameras']
            logged_result = dict(robot0_robotview=cameras['front'],
                                 robot0_eye_in_hand=cameras['wrist'],
                                 agentview=cameras['top'], robot_state=result['robot'])
        if name in ('segment_instrument', 'get_tabletop_candidates'):
            logged_name = 'segment_sam3_text_prompt'
            camera = kwargs.get('camera', 'top')
            rgb = self._env.get_observation()['cameras'][camera]['images']['rgb']
            visual = name == 'get_tabletop_candidates' or kwargs.get('box') is not None
            logged_args = (rgb, 'class-agnostic visual region' if visual else kwargs.get('text', self._env.config.target))
        super().log_call(logged_name, logged_args, kwargs, logged_result, duration_ms, error)
        entry = self.entries[-1]
        entry['function'] = name
        if name == 'get_tabletop_candidates' and result is not None:
            entry['perception_mode'] = 'depth_components'
            entry['candidates'] = [{key: row[key] for key in ('box', 'point_count', 'center', 'extent_xy')}
                                   for row in result]
        elif name == 'segment_instrument' and kwargs.get('box') is not None:
            entry['perception_mode'] = 'visual_box'
        entry['sim_step'] = self._env._sim_step_count
        if name in ('get_robot_state', 'goto_pose', 'open_gripper', 'close_gripper') and result is not None:
            entry['result'] = result
        entry['after_images'] = self.capture(name, 'after')
        entry['keyframe_saved'] = True


class TracedSurgicalControlApi(SurgicalControlApi):
    def __init__(self, env):
        super().__init__(env)
        self.trace = SurgicalTraceLogger()
        self.trace.set_env(env)

    def functions(self):
        def wrap(name, fn):
            @wraps(fn)
            def traced(*args, **kwargs):
                started, result, error = time.perf_counter(), None, None
                before = self.trace.capture(name, 'before')
                try:
                    result = fn(*args, **kwargs)
                    return result
                except Exception as exc:
                    error = f'{type(exc).__name__}: {exc}'
                    raise
                finally:
                    self.trace.log_call(name, args, kwargs, result,
                                        (time.perf_counter()-started)*1000, error)
                    self.trace.entries[-1]['before_images'] = before
                    if self._env._sink:
                        self.trace.save(self._env._sink.directory)
            return traced
        return {name: wrap(name, fn) for name, fn in super().functions().items()}
