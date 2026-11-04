"""RF-DETR transport and sensor geometry, without weights or simulator startup."""
import base64
import io
import json
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from scripts.serve_rfdetr import create_app, encode_results, RfDetrEngine
from src.aspire.geometry import box_depth_mask, mask_to_points
from src.aspire.perception import RfDetrClient


class FakeEngine:
    metadata = dict(backend="rfdetr", output="boxes")

    def detect(self, image):
        detections = SimpleNamespace(xyxy=np.array([[1, 1, 6, 4], [2, 1, 5, 3]]),
                                     class_id=np.array([0, 1]), confidence=np.array([.8, .9]))
        return encode_results(detections, (image.height, image.width))


def payload():
    buffer = io.BytesIO()
    Image.fromarray(np.zeros((5, 7, 3), dtype=np.uint8)).save(buffer, format="PNG")
    return dict(image_base64=base64.b64encode(buffer.getvalue()).decode())


def test_detector_client_roundtrip_preserves_class_mapping_and_source_coordinates(monkeypatch):
    server = TestClient(create_app(FakeEngine()))
    def transport(request, timeout):
        assert request.full_url.endswith("/detect")
        response = server.post("/detect", json=json.loads(request.data))
        assert response.status_code == 200
        return io.BytesIO(json.dumps(response.json()).encode())
    monkeypatch.setattr("src.aspire.perception.urllib.request.urlopen", transport)
    rows = RfDetrClient("http://localhost:8115").detect(np.zeros((5, 7, 3), dtype=np.uint8))
    assert rows[0] == dict(box=[2., 1., 5., 3.], score=.9, label="scissor")
    assert rows[1]["label"] == "scalpel"
    assert server.get("/health").json()["output"] == "boxes"


def test_invalid_image_and_model_failure_are_errors():
    server = TestClient(create_app(FakeEngine()))
    assert server.post("/detect", json=dict(image_base64="bad!")).status_code == 400
    class BrokenEngine(FakeEngine):
        def detect(self, image):
            raise RuntimeError("failed model")
    assert TestClient(create_app(BrokenEngine())).post("/detect", json=payload()).status_code == 500


@pytest.mark.parametrize("class_id", [5, -1, .5])
def test_rejects_wrong_detector_label_space(class_id):
    with pytest.raises(ValueError, match="class ID"):
        encode_results(SimpleNamespace(xyxy=[[0, 0, 2, 2]], class_id=[class_id], confidence=[.8]), (5, 7))


def test_depth_foreground_removes_table_high_objects_and_invalid_depth():
    # Optical camera looks straight down from 1 m above the table.
    transform = np.diag([1., -1., -1., 1.])
    transform[2, 3] = 1.
    depth = np.ones((10, 10))
    depth[3:7, 3:7] = .99
    depth[2, 2] = np.nan
    depth[2, 3] = .8  # Not a table instrument.
    mask = box_depth_mask([1, 1, 9, 9], depth, np.eye(3), transform, 0.)
    assert mask.sum() == 16
    points = mask_to_points(mask, depth, np.eye(3), transform)
    np.testing.assert_allclose(points[:, 2], .01)
    with pytest.raises(ValueError, match="insufficient foreground"):
        box_depth_mask([0, 0, 3, 3], depth, np.eye(3), transform, 0.)
    with pytest.raises(ValueError, match="inside"):
        box_depth_mask([-1, 0, 2, 2], depth, np.eye(3), transform, 0.)


def test_client_rejects_misaligned_image_response(monkeypatch):
    response = dict(contract="p4_rfdetr_detections_v1", shape=[7, 5], results=[])
    monkeypatch.setattr("src.aspire.perception.urllib.request.urlopen",
                        lambda *args, **kwargs: io.BytesIO(json.dumps(response).encode()))
    with pytest.raises(ValueError, match="source image"):
        RfDetrClient("http://localhost:8115").detect(np.zeros((5, 7, 3), dtype=np.uint8))


def test_missing_checkpoint_never_loads_generic_weights(tmp_path):
    with pytest.raises(ValueError, match="existing surgical"):
        RfDetrEngine(tmp_path / "missing.pth", "small", "cpu", .5)
