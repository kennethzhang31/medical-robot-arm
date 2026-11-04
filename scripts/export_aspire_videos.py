"""Make portable H.264 copies of ASPIRE recordings and verify decoded frames."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import cv2
import numpy as np
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def decode(path):
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise RuntimeError(f'Cannot open {path}')
    expected = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = capture.get(cv2.CAP_PROP_FPS)
    fourcc = int(capture.get(cv2.CAP_PROP_FOURCC))
    sample_indices = {0, expected // 4, expected // 2, 3 * expected // 4, expected - 1}
    samples, stats, count = {}, [], 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if count in sample_indices:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                samples[count] = Image.fromarray(rgb)
                red, green, blue = rgb.astype(np.float32).transpose(2, 0, 1)
                green_fraction = np.mean((green > 100) & (green > red * 1.5) & (green > blue * 1.5))
                stats.append(dict(frame=count, green_fraction=float(green_fraction)))
            count += 1
    finally:
        capture.release()
    if count != expected or not count:
        raise RuntimeError(f'Incomplete decode for {path}: {count}/{expected}')
    return dict(frames=count, fps=fps, duration_s=count / fps,
                codec_tag=''.join(chr((fourcc >> (8 * i)) & 255) for i in range(4)),
                width=samples[0].width, height=samples[0].height,
                sampled_green_fractions=stats), samples


def export(args):
    destination = Path(args.out).resolve()
    if not destination.is_relative_to(ROOT):
        raise ValueError('Export directory must be inside the workspace')
    destination.mkdir(parents=True, exist_ok=args.resume)
    trials = ROOT / 'logs/scissor_hab_source_physics_20261007/trials'
    sources = sorted(trials.glob('*/*.mp4'))
    sources += sorted((ROOT / 'logs/scissor_hab_20261007/trials').glob('*/*.mp4'))
    report = dict(encoding=dict(codec='libx264', profile='high', pixel_format='yuv420p',
                                fps=24, crf=18, faststart=True, audio=False), videos=[])
    panels = []
    for source in sources:
        trial = source.parent.name
        prefix = 'failed_preflight_' if source.is_relative_to(ROOT / 'logs/scissor_hab_20261007') else ''
        label = {'H_s903': '_HUMAN', 'A_s903': '_no_library', 'B_s903': '_3_skills'}.get(trial, '')
        target = destination / f'{prefix}{trial}{label}.mp4'
        before = sha256(source)
        original, original_samples = decode(source)
        metadata = json.loads((source.parent / 'screen_recording.json').read_text(encoding='utf-8'))
        if before != metadata['sha256']:
            raise RuntimeError(f'Original recording hash differs from capture metadata: {source}')
        command = [args.ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin', '-n',
                   '-i', str(source), '-map', '0:v:0', '-an', '-vf', 'fps=24,format=yuv420p',
                   '-c:v', 'libx264', '-profile:v', 'high', '-level:v', '4.0',
                   '-preset', 'fast', '-crf', '18', '-threads', '2', '-movflags', '+faststart', str(target)]
        if not target.exists():
            result = subprocess.run(command, capture_output=True, text=True, timeout=600)
            if result.returncode:
                raise RuntimeError(result.stderr)
        probe = subprocess.run([args.ffmpeg, '-hide_banner', '-i', str(target)],
                               capture_output=True, text=True, timeout=30).stderr
        if 'Video: h264' not in probe or 'yuv420p' not in probe:
            raise RuntimeError(f'Output is not H.264 YUV 4:2:0: {target}')
        portable, portable_samples = decode(target)
        if abs(original['duration_s'] - portable['duration_s']) > 1 / 24 + 0.001:
            raise RuntimeError(f'Output codec or duration check failed: {target}')
        comparisons = []
        for fraction in (0.25, 0.75):
            source_index = int(original['frames'] * fraction)
            target_index = int(portable['frames'] * fraction)
            src_image = original_samples[source_index]
            dst_image = portable_samples[target_index]
            mae = float(np.mean(np.abs(np.asarray(src_image, dtype=float) - np.asarray(dst_image, dtype=float))))
            comparisons.append(dict(fraction=fraction, mean_absolute_rgb_error=mae))
            if mae > 10:
                raise RuntimeError(f'Output frame differs substantially from original: {target}')
            if trial in ('H_s903', 'A_s903', 'B_s903'):
                panels.append((trial, fraction, src_image, dst_image))
        if sha256(source) != before:
            raise RuntimeError(f'Original changed during conversion: {source}')
        report['videos'].append(dict(source=str(source.relative_to(ROOT)), output=target.name,
            source_sha256=before, output_sha256=sha256(target), original=original, portable=portable,
            frame_comparisons=comparisons, output_bytes=target.stat().st_size))
        (destination / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(dict(video=target.name, duration_s=portable['duration_s'], status='verified')), flush=True)
    sheet = Image.new('RGB', (1280, 230 * 3), 'white')
    draw = ImageDraw.Draw(sheet)
    for row, trial in enumerate(('H_s903', 'A_s903', 'B_s903')):
        matches = [panel for panel in panels if panel[0] == trial]
        for column_pair, (_, fraction, original, portable) in enumerate(matches):
            for side, picture in enumerate((original, portable)):
                x, y = (column_pair * 2 + side) * 320, row * 230
                picture = picture.copy()
                picture.thumbnail((320, 200))
                sheet.paste(picture, (x, y + 25))
                draw.text((x + 4, y + 5), f'{trial} {fraction:.0%} ' + ('original' if side == 0 else 'H.264'), fill='black')
    sheet.save(destination / 'decoded_frame_comparison.jpg')
    (destination / 'SHA256SUMS.txt').write_text(''.join(
        f"{row['output_sha256']}  {row['output']}\n" for row in report['videos']), encoding='ascii')
    (destination / 'README.md').write_text(
        '# Portable ASPIRE Recordings\n\n'
        'H.264 High profile, YUV 4:2:0, 24 fps, fast-start MP4, no audio. '
        'The original 4 fps timeline is preserved by repeating frames; there is no new captured motion.\n\n'
        'H = human baseline; A = generated without a skill library; B = generated with three skills. '
        'Seeds 901-905 are paired trials. The three seed-903 files have descriptive suffixes. '
        'observe and observe_replay are motionless preflight recordings. '
        'failed_preflight_observe is the earlier failed setup.\n\n'
        'All original hashes match capture metadata. Every original and exported frame decoded. '
        'manifest.json records codecs, duration, frame comparisons and SHA-256 checksums. '
        'decoded_frame_comparison.jpg compares the three named clips before and after conversion.\n\n'
        'To check a Google Drive download, compare Get-FileHash -Algorithm SHA256 on it with '
        'SHA256SUMS.txt. Equal hashes establish identical bytes. A mismatch needs investigation: '
        'a processed/transcoded copy can differ from the original download without transfer corruption. '
        'No cloud round-trip was tested here.\n', encoding='utf-8')
    print(json.dumps(dict(status='complete', count=len(report['videos']), directory=str(destination))), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    parser.add_argument('--ffmpeg', required=True)
    parser.add_argument('--resume', action='store_true', help='Verify and reuse existing exports')
    export(parser.parse_args())
