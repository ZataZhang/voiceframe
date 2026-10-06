#!/usr/bin/env python3
"""Extract SCRIPT lines, synthesize bounded-retry WAVs and measure a timeline."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import time


def parse_script(text):
    lines, current = [], None
    for row in text.splitlines():
        match = re.match(r'^## Line (\d+)\b(.*)', row)
        if match:
            tail = match[2]
            frame = re.search(r'\(Frame (\d+)\)', tail)
            current = {'line': int(match[1]), 'frame': int(frame[1]) if frame else int(match[1]),
                       'title': tail.strip(' —'), 'parts': []}
            lines.append(current)
        elif row.startswith('## '):
            current = None
        elif current is not None and row.startswith('    ') and row.strip():
            current['parts'].append(row[4:])
    if not lines or len({x['line'] for x in lines}) != len(lines):
        raise ValueError('SCRIPT must contain unique ## Line N sections')
    for item in lines:
        item['text'] = '\n'.join(item.pop('parts'))
        if not item['text'].strip():
            raise ValueError(f"Line {item['line']} has no indented narration")
    return lines


def duration(path):
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                             '-of', 'csv=p=0', str(path)], check=True, capture_output=True, text=True)
    value = float(result.stdout.strip())
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f'Invalid audio duration: {path}')
    return value


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project', type=Path, required=True)
    p.add_argument('--script', default='SCRIPT.md')
    p.add_argument('--model', default='qwen-audio-3.1-tts-flash')
    p.add_argument('--voice', default='xunanchuan_v3.1')
    p.add_argument('--tail', type=float, default=0.7)
    p.add_argument('--attempts', type=int, choices=range(1, 5), default=4)
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--existing-audio', action='store_true', help='Index existing NN.wav; do not invoke bl')
    a = p.parse_args()
    if not math.isfinite(a.tail) or a.tail < 0:
        p.error('--tail must be finite and non-negative')
    root = a.project.resolve()
    lines = parse_script((root / a.script).read_text(encoding='utf-8'))
    if a.dry_run:
        print(json.dumps({'model': a.model, 'voice': a.voice, 'lines': lines}, ensure_ascii=False, indent=2))
        return
    out = root / 'assets/voice'
    out.mkdir(parents=True, exist_ok=True)
    meta, cursor = [], 0.0
    for item in lines:
        dest = out / f"{item['line']:02d}.wav"
        stamp = dest.with_suffix('.sha256')
        fingerprint = hashlib.sha256(json.dumps([item['text'], a.model, a.voice, 24000],
                                                ensure_ascii=False).encode()).hexdigest()
        cached = dest.exists() and stamp.exists() and stamp.read_text() == fingerprint
        if not a.existing_audio and cached:
            try:
                duration(dest)
            except (subprocess.CalledProcessError, ValueError):
                cached = False
        if not a.existing_audio and not cached:
            textfile = out / f"{item['line']:02d}.txt"
            textfile.write_text(item['text'], encoding='utf-8')
            pending = dest.with_name(dest.stem + '.pending.wav')
            for attempt in range(a.attempts):
                pending.unlink(missing_ok=True)
                result = subprocess.run(['bl', 'speech', 'synthesize', '--model', a.model,
                    '--voice', a.voice, '--text-file', str(textfile), '--format', 'wav',
                    '--sample-rate', '24000', '--out', str(pending)], capture_output=True, text=True)
                if result.returncode == 0:
                    duration(pending)
                    pending.replace(dest)
                    stamp.write_text(fingerprint)
                    break
                transient = any(s in result.stderr + result.stdout for s in
                    ['url error, please check url', 'Engine error [411]', 'Engine return error code: 418'])
                pending.unlink(missing_ok=True)
                if not transient or attempt + 1 == a.attempts:
                    raise RuntimeError(f"Line {item['line']} synthesis failed; CLI exit {result.returncode}")
                time.sleep(min(2 ** attempt, 8))
        seconds = duration(dest)
        meta.append({**item, 'path': dest.relative_to(root).as_posix(), 'start': round(cursor, 6),
                     'audio_duration': seconds, 'duration': seconds + a.tail})
        cursor += seconds + a.tail
    payload = {'bgm': None, 'sfx': [], 'voices': meta, 'duration': round(cursor, 6),
               'engine': 'existing-audio' if a.existing_audio else f'bl/{a.model}',
               'voice': None if a.existing_audio else a.voice}
    temporary = root / 'audio_meta.json.tmp'
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(root / 'audio_meta.json')
    print(f'Indexed {len(meta)} lines, {cursor:.2f}s → audio_meta.json')


if __name__ == '__main__':
    main()
