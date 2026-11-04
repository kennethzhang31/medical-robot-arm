"""Wire-contract tests without downloading weights or starting a GPU model."""
import base64
import io
import json
import pytest
import numpy as np
from PIL import Image
from fastapi.testclient import TestClient
from scripts.serve_sam3_windows import create_app, encode_results


class FakeEngine:
    metadata = {"device": "fake", "point_prompts": False}

    def segment(self, image, text, *, box=None):
        mask = np.zeros((image.height, image.width), dtype=np.uint8)
        mask[1:3, 2:4] = 1
        return encode_results(dict(masks=[mask], boxes=[[2, 1, 4, 3]], scores=[0.9]),
                              text or "visual", mask.shape)


def image_payload():
    buffer = io.BytesIO()
    Image.fromarray(np.zeros((5, 7, 3), dtype=np.uint8)).save(buffer, format="PNG")
    return dict(image_base64=base64.b64encode(buffer.getvalue()).decode(), text_prompt="scissors")


def test_roundtrip_source_resolution_mask():
    client = TestClient(create_app(FakeEngine()))
    response = client.post("/segment", json=image_payload())
    assert response.status_code == 200
    row = response.json()["results"][0]
    mask = np.frombuffer(base64.b64decode(row["mask_base64"]), dtype=np.uint8).reshape(row["shape"])
    assert mask.shape == (5, 7) and mask.sum() == 4 and mask[1, 2] == 1
    assert row["label"] == "scissors" and row["box"] == [2, 1, 4, 3]
    assert client.get("/health").json()["ready"] is True


def test_invalid_image_and_unsupported_point_are_explicit():
    client = TestClient(create_app(FakeEngine()))
    assert client.post("/segment", json=dict(image_base64="bad!", text_prompt="scissor")).status_code == 400
    assert client.post("/segment_point", json={}).status_code == 501


def test_inference_failure_is_not_an_empty_success():
    class BrokenEngine(FakeEngine):
        def segment(self, image, text):
            raise RuntimeError("failed model")
    response = TestClient(create_app(BrokenEngine())).post("/segment", json=image_payload())
    assert response.status_code == 500


def test_client_empty_detection_can_trigger_camera_fallback(monkeypatch):
    from src.aspire.perception import Sam3Client
    class EmptyEngine(FakeEngine):
        def segment(self, image, text):
            return {"results": []}
    server = TestClient(create_app(EmptyEngine()))
    def transport(request, timeout):
        response = server.post("/segment", json=json.loads(request.data))
        return io.BytesIO(json.dumps(response.json()).encode())
    monkeypatch.setattr("src.aspire.perception.urllib.request.urlopen", transport)
    client = Sam3Client("http://127.0.0.1:8114")
    rgb = np.zeros((5, 7, 3), dtype=np.uint8)
    with pytest.raises(RuntimeError, match="no target candidates"):
        client.segment(rgb, "scissor")
    assert client.segment(rgb, "scissor", allow_empty=True) == []


def test_visual_box_roundtrip_omits_target_text(monkeypatch):
    from src.aspire.perception import Sam3Client
    calls = []

    class BoxEngine(FakeEngine):
        def segment(self, image, text, *, box=None):
            calls.append((text, box))
            return super().segment(image, text, box=box)

    server = TestClient(create_app(BoxEngine()))

    def transport(request, timeout):
        assert request.full_url.endswith('/segment_box')
        payload = json.loads(request.data)
        assert 'text_prompt' not in payload
        response = server.post('/segment_box', json=payload)
        assert response.status_code == 200
        return io.BytesIO(json.dumps(response.json()).encode())

    monkeypatch.setattr('src.aspire.perception.urllib.request.urlopen', transport)
    result = Sam3Client('http://localhost:8114').segment(
        np.zeros((5, 7, 3), dtype=np.uint8), box=[1, 0, 5, 4])
    assert calls == [(None, [1., 0., 5., 4.])]
    assert result[0]['label'] == 'visual'
    assert result[0]['mask'].shape == (5, 7)


@pytest.mark.parametrize('box', [[-1, 0, 3, 4], [0, 0, 8, 4], [3, 0, 2, 4], [0, 0, 2, 6]])
def test_box_bounds_rejected_by_client_and_server(box):
    from src.aspire.perception import Sam3Client
    client = Sam3Client('http://localhost:8114')
    with pytest.raises(ValueError, match='XYXY'):
        client.segment(np.zeros((5, 7, 3), dtype=np.uint8), box=box)
    payload = image_payload()
    payload.pop('text_prompt')
    payload['box'] = box
    assert TestClient(create_app(FakeEngine())).post('/segment_box', json=payload).status_code == 400


def test_box_failure_is_not_returned_as_an_empty_detection():
    class BrokenEngine(FakeEngine):
        def segment(self, image, text, *, box=None):
            raise RuntimeError('inference failed')
    payload = image_payload()
    payload.pop('text_prompt')
    payload['box'] = [1, 0, 5, 4]
    assert TestClient(create_app(BrokenEngine())).post('/segment_box', json=payload).status_code == 500


def test_depth_components_separate_tools_and_reject_table_and_missing_depth():
    from src.aspire.geometry import tabletop_candidates
    depth = np.ones((100, 100))
    depth[20:25, 10:35] = .99
    depth[65:70, 55:85] = .99
    depth[0:4, :] = np.nan
    depth[80:90, :8] = 0
    intrinsics = np.array([[200., 0, 50], [0, 200., 50], [0, 0, 1]])
    pose = np.diag([1., -1., -1., 1.])
    pose[2, 3] = 1.
    candidates = tabletop_candidates(depth, intrinsics, pose, 0.)
    assert len(candidates) == 2
    assert sorted(row['point_count'] for row in candidates) == [125, 150]
    assert all(np.allclose(row['center'][2], .01) for row in candidates)
    assert not np.any(candidates[0]['mask'] & candidates[1]['mask'])
    assert tabletop_candidates(np.ones((100, 100)), intrinsics, pose, 0.) == []
    assert tabletop_candidates(np.full((100, 100), np.nan), intrinsics, pose, 0.) == []
    depth[20:25, 22] = 1.
    fragmented = tabletop_candidates(depth, intrinsics, pose, 0.)
    assert len(fragmented) == 2
    assert sorted(row['point_count'] for row in fragmented) == [120, 150]
    assert not any(row['mask'][20:25, 22].any() for row in fragmented)
