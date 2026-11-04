"""Window recorder tests without launching Kit or capturing the desktop."""
from types import SimpleNamespace
import numpy as np
import pytest
from PIL import Image
from src.aspire.screen_recording import WindowRecording


def fake_recording(tmp_path):
    clock = [0.]
    subscription = SimpleNamespace(unsubscribe=lambda: None)
    stream = SimpleNamespace(create_subscription_to_pop=lambda callback, **kwargs: subscription)
    app = SimpleNamespace(get_post_update_event_stream=lambda: stream)
    paths = []
    capture = SimpleNamespace(capture_next_frame_swapchain=lambda path: paths.append(path),
                              wait_async_capture=lambda: None)
    return WindowRecording(tmp_path, app, capture, clock=lambda: clock[0]), clock, paths


def test_recording_throttles_and_never_queues_over_pending_frame(tmp_path):
    recording, clock, paths = fake_recording(tmp_path)
    recording.on_update(None)
    clock[0] = 1.
    recording.on_update(None)
    assert len(paths) == 1
    Image.new("RGB", (64, 48), "red").save(paths[0])
    recording.on_update(None)
    assert len(paths) == 2
    recording.on_update(None)
    assert len(paths) == 2


def test_recording_saves_decodable_mp4_and_preserves_wall_time(tmp_path):
    pytest.importorskip("cv2")
    recording, clock, paths = fake_recording(tmp_path)
    recording.on_update(None)
    Image.fromarray(np.full((48, 64, 3), 80, dtype=np.uint8)).save(paths[0])
    clock[0] = 1.
    recording.on_update(None)
    Image.new("RGB", (64, 48), "blue").save(paths[1])
    clock[0] = 2.
    result = recording.close()
    assert result["status"] == "complete" and result["captured_frames"] == 2
    assert result["video_frames"] == 8 and result["duration_s"] == 2.
    assert result["scope"] == "Isaac rendered app window only" and not result["audio"]
    assert (tmp_path / "screen.mp4").stat().st_size > 0
    assert len(result["sha256"]) == 64


def test_recording_no_frames_preserves_failure_metadata(tmp_path):
    recording, clock, paths = fake_recording(tmp_path)
    result = recording.close()
    assert result["status"] == "failed" and result["capture_requests"] == 0
    assert "No usable" in result["error"] and not paths
