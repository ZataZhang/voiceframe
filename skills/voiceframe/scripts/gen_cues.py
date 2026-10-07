#!/usr/bin/env python3
"""从 audio_meta.json 的时间轴切出字幕块（cues.json）。

时间基准是实测音轨，不是估算。切分规则：
  主标点（。！？；）→ 超 18 字按（，、）再切 → 仍超长的硬拆。
单块时长按字数比例分配该句时长。
"""
import argparse
import json
import re
import sys
import subprocess
import tempfile
from pathlib import Path

MAX = 18
HARD = MAX + 6      # 无标点长串的硬拆阈值


def split_cues(text, max_chars=MAX):
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
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


def offline_main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project', type=Path, required=True)
    p.add_argument('--meta', default='audio_meta.json')
    p.add_argument('--out', default='cues.json')
    p.add_argument('--max-chars', type=int, default=MAX)
    a = p.parse_args()
    if a.max_chars <= 0:
        p.error('--max-chars must be positive')
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




def split_piece(text, max_chars=MAX):
    """把一条 ASR 句切成字幕块：优先在标点处断，过长则硬拆。"""
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    # 保留标点跟着前一个片段
    chunks, buf = [], ''
    for ch in text:
        buf += ch
        if ch in BREAKS and len(buf) >= max_chars * 0.55:
            chunks.append(buf)
            buf = ''
    if buf:
        chunks.append(buf)

    out = []
    for c in chunks:
        c = c.strip()
        while len(c) > max_chars + 8:
            cut = c[:max_chars]
            # 尽量切在标点附近
            for i in range(len(cut) - 1, int(max_chars * 0.6), -1):
                if cut[i] in BREAKS:
                    cut = cut[:i + 1]
                    break
            out.append(cut.strip())
            c = c[len(cut):]
        if c.strip():
            out.append(c.strip())
    return out


def asr_main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--asr', action='store_true', required=True)
    ap.add_argument('--project', type=Path, required=True)
    ap.add_argument('--audio', default='assets/voice/master-oneshot.wav')
    ap.add_argument('--model', default='fun-asr')
    ap.add_argument('--out', default='cues-asr.json')
    ap.add_argument('--raw', default='asr-raw.json')
    ap.add_argument('--max-chars', type=int, default=MAX)
    ap.add_argument('--reuse', action='store_true', help='复用已存在的 --raw，不重跑 ASR')
    a = ap.parse_args()
    if a.max_chars <= 0:
        ap.error('--max-chars must be positive')
    root = a.project.resolve()
    audio = root / a.audio
    if not audio.exists():
        raise SystemExit(f'audio not found: {audio}')
    raw = root / a.raw

    if not (a.reuse and raw.exists()):
        print(f'ASR {audio.name} …')
        with tempfile.TemporaryDirectory(prefix='voiceframe-asr-') as tmp:
            pending = Path(tmp) / 'asr.json'
            r = subprocess.run(['bl', 'speech', 'recognize', '--url', str(audio),
                '--model', a.model, '--language', 'zh', '--out', str(pending)],
                capture_output=True, text=True)
            if r.returncode != 0 or not pending.exists():
                raise SystemExit(f'ASR failed:\n{r.stdout[-800:]}\n{r.stderr[-800:]}')
            data = json.loads(pending.read_text(encoding='utf-8'))
            if not data.get('transcripts'):
                raise SystemExit('ASR returned no transcripts')
            raw.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')


    data = json.loads(raw.read_text(encoding='utf-8'))
    tr = data['transcripts'][0]
    sents = tr.get('sentences') or []

    cues = []
    for s in sents:
        text = (s.get('text') or '').strip()
        b, e = s.get('begin_time', 0), s.get('end_time', 0)
        if not text or e <= b:
            continue
        pieces = split_piece(text, a.max_chars)
        if not pieces:
            continue
        # 一条 ASR 句拆成多块时，按字数比例瓜分该句时长；
        # 否则所有块共用同一 t，会同时出现。
        span = (e - b) / 1000
        weights = [max(len(x), 1) for x in pieces]
        tot = sum(weights)
        acc = b / 1000
        for piece, w in zip(pieces, weights):
            d = span * w / tot
            cues.append({'text': piece, 't': round(acc, 3), 'd': round(d, 3)})
            acc += d

    (root / a.out).write_text(json.dumps(cues, ensure_ascii=False, indent=2),
                              encoding='utf-8')
    lens = [len(c['text']) for c in cues] or [0]
    dur = tr.get('content_duration_in_milliseconds', 0) / 1000
    print(f'{len(cues)} cues / {len(sents)} ASR sentences → {a.out}')
    print(f'chars/cue: min {min(lens)} / avg {sum(lens)/len(lens):.1f} / max {max(lens)}')
    if dur:
        print(f'speech ends at {dur:.1f}s')
    bad = sum(1 for i in range(1, len(cues)) if cues[i]['t'] < cues[i-1]['t'])
    print('monotonic:', 'OK' if not bad else f'{bad} violations')
    for c in cues[:5]:
        print(f"  {c['t']:7.2f}s +{c['d']:5.2f}  {c['text']}")




if __name__ == '__main__':
    if '--asr' in sys.argv:
        asr_main()
    else:
        offline_main()
