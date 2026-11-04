"""Native Windows SAM3 text/visual-box segmentation with ASPIRE-compatible responses.

Uses Hugging Face Transformers, not upstream SAM3/Triton. Point prompts are
explicitly unsupported; the supplied visual_pick_place skill uses text prompts.
"""
import argparse
import base64
import io
import logging
import threading
from pathlib import Path

import numpy as np
from PIL import Image
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


class SegmentRequest(BaseModel):
    image_base64: str = Field(min_length=1, max_length=12_000_000)
    text_prompt: str = Field(min_length=1, max_length=256)


class BoxSegmentRequest(BaseModel):
    image_base64: str = Field(min_length=1, max_length=12_000_000)
    box: list[float] = Field(min_length=4, max_length=4)


def decode_image(encoded):
    try:
        with Image.open(io.BytesIO(base64.b64decode(encoded, validate=True))) as source:
            if source.width * source.height > 4_000_000:
                raise ValueError("Image exceeds four million pixels")
            return source.convert("RGB")
    except (ValueError, OSError, Image.DecompressionBombError) as error:
        raise HTTPException(400, "Expected a base64 encoded image of at most four million pixels") from error


def encode_results(result, label, shape):
    rows = []
    for mask, box, score in zip(result["masks"], result["boxes"], result["scores"]):
        if hasattr(mask, "detach"):
            mask = mask.detach().cpu().numpy()
        mask = np.asarray(mask, dtype=np.uint8)
        if mask.shape != shape:
            raise ValueError("Model returned a mask that is not aligned with the source image")
        box = box.detach().cpu().tolist() if hasattr(box, "detach") else list(box)
        score = float(score)
        if len(box) != 4 or not np.isfinite(box).all() or not np.isfinite(score):
            raise ValueError("Model returned nonfinite coordinates or confidence")
        rows.append(dict(mask_base64=base64.b64encode(mask.tobytes()).decode("ascii"),
                         shape=list(shape), box=box, score=score, label=label))
    return {"results": sorted(rows, key=lambda row: row["score"], reverse=True)}


class Sam3Engine:
    def __init__(self, model_id, device, threshold, revision=None):
        import torch
        import transformers
        from transformers import Sam3Model, Sam3Processor
        if device.startswith("cuda") and not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable; check the Windows driver or select --device cpu")
        self.torch, self.device, self.threshold = torch, device, threshold
        dtype = torch.float16 if device.startswith("cuda") else torch.float32
        logging.info("Loading %s on %s; first launch may download gated weights", model_id, device)
        self.processor = Sam3Processor.from_pretrained(model_id, revision=revision)
        self.model = Sam3Model.from_pretrained(model_id, revision=revision,
            dtype=dtype, attn_implementation="sdpa").to(device).eval()
        resolved_revision = getattr(self.model.config, "_commit_hash", None) or revision
        if resolved_revision is None and not Path(model_id).is_dir():
            from huggingface_hub import try_to_load_from_cache
            cached_config = try_to_load_from_cache(model_id, "config.json", revision=revision)
            if isinstance(cached_config, str):
                resolved_revision = Path(cached_config).parent.name
        self.metadata = dict(model=model_id, revision=resolved_revision,
                             device=device, dtype=str(dtype), transformers=transformers.__version__,
                             torch=torch.__version__, threshold=threshold, point_prompts=False,
                             box_prompts=True)
        self.lock = threading.Lock()

    def segment(self, image, text, *, box=None):
        with self.lock, self.torch.inference_mode():
            geometry = {} if box is None else dict(input_boxes=[[list(box)]], input_boxes_labels=[[1]])
            inputs = self.processor(images=image, text=text, return_tensors="pt", **geometry).to(self.device)
            # Move only floating tensors to FP16; preserve integer token IDs.
            if self.device.startswith("cuda"):
                inputs = {key: value.to(dtype=self.torch.float16) if value.is_floating_point() else value
                          for key, value in inputs.items()}
            outputs = self.model(**inputs)
            result = self.processor.post_process_instance_segmentation(outputs,
                threshold=self.threshold, mask_threshold=0.5,
                target_sizes=[(image.height, image.width)])[0]
            return encode_results(result, text or "visual", (image.height, image.width))


def create_app(engine):
    app = FastAPI(title="ASPIRE Windows SAM3")

    @app.get("/health")
    def health():
        return dict(ready=True, **engine.metadata)

    @app.post("/segment")
    def segment(request: SegmentRequest):
        image = decode_image(request.image_base64)
        try:
            return engine.segment(image, request.text_prompt)
        except Exception as error:
            logging.exception("SAM3 inference failed")
            raise HTTPException(500, "SAM3 inference failed; inspect the server terminal") from error

    @app.post("/segment_point")
    def point():
        raise HTTPException(501, "This native server supports text and box prompts; point prompts are unsupported")

    @app.post("/segment_box")
    def segment_box(request: BoxSegmentRequest):
        image = decode_image(request.image_base64)
        x1, y1, x2, y2 = request.box
        if (not np.isfinite(request.box).all() or
                not 0 <= x1 < x2 <= image.width or not 0 <= y1 < y2 <= image.height):
            raise HTTPException(400, "Box must be finite source-image XYXY coordinates within image bounds")
        try:
            return engine.segment(image, None, box=request.box)
        except Exception:
            logging.exception("SAM3 box inference failed")
            raise HTTPException(500, "SAM3 inference failed; inspect the server terminal")

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8114)
    parser.add_argument("--model", default="facebook/sam3")
    parser.add_argument("--revision")
    parser.add_argument("--threshold", type=float, default=0.5)
    args = parser.parse_args()
    if not 0 <= args.threshold <= 1:
        parser.error("--threshold must be between zero and one")
    log_path = Path(__file__).resolve().parents[1] / ".local" / "sam3-server.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, handlers=[logging.StreamHandler(),
                        logging.FileHandler(log_path, encoding="utf-8")])
    logging.getLogger("httpx").setLevel(logging.WARNING)
    import uvicorn
    try:
        engine = Sam3Engine(args.model, args.device, args.threshold, args.revision)
    except Exception:
        logging.exception("Model initialization failed")
        raise SystemExit(1)
    uvicorn.run(create_app(engine), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
