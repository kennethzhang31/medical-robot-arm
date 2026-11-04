"""Lightweight client for the pinned ASPIRE SAM3 wire protocol."""
import base64
import io
import json
import urllib.request
import numpy as np
from PIL import Image
from .config import INSTRUMENTS


def check_perception_service(config):
    """Verify the selected detector before spending on program generation."""
    url = config.rfdetr_url if config.perception_backend == 'rfdetr' else config.sam3_url
    if not url:
        raise RuntimeError('The selected perception backend requires a service URL')
    with urllib.request.urlopen(url.rstrip('/')+'/health', timeout=5) as response:
        health = json.load(response)
    if health.get('ready') is not True:
        raise RuntimeError('The selected perception service is not ready')
    if config.perception_backend == 'rfdetr':
        if (health.get('backend') != 'rfdetr' or tuple(health.get('classes', [])) != INSTRUMENTS
                or health.get('output') != 'boxes' or health.get('rfdetr') != '1.11.0'):
            raise RuntimeError('RF-DETR service must use the pinned five-class surgical detector')
        checkpoint = health.get('checkpoint_sha256', '')
        if len(checkpoint) != 64 or any(c not in '0123456789abcdef' for c in checkpoint):
            raise RuntimeError('RF-DETR service must identify its trained checkpoint SHA256')
    return health


class RfDetrClient:
    """Box-only detector transport; no SAM3 or model dependencies in Isaac Sim."""
    def __init__(self, url, timeout=30.):
        self.url, self.timeout = url.rstrip("/"), timeout
        if not self.url.startswith(("http://", "https://")):
            raise ValueError("rfdetr_url must be an HTTP(S) service URL")

    def detect(self, rgb):
        rgb = np.asarray(rgb)
        if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8:
            raise ValueError("RF-DETR needs uint8 RGB")
        buffer = io.BytesIO()
        Image.fromarray(rgb).save(buffer, format="PNG")
        payload = {"image_base64": base64.b64encode(buffer.getvalue()).decode("ascii")}
        request = urllib.request.Request(self.url + "/detect", json.dumps(payload).encode(),
                                         {"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            data = json.load(response)
        if data.get("contract") != "p4_rfdetr_detections_v1" or data.get("shape") != list(rgb.shape[:2]):
            raise ValueError("RF-DETR response must match the source image and detector contract")
        results = []
        for row in data["results"]:
            box = np.asarray(row["box"], dtype=float)
            score = float(row["score"])
            if (box.shape != (4,) or not np.isfinite(box).all() or
                    not 0 <= box[0] < box[2] <= rgb.shape[1] or
                    not 0 <= box[1] < box[3] <= rgb.shape[0] or
                    not np.isfinite(score) or not 0 <= score <= 1 or row["label"] not in INSTRUMENTS):
                raise ValueError("Malformed RF-DETR box, label or score")
            results.append(dict(box=box.tolist(), score=score, label=row["label"]))
        return sorted(results, key=lambda row: row["score"], reverse=True)


class Sam3Client:
    def __init__(self, url, timeout=30.):
        self.url, self.timeout = url.rstrip("/"), timeout
        if not self.url.startswith(("http://", "https://")):
            raise ValueError("sam3_url must be an HTTP(S) service URL")

    def segment(self, rgb, text=None, *, point=None, box=None, allow_empty=False):
        rgb = np.asarray(rgb)
        if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8:
            raise ValueError("SAM3 needs uint8 RGB")
        buffer = io.BytesIO()
        Image.fromarray(rgb).save(buffer, format="PNG")
        payload = {"image_base64": base64.b64encode(buffer.getvalue()).decode("ascii")}
        if point is not None and box is not None:
            raise ValueError("Choose either a box or a point prompt")
        if box is not None:
            coordinates = np.asarray(box, dtype=float)
            if (coordinates.shape != (4,) or not np.isfinite(coordinates).all() or
                    not 0 <= coordinates[0] < coordinates[2] <= rgb.shape[1] or
                    not 0 <= coordinates[1] < coordinates[3] <= rgb.shape[0]):
                raise ValueError("Box must be finite in-image XYXY coordinates")
            endpoint = "/segment_box"
            payload["box"] = coordinates.tolist()
        elif point is None:
            endpoint = "/segment"
            payload["text_prompt"] = text
        else:
            endpoint = "/segment_point"
            if len(point) != 2 or not all(np.isfinite(point)) or not (0 <= point[0] < rgb.shape[1] and 0 <= point[1] < rgb.shape[0]):
                raise ValueError("Point must be an in-image (x,y) pixel")
            payload["point_coords"] = list(point)
        request = urllib.request.Request(self.url + endpoint, json.dumps(payload).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            data = json.load(response)
        results = []
        if point is None:
            for row in data["results"]:
                mask = np.frombuffer(base64.b64decode(row["mask_base64"]), dtype=np.uint8).reshape(row["shape"]).astype(bool)
                results.append({"mask": mask, "box": row["box"], "score": float(row["score"]), "label": row["label"]})
        else:
            masks = np.frombuffer(base64.b64decode(data["masks_base64"]), dtype=np.dtype(data["masks_dtype"])).reshape(data["masks_shape"])
            results = [{"mask": mask.astype(bool), "score": float(score)} for mask, score in zip(masks, data["scores"])]
        for row in results:
            if row["mask"].shape != rgb.shape[:2] or not np.isfinite(row["score"]):
                raise ValueError("Malformed SAM3 mask/score")
        if not results and not allow_empty:
            raise RuntimeError("SAM3 returned no target candidates")
        return sorted(results, key=lambda row: row["score"], reverse=True)
