"""Serve the existing five-class RF-DETR detector outside Isaac Sim."""
import argparse
import base64
import hashlib
import io
import logging
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from PIL import Image
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from training.rfdetr_pipeline import CLASSES, MODELS


class DetectRequest(BaseModel):
    image_base64: str = Field(min_length=1, max_length=12_000_000)


def decode_image(encoded):
    try:
        with Image.open(io.BytesIO(base64.b64decode(encoded, validate=True))) as source:
            if source.width * source.height > 4_000_000:
                raise ValueError("Image exceeds four million pixels")
            return source.convert("RGB")
    except (ValueError, OSError, Image.DecompressionBombError) as error:
        raise HTTPException(400, "Expected a base64 image of at most four million pixels") from error


def encode_results(detections, shape):
    """Fine-tuned Roboflow datasets use contiguous zero-based class IDs."""
    rows = []
    if detections.class_id is None or detections.confidence is None:
        raise ValueError("Detector omitted class IDs or confidence")
    if not len(detections.xyxy) == len(detections.class_id) == len(detections.confidence):
        raise ValueError("Detector returned inconsistent result lengths")
    height, width = shape
    for box, class_id, score in zip(detections.xyxy, detections.class_id, detections.confidence):
        if not np.isfinite(class_id) or int(class_id) != class_id or not 0 <= class_id < len(CLASSES):
            raise ValueError("Unexpected class ID; expected the trained five-class model")
        box = np.asarray(box, dtype=float)
        score = float(score)
        if box.shape != (4,) or not np.isfinite(box).all() or not np.isfinite(score) or not 0 <= score <= 1:
            raise ValueError("Detector returned invalid coordinates or confidence")
        box[[0, 2]] = np.clip(box[[0, 2]], 0, width)
        box[[1, 3]] = np.clip(box[[1, 3]], 0, height)
        if box[0] >= box[2] or box[1] >= box[3]:
            continue
        rows.append(dict(box=box.tolist(), score=score, label=CLASSES[int(class_id)]))
    return dict(contract="p4_rfdetr_detections_v1", shape=list(shape),
                results=sorted(rows, key=lambda row: row["score"], reverse=True))


class RfDetrEngine:
    def __init__(self, checkpoint, variant, device, threshold):
        checkpoint = Path(checkpoint).resolve()
        if not checkpoint.is_file():
            raise ValueError("Pass an existing surgical-instrument checkpoint_best_total.pth")
        import rfdetr
        from importlib.metadata import version
        if version("rfdetr") != "1.11.0":
            raise RuntimeError("Use the repository-pinned rfdetr==1.11.0 environment")
        variants = {name: getattr(rfdetr, "RFDETR" + name.title()) for name in MODELS}
        self.model = variants[variant](pretrain_weights=str(checkpoint), device=device)
        if tuple(self.model.class_names) != CLASSES:
            raise ValueError("Checkpoint class names/order do not match this repo's five instrument classes")
        self.threshold = threshold
        self.lock = threading.Lock()
        with checkpoint.open("rb") as source:
            digest = hashlib.sha256()
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        self.metadata = dict(backend="rfdetr", model=variant, device=device,
                             checkpoint_sha256=digest.hexdigest(), classes=list(CLASSES),
                             threshold=threshold, rfdetr=version("rfdetr"), output="boxes")

    def detect(self, image):
        with self.lock:
            detections = self.model.predict(image, threshold=self.threshold)
        return encode_results(detections, (image.height, image.width))


def create_app(engine):
    app = FastAPI(title="ASPIRE surgical RF-DETR")

    @app.get("/health")
    def health():
        return dict(ready=True, **engine.metadata)

    @app.post("/detect")
    def detect(request: DetectRequest):
        image = decode_image(request.image_base64)
        try:
            return engine.detect(image)
        except Exception as error:
            logging.exception("RF-DETR inference failed")
            raise HTTPException(500, "RF-DETR inference failed; inspect the server terminal") from error

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--model", choices=MODELS, default="small")
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--threshold", type=float, default=.5)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8115)
    args = parser.parse_args()
    if not np.isfinite(args.threshold) or not 0 <= args.threshold <= 1:
        parser.error("--threshold must be between zero and one")
    logging.basicConfig(level=logging.INFO)
    import uvicorn
    engine = RfDetrEngine(args.checkpoint, args.model, args.device, args.threshold)
    uvicorn.run(create_app(engine), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
