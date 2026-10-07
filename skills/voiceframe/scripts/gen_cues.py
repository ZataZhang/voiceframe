#!/usr/bin/env python3
"""用 ASR 从音频反推与语音严格同步的字幕（cues-asr.json）。

为什么不用「按字数比例分配」：估算的时间轴随语速漂移，长片累积到几秒
就明显不同步。ASR 直接给出毫秒级句边界，是唯一可靠的时间基准。

用法：
    python3 gen_cues.py --project . --audio assets/voice/master-oneshot.wav

输出：
    cues-asr.json         平铺 list，按绝对时间排序（build_frames.py 按窗口取用）
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

MAX = 18
BREAKS = '。！？；，、,.!?;'


def media_duration(path):
    """音频实测时长（秒）；ffprobe 缺失或解析失败时返回 0，跳过覆盖检查。"""
    try:
        r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                            'format=duration', '-of', 'csv=p=0', str(path)],
                           capture_output=True, text=True)
        return float(r.stdout.strip())
    except (OSError, ValueError):
        return 0.0


def split_piece(text, max_chars=MAX):
    """把一条 ASR 句切成字幕块：优先在标点处断，过长则硬拆。"""
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

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
            # 尽量切在标点附近，避免切在词中间
            for i in range(len(cut) - 1, int(max_chars * 0.6), -1):
                if cut[i] in BREAKS:
                    cut = cut[:i + 1]
                    break
            out.append(cut.strip())
            c = c[len(cut):]
        if c.strip():
            out.append(c.strip())
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--project', type=Path, required=True)
    ap.add_argument('--audio', default='assets/voice/master-oneshot.wav')
    ap.add_argument('--model', default='fun-asr')
    ap.add_argument('--out', default='cues-asr.json')
    ap.add_argument('--raw', default='asr-raw.json')
    ap.add_argument('--max-chars', type=int, default=MAX)
    ap.add_argument('--reuse', action='store_true',
                    help='复用已存在的 --raw，不重跑 ASR')
    a = ap.parse_args()

    root = a.project.resolve()
    audio = root / a.audio
    if not audio.exists():
        raise SystemExit(f'audio not found: {audio}')
    raw = root / a.raw

    if not (a.reuse and raw.exists()):
        print(f'ASR {audio.name} …')
        r = subprocess.run(
            ['bl', 'speech', 'recognize', '--url', str(audio),
             '--model', a.model, '--language', 'zh', '--out', str(raw)],
            capture_output=True, text=True)
        if not raw.exists():
            raise SystemExit(f'ASR failed:\n{r.stdout[-800:]}\n{r.stderr[-800:]}')

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
        # 一条 ASR 句拆成多块时，按字数比例瓜分该句时长——
        # 否则所有块共用同一个 t，会同时出现在画面上。
        span = (e - b) / 1000
        weights = [max(len(x), 1) for x in pieces]
        tot = sum(weights)
        acc = b / 1000
        for piece, w in zip(pieces, weights):
            cues.append({'text': piece, 't': round(acc, 3),
                         'd': round(span * w / tot, 3)})
            acc += span * w / tot

    cues.sort(key=lambda c: c['t'])
    (root / a.out).write_text(json.dumps(cues, ensure_ascii=False, indent=2),
                              encoding='utf-8')

    lens = [len(c['text']) for c in cues] or [0]
    print(f'{len(cues)} cues / {len(sents)} ASR sentences → {a.out}')
    print(f'chars/cue: min {min(lens)} / avg {sum(lens)/len(lens):.1f} / max {max(lens)}')

    # 字幕必须覆盖到音频末尾。ASR 的 content_duration 是净语音时长（不含停顿），
    # 不是结束时间——拿它对照会误判成「字幕缺了一截」。这里用音频实测时长。
    if cues:
        covered = cues[-1]['t'] + cues[-1]['d']
        actual = media_duration(audio)
        print(f'cues cover {covered:.2f}s / audio {actual:.2f}s')
        if actual and covered < actual - 0.5:
            print(f'⚠️ 字幕未覆盖到音频末尾，缺 {actual - covered:.2f}s', file=sys.stderr)

    # 单调性校验：必须不递减，否则字幕会乱序
    bad = sum(1 for i in range(1, len(cues)) if cues[i]['t'] < cues[i - 1]['t'])
    print('monotonic:', 'OK' if not bad else f'{bad} violations')
    if bad:
        raise SystemExit('字幕时间不是单调递增，不能用')

    for c in cues[:4]:
        print(f"  {c['t']:7.2f}s +{c['d']:5.2f}  {c['text']}")


if __name__ == '__main__':
    main()