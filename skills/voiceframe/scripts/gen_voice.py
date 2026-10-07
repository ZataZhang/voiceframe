#!/usr/bin/env python3
"""Extract SCRIPT lines, synthesize bounded-retry WAVs and measure a timeline.

Two modes:
  --mode segment  one WAV per Line. Short pieces, and lets you re-record a single line.
  --mode oneshot  the whole script in ONE request. **Required for narration >= 3 min** —
                  per-Line segments make the TTS add 1-5s of breath at each head/tail,
                  which accumulates to ~28% silence across a long piece.
                  Requires numpy (for net-speech measurement in the alignment pass).
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import time

try:
    import numpy as np
except ImportError:  # only --mode oneshot needs it
    np = None


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


def synth_once(root, model, voice, text, dest, attempts):
    """一次请求生成整段音频，带有上限的瞬态错误重试。"""
    textfile = dest.with_suffix('.txt')
    textfile.write_text(text, encoding='utf-8')
    pending = dest.with_name(dest.stem + '.pending.wav')
    for attempt in range(attempts):
        pending.unlink(missing_ok=True)
        result = subprocess.run(['bl', 'speech', 'synthesize', '--model', model,
            '--voice', voice, '--text-file', str(textfile), '--format', 'wav',
            '--sample-rate', '24000', '--out', str(pending)], capture_output=True, text=True)
        if result.returncode == 0:
            try:
                duration(pending)
            except (subprocess.CalledProcessError, ValueError):
                pass
            else:
                pending.replace(dest)
                return dest
        transient = any(s in result.stderr + result.stdout for s in
            ['url error, please check url', 'Engine error [411]', 'Engine return error code: 418'])
        pending.unlink(missing_ok=True)
        if not transient or attempt + 1 == attempts:
            raise RuntimeError(f'One-shot synthesis failed; CLI exit {result.returncode}')
        time.sleep(min(2 ** attempt, 8))
    raise RuntimeError('unreachable')


def run_oneshot(root, lines, a):
    """整段一次生成，并用语速一致性映射反推每句起止。

    分段拼接会让 TTS 在每段首尾各加 1-5s 呼吸，累积后占全片 28% 静音；
    整段生成只保留句内韵律。见 references/tts-voice.md。
    """
    out = root / 'assets/voice'
    out.mkdir(parents=True, exist_ok=True)
    master = out / a.oneshot_name
    script_text = '\n'.join(item['text'] for item in lines)

    if a.dry_run:
        print(json.dumps({'mode': 'oneshot', 'model': a.model, 'voice': a.voice,
                          'chars': len(script_text), 'lines': len(lines),
                          'out': master.relative_to(root).as_posix()},
                         ensure_ascii=False, indent=2))
        return

    if a.existing_audio:
        if not master.exists():
            raise SystemExit(f'--existing-audio needs an existing {master}')
    else:
        synth_once(root, a.model, a.voice, script_text, master, a.attempts)

    total = duration(master)
    segments = segment_stt(lines, root, a) if not a.existing_audio else None

    # 语速一致性映射：分段版每句的净语音时长按比例缩放到母带
    timeline = []
    if segments:
        weights = segments
    else:
        weights = [len(item['text']) for item in lines]
    total_weight = sum(weights) or 1
    acc = 0.0
    for item, w in zip(lines, weights):
        span = total * w / total_weight
        timeline.append({**item, 'start': round(acc, 3), 'end': round(acc + span, 3),
                         'duration': round(span, 3)})
        acc += span
    timeline[0]['start'] = 0.0
    timeline[-1]['end'] = round(total, 3)
    timeline[-1]['duration'] = round(total - timeline[-1]['start'], 3)

    payload = {'engine': 'existing-audio' if a.existing_audio else f'bl/{a.model}',
               'voice': None if a.existing_audio else a.voice,
               'mode': 'oneshot', 'master': master.relative_to(root).as_posix(),
               'duration': round(total, 3), 'line_count': len(lines), 'timeline': timeline}
    temporary = root / 'audio_meta.json.tmp'
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(root / 'audio_meta.json')
    print(f'One-shot master {total:.2f}s, {len(timeline)} lines aligned → audio_meta.json')


def segment_stt(lines, root, a):
    """分段跑一遍只为量每句净语音时长（剔除首尾静音），用于语速映射。

    不影响交付物：母带仍是整段那一份。这些分段可留在 assets/voice 供逐句替换。
    """
    probe_dir = root / 'assets/voice/_probe'
    probe_dir.mkdir(parents=True, exist_ok=True)
    weights = []
    for item in lines:
        dest = probe_dir / f"{item['line']:02d}.wav"
        if not dest.exists():
            synth_once(root, a.model, a.voice, item['text'], dest, a.attempts)
        weights.append(net_speech_seconds(dest))
    return weights


def net_speech_seconds(path, sr=16000, frame_ms=20):
    """量一段音频的有声时长（剔除首尾静音）。"""
    if np is None:
        raise SystemExit('--mode oneshot alignment needs numpy: pip install numpy')
    raw = path.with_name(path.stem + '.f32')
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', str(path), '-ac', '1',
                    '-ar', str(sr), '-f', 'f32le', str(raw)], capture_output=True)
    data = np.frombuffer(raw.read_bytes(), dtype=np.float32)
    raw.unlink(missing_ok=True)
    if data.size == 0:
        raise ValueError(f'empty probe: {path}')
    fl = int(sr * frame_ms / 1000)
    nf = data.size // fl
    energy = np.sqrt((data[:nf * fl].reshape(nf, fl) ** 2).mean(axis=1) + 1e-12)
    return float((energy > energy.max() * 0.02).sum() * fl / sr)


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
    p.add_argument('--mode', choices=['segment', 'oneshot'], default='segment',
                   help='segment: one WAV per Line (short pieces). oneshot: the whole script in ONE '
                        'request — required for narration >= 3 min, see references/tts-voice.md')
    p.add_argument('--oneshot-name', default='master-oneshot.wav')
    a = p.parse_args()
    if not math.isfinite(a.tail) or a.tail < 0:
        p.error('--tail must be finite and non-negative')
    root = a.project.resolve()
    lines = parse_script((root / a.script).read_text(encoding='utf-8'))

    if a.mode == 'oneshot':
        return run_oneshot(root, lines, a)

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
