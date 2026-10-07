#!/usr/bin/env python3
"""从 audio_meta.json 的时间轴切出字幕块（cues.json）。

时间基准是实测音轨，不是估算。切分规则：
  主标点（。！？；）→ 超 18 字按（，、）再切 → 仍超长的硬拆。
单块时长按字数比例分配该句时长。
"""
import argparse
import json
import re
from pathlib import Path

MAX = 18
HARD = MAX + 6      # 无标点长串的硬拆阈值


def split_cues(text, max_chars=MAX):
    chunks = []
    for raw in re.split(r'(?<=[。！？；])', text):
        raw = raw.strip()
        if not raw:
            continue
        if len(raw) <= max_chars:
            chunks.append(raw)
            continue
        buf = ''
        for part in re.split(r'(?<=[，、])', raw):
            if len(buf) + len(part) <= max_chars:
                buf += part
            else:
                if buf:
                    chunks.append(buf)
                buf = part
        if buf:
            chunks.append(buf)
    out = []
    for c in chunks:
        while len(c) > max_chars + 6:
            out.append(c[:max_chars])
            c = c[max_chars:]
        if c:
            out.append(c)
    return [c.strip('，、；。 ') for c in out if c.strip('，、；。 ')]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project', type=Path, required=True)
    p.add_argument('--meta', default='audio_meta.json')
    p.add_argument('--out', default='cues.json')
    p.add_argument('--max-chars', type=int, default=MAX)
    a = p.parse_args()
    root = a.project.resolve()
    meta = json.loads((root / a.meta).read_text(encoding='utf-8'))
    lines = meta.get('timeline') or meta.get('voices')
    if not lines:
        raise SystemExit(f'no timeline in {a.meta}')

    out = {}
    for item in lines:
        text = item.get('text') or item.get('voiceover') or ''
        cues = split_cues(text, a.max_chars)
        if not cues:
            continue
        weights = [len(c) for c in cues]
        total = sum(weights) or 1
        span = float(item.get('duration') or (item['end'] - item['start']))
        acc = 0.0
        seq = []
        for i, (c, w) in enumerate(zip(cues, weights)):
            d = span * w / total
            if i == len(cues) - 1:
                d = span - acc
            seq.append({'text': c, 't': round(item['start'] + acc, 3), 'd': round(d, 3)})
            acc += d
        out[str(item['line'])] = seq

    n = sum(len(v) for v in out.values())
    lens = [c['text'] for v in out.values() for c in v]
    (root / a.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{n} cues over {len(out)} lines → {a.out}')
    if lens:
        print(f'chars per cue: min {min(map(len, lens))} / avg {sum(map(len, lens))/len(lens):.1f} / max {max(map(len, lens))}')


if __name__ == '__main__':
    main()