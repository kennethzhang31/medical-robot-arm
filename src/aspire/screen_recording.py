"""Capture Isaac's rendered app window without recording the Windows desktop."""
import hashlib
import math
import time
from pathlib import Path
from .artifacts import write_json


class WindowRecording:
    def __init__(self, directory, app, capture, *, fps=4., clock=time.monotonic):
        if not 1 <= fps <= 10:
            raise ValueError("Window recording FPS must be 1..10")
        self.directory = Path(directory)
        self.frames_directory = self.directory / "screen_frames"
        self.frames_directory.mkdir(exist_ok=False)
        self.capture, self.clock, self.fps = capture, clock, fps
        self.started = clock()
        self.frames = []
        self.errors = []
        self.pending = None
        self.last_capture = -math.inf
        self.metadata = dict(status="recording", scope="Isaac rendered app window only",
            backend="omni.kit.renderer.capture swapchain", fps=fps, audio=False,
            playback="Wall-clock timing with repeated frames during render gaps",
            video="screen.mp4", frames_directory="screen_frames")
        write_json(self.directory / "screen_recording.json", self.metadata)
        self.subscription = app.get_post_update_event_stream().create_subscription_to_pop(
            self.on_update, name="ASPIRE per-trial window recording")

    def on_update(self, event):
        if self.errors:
            return
        now = self.clock()
        if now - self.last_capture < 1. / self.fps:
            return
        if self.pending is not None and not self.pending.exists():
            return
        try:
            path = self.frames_directory / f"{len(self.frames):06d}.png"
            self.capture.capture_next_frame_swapchain(str(path))
            self.frames.append(dict(file=path.name, time_s=now - self.started))
            self.pending, self.last_capture = path, now
        except Exception as error:
            self.errors.append(str(error))

    def close(self):
        ended = self.clock() - self.started
        self.subscription.unsubscribe()
        self.subscription = None
        self.metadata.update(capture_requests=len(self.frames), elapsed_s=ended, errors=self.errors)
        write_json(self.frames_directory / "index.json", self.frames)
        try:
            self.capture.wait_async_capture()
            import cv2
            available = []
            for frame in self.frames:
                path = self.frames_directory / frame["file"]
                if path.is_file() and path.stat().st_size:
                    available.append(frame)
            if self.errors or not available:
                raise RuntimeError("No usable app-window frames" if not self.errors else "; ".join(self.errors))
            image = cv2.imread(str(self.frames_directory / available[0]["file"]))
            if image is None:
                raise RuntimeError("First recorded window frame is unreadable")
            source_height, source_width = image.shape[:2]
            width = max(2, min(source_width, 1280) // 2 * 2)
            height = max(2, round(source_height * width / source_width) // 2 * 2)
            video = self.directory / "screen.mp4"
            writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), self.fps, (width, height))
            if not writer.isOpened():
                writer.release()
                raise RuntimeError("MP4 encoder could not open")
            duration = max(0., ended - available[0]["time_s"])
            frame_count = max(1, math.ceil(duration * self.fps))
            source_index = 0
            try:
                for frame_index in range(frame_count):
                    timestamp = available[0]["time_s"] + frame_index / self.fps
                    while source_index + 1 < len(available) and available[source_index + 1]["time_s"] <= timestamp:
                        source_index += 1
                        image = cv2.imread(str(self.frames_directory / available[source_index]["file"]))
                        if image is None:
                            raise RuntimeError("Recorded window frame is unreadable")
                    writer.write(cv2.resize(image, (width, height)))
            finally:
                writer.release()
            if not video.is_file() or not video.stat().st_size:
                raise RuntimeError("MP4 output is empty")
            decoder = cv2.VideoCapture(str(video))
            try:
                decoded, sample = decoder.read()
            finally:
                decoder.release()
            if not decoded or sample is None:
                raise RuntimeError("MP4 verification could not decode a frame")
            self.metadata.update(status="complete", captured_frames=len(available),
                video_frames=frame_count, duration_s=frame_count / self.fps,
                width=width, height=height, sha256=hashlib.sha256(video.read_bytes()).hexdigest())
        except Exception as error:
            self.metadata.update(status="failed", error=str(error))
        write_json(self.directory / "screen_recording.json", self.metadata)
        return self.metadata


def create_window_recording(directory):
    import omni.kit.app
    app = omni.kit.app.get_app()
    app.get_extension_manager().set_extension_enabled_immediate("omni.kit.renderer.capture", True)
    from omni.kit.renderer.capture import acquire_renderer_capture_interface
    return WindowRecording(directory, app, acquire_renderer_capture_interface())
