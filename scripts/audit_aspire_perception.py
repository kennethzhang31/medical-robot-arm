"""Audit fixed SAM3 prompts on saved RGB-D scenes; private labels stay diagnostic."""
import argparse
import hashlib
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.aspire.artifacts import write_json
from src.aspire.geometry import mask_to_points, relative_point
from src.aspire.perception import Sam3Client


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def health(url):
    with urllib.request.urlopen(url.rstrip('/') + '/health', timeout=10) as response:
        return json.load(response)


def diagnose(detections, depth, calibration, positions, target, table_z=-0.003):
    rows = []
    for detection in detections:
        mask = np.asarray(detection['mask'], dtype=bool)
        row = dict(score=float(detection['score']), box=list(detection['box']),
                   mask_pixels=int(mask.sum()), mask_sha256=hashlib.sha256(mask.tobytes()).hexdigest(),
                   intended_identity_proxy=False)
        try:
            points = mask_to_points(mask, depth, calibration['intrinsics'], calibration['pose_mat'])
            points = points[(points[:, 2] > table_z + 0.0005) & (points[:, 2] < table_z + 0.045)]
            row['table_foreground_points'] = len(points)
            if len(points) < 8:
                raise ValueError('Insufficient foreground depth')
            center = np.median(points, axis=0)
            distances = {label: float(np.linalg.norm(center[:2] - position[:2]))
                         for label, position in positions.items()}
            nearest = min(distances, key=distances.get)
            row.update(sensor_center_base=center.tolist(), nearest_asset_root_xy=nearest,
                       nearest_distance_m=distances[nearest], intended_distance_m=distances[target],
                       intended_identity_proxy=nearest == target and distances[target] < 0.06)
        except ValueError as error:
            row['depth_error'] = str(error)
        rows.append(row)
    return rows


def draw(image, detections, rows):
    result = image.convert('RGBA')
    for detection, row in zip(detections, rows):
        pixels = np.zeros((image.height, image.width, 4), dtype=np.uint8)
        color = (0, 180, 90) if row['intended_identity_proxy'] else (255, 90, 0)
        pixels[np.asarray(detection['mask'], dtype=bool)] = [*color, 95]
        result = Image.alpha_composite(result, Image.fromarray(pixels))
    painter = ImageDraw.Draw(result)
    for detection, row in zip(detections, rows):
        color = (0, 255, 90) if row['intended_identity_proxy'] else (255, 110, 0)
        painter.rectangle(detection['box'], outline=color, width=2)
        painter.text(detection['box'][:2], f'{row["score"]:.3f} {row.get("nearest_asset_root_xy", "no depth")}', fill=color)
    return result.convert('RGB')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--url', default='http://127.0.0.1:8114')
    args = parser.parse_args()
    destination = Path(args.out).resolve()
    if not destination.is_relative_to(ROOT / 'logs'):
        raise ValueError('Audit output must be under repository logs')
    destination.mkdir(parents=True, exist_ok=True)
    if (destination / 'plan.json').exists():
        raise ValueError('Preserve completed/partial audits; use a fresh output directory')
    manifest = read(args.manifest)
    service = health(args.url)
    if service.get('ready') is not True or service['threshold'] != 0.5:
        raise ValueError('Expected ready SAM3 at unchanged threshold 0.5')
    hashes = {}
    for source in manifest['sources'].values():
        paths = [ROOT / source['snapshot'], ROOT / source['images'] / 'observation.json']
        paths += [ROOT / source['images'] / (camera + suffix)
                  for camera in manifest['cameras'] for suffix in ('.png', '_depth.npy')]
        hashes.update({str(path.relative_to(ROOT)): sha(path) for path in paths})
    write_json(destination / 'plan.json', dict(manifest=manifest, service=service, input_sha256=hashes,
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        identity_scope='Private nearest-root XY is a diagnostic proxy, not pixel ground truth or policy input.',
        simulator_starts=0, aspire_requests=0))
    client = Sam3Client(args.url)
    results = []
    started = time.monotonic()
    for scene, source in manifest['sources'].items():
        directory = ROOT / source['images']
        observation = read(directory / 'observation.json')
        snapshot = read(ROOT / source['snapshot'])
        robot = snapshot['state']['articulation']['robot']['root_pose'][0]
        positions = {(snapshot['task']['target'] if name == 'object' else name):
                     relative_point(asset['root_pose'][0][:3], robot[:3], robot[3:])
                     for name, asset in snapshot['state']['rigid_object'].items()}
        for target, prompts in manifest['prompts'].items():
            for prompt in prompts:
                for camera in manifest['cameras']:
                    identifier = f'{scene}_{target}_{prompt.replace(" ", "_")}_{camera}'
                    image = Image.open(directory / (camera + '.png')).convert('RGB')
                    depth = np.load(directory / (camera + '_depth.npy'), allow_pickle=False)
                    detections = client.segment(np.asarray(image), prompt, allow_empty=True)
                    rows = diagnose(detections, depth, observation['cameras'][camera], positions, target)
                    result = dict(id=identifier, scene=scene, target=target, prompt=prompt,
                                  camera=camera, detections=rows,
                                  target_proxy=any(row['intended_identity_proxy'] for row in rows))
                    write_json(destination / 'cases' / (identifier + '.json'), result)
                    mask_path = destination / 'masks' / (identifier + '.npz')
                    mask_path.parent.mkdir(exist_ok=True)
                    np.savez_compressed(mask_path, **{f'mask_{i}': row['mask'] for i, row in enumerate(detections)})
                    overlay_path = destination / 'overlays' / (identifier + '.png')
                    overlay_path.parent.mkdir(exist_ok=True)
                    draw(image, detections, rows).save(overlay_path)
                    results.append(result)
                    write_json(destination / 'progress.json', dict(completed=len(results), active=identifier))
                    print(json.dumps(dict(case=identifier, masks=len(rows), target_proxy=result['target_proxy'])), flush=True)
    summary = []
    for target, prompts in manifest['prompts'].items():
        for prompt in prompts:
            scenes = {scene: [r['camera'] for r in results if r['target'] == target and
                       r['prompt'] == prompt and r['scene'] == scene and r['target_proxy']]
                      for scene in manifest['sources']}
            summary.append(dict(target=target, prompt=prompt, target_proxy_views=scenes,
                                minimum_views=min(map(len, scenes.values()))))
            sheet = Image.new('RGB', (448 * len(manifest['cameras']), 472 * len(manifest['sources'])), 'white')
            painter = ImageDraw.Draw(sheet)
            for y, scene in enumerate(manifest['sources']):
                for x, camera in enumerate(manifest['cameras']):
                    identifier = f'{scene}_{target}_{prompt.replace(" ", "_")}_{camera}'
                    with Image.open(destination / 'overlays' / (identifier + '.png')) as overlay:
                        sheet.paste(overlay.resize((448, 448)), (448*x, 472*y + 24))
                    painter.text((448*x + 5, 472*y + 5), f'{scene} | {camera} | {prompt}', fill='black')
            sheet.save(destination / f'{target}_{prompt.replace(" ", "_")}_sheet.png')
    assert health(args.url) == service
    assert all(sha(ROOT / path) == expected for path, expected in hashes.items())
    write_json(destination / 'report.json', dict(status='completed', cases=len(results),
        elapsed_s=time.monotonic()-started, summary=summary, input_hashes_verified=True,
        service_unchanged=True, simulator_starts=0, aspire_requests=0))
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()
