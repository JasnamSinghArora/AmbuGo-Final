#!/usr/bin/env python3
"""One entry point for both AmbuGo animations; no live map service required."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))
os.environ.setdefault('MPLCONFIGDIR', str(ROOT / 'generated' / '.mplconfig'))


def verify_files():
    manifest = ROOT / 'MANIFEST.json'
    if not manifest.exists():
        raise FileNotFoundError('MANIFEST.json is missing; extract the complete archive.')
    items = json.loads(manifest.read_text())['files']
    errors = []
    for item in items:
        path = ROOT / item['path']
        if not path.is_file():
            errors.append('Missing: ' + item['path'])
        elif hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            errors.append('Changed: ' + item['path'])
    if errors:
        raise RuntimeError('\n'.join(errors))
    print(f'Archive integrity: {len(items)} files match their SHA-256 checksums.')


def verify_videos(directory):
    import imageio_ffmpeg
    ffmpeg = os.environ.get('AMBUGO_FFMPEG') or imageio_ffmpeg.get_ffmpeg_exe()
    checks = []
    for name in ['01_Google_Maps_Journey.mp4', '02_Progression.mp4']:
        path = Path(directory) / name
        result = subprocess.run(
            [ffmpeg, '-v', 'error', '-i', str(path), '-f', 'null', '-',
             '-progress', 'pipe:1'], capture_output=True, text=True, check=True)
        progress = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
        if int(progress.get('frame', 0)) != 600 or progress.get('out_time') != '00:00:20.000000':
            raise AssertionError(f'Unexpected frame count or duration: {name}: {progress}')
        frames = imageio_ffmpeg.read_frames(str(path), pix_fmt='rgb24')
        try:
            info = next(frames)
        finally:
            frames.close()
        if tuple(info['size']) != (1920, 1080) or abs(info['fps'] - 30) > 1e-6:
            raise AssertionError(f'Unexpected resolution or frame rate: {name}: {info}')
        checks.append({'file': name, 'frames': 600, 'duration_s': 20,
                       'size': list(info['size']), 'fps': info['fps'], 'decode': 'passed'})
    return checks


def make_player(output):
    for name in ['index.html', 'READ_ME.txt']:
        shutil.copy2(ROOT / 'reference' / name, output / name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['all', 'map', 'graph', 'preview', 'verify', 'data', 'serve'])
    parser.add_argument('--output', type=Path, default=ROOT / 'generated', help='Generated files; reference videos are never overwritten.')
    parser.add_argument('--videos', type=Path, help='With verify, also fully decode both MP4s in this folder.')
    parser.add_argument('--port', type=int, default=8768, help='Local preview port for serve.')
    args = parser.parse_args()
    output = args.output.resolve()
    if args.command == 'serve':
        from functools import partial
        from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
        print(f'Open http://127.0.0.1:{args.port}/reference/ to watch the supplied videos.', flush=True)
        print(f'Open http://127.0.0.1:{args.port}/generated/ after rendering with the default output folder.', flush=True)
        with ThreadingHTTPServer(('127.0.0.1', args.port), partial(SimpleHTTPRequestHandler, directory=str(ROOT))) as server:
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
        return
    output.mkdir(parents=True, exist_ok=True)
    if args.command == 'verify':
        verify_files()
        from validate_story import validate_story
        from map_animation import Movie
        from build_graph_data import build, compare_curves
        validate_story(output)
        rebuilt = build(ROOT / 'data' / 'replays', output / 'progression_data_rebuilt.json')
        compare_curves(rebuilt, ROOT / 'data' / 'progression_data.json')
        Movie(output)
        camera = json.loads((output / 'camera_audit.json').read_text())
        if camera['checked_frames'] != 495 or camera['failures']:
            raise AssertionError('Camera visibility check failed.')
        report = {'archive_integrity': 'passed', 'story_events': 'passed', 'raw_graph_series': 'exact match',
                  'camera_visible_frames': camera['visible_frames'],
                  'camera_checked_frames': camera['checked_frames']}
        if args.videos:
            report['videos'] = verify_videos(args.videos)
        (output / 'verification.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
        return
    if args.command == 'data':
        subprocess.run([sys.executable, str(ROOT / 'src' / 'build_graph_data.py'),
                        '--output', str(output / 'progression_data_rebuilt.json'),
                        '--check-against', str(ROOT / 'data' / 'progression_data.json')], check=True)
        return
    if args.command in ('all', 'map', 'preview'):
        from map_animation import render
        render(output, preview=args.command == 'preview')
    if args.command in ('all', 'graph', 'preview'):
        from graph_animation import render
        render(output, preview=args.command == 'preview')
    if args.command != 'preview':
        make_player(output)
        print('Saved to:', output)


if __name__ == '__main__':
    main()
