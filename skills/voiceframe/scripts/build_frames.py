#!/usr/bin/env python3
"""从实测音轨时间轴批量生成 HyperFrames 帧 —— 视频项目的建帧主脚本。

用法：
    python3 build_frames.py --project .                # 读配置、生成、校验
    python3 build_frames.py --project . --dry-run      # 只打印计划

输入（都在项目根目录）：
    audio_meta.json    gen_voice.py 的产物：timeline 或 voices；母带句边界需校对
    cues.json          gen_cues.py 的产物；也支持 --cues cues-asr.json
    titles.json        Line 号 → 上屏标题（None = 不上屏）
    frames.config.json 项目配置：版式/ 素材池 / 章节卡（见下方 DEFAULT_CONFIG）

产物：
    compositions/frames/NN-slug.html
    frames.json   用于填写入口模板的帧清单
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# ══════════════════════════════════════════════════════════════
# 默认配置：按项目改这几处即可
# ══════════════════════════════════════════════════════════════

DEFAULT_CONFIG = {
    # 章节卡：Line 号 → (卡片副题, 巨字)
    "chapters": {},
    "figures": {},
    "pools": {},
    # 无标题的延续帧依次轮换的池（引文版式配抽象纹理较好）
    "quote_pool": "abstract",
    # 帧的轮转顺序（按帧号取模）
    "rotation": [],
    # 起始帧号 + 时间（开场帧不做揭开动画，保证第 0 帧有画面）
    "opening": {"frames": [1], "preload_frames": [1]},
    # 每句拆帧的时长阈值（秒）
    "split_thresholds": [20, 38],
    # 字体目录与 GSAP 路径（相对项目根）
    "font_dir": "assets/fonts",
    "gsap": "assets/gsap-3.14.2.min.js",
    # 系列标签（帧内左上角）
    "series_label": "系列名 · 副题",
}

# ══════════════════════════════════════════════════════════════
# 排版参数：按版式分栏宽，标题字号必须跟着栏宽走
# ══════════════════════════════════════════════════════════════

# 每种版式的标题栏宽（px）—— 用来校验标题不会在窄栏里折成孤字
TITLE_BOX = {"split": 500, "full": 1000, "chapter": 1700, "photo": 1200, "data": 340, "quote": 0}
MIN_BOX_FOR_CHARS = {500: 16, 1000: 26, 1700: 34, 1200: 30, 340: 10}

FONT_FACE = """      @font-face {{
        font-family: "Noto Sans SC"; font-weight: {w};
        src: url("{d}/notosanssc-{w}.woff2") format("woff2");
      }}
"""

SPLIT_CSS = """
      .v { position:absolute; left:0; top:0; width:62%; height:100%; overflow:hidden; }
      .v > video { width:100%; height:100%; object-fit:cover;
        /* 降饱和保色相，不用 grayscale —— 压掉色相就回不来了 */
        filter: saturate(0.42) contrast(1.16) brightness(0.62); transform-origin:50% 50%; }
      /* 画面侧统一压暗：素材亮度差异很大，压一层才能保证右侧文字永远可读 */
      .dim-l { position:absolute; left:0; top:0; width:62%; height:100%;
        background: rgba(17,17,17,0.42); pointer-events:none; }
      .fade-r { position:absolute; left:40%; top:0; width:22%; height:100%;
        background: linear-gradient(90deg, rgba(17,17,17,0) 0%, rgba(17,17,17,1) 100%); pointer-events:none; }
      .seam { position:absolute; left:62%; top:0; width:1px; height:100%; background: var(--line); }
      .hr { position:absolute; left:calc(62% + 110px); right:110px; height:1px; background: var(--line); }
      .kicker { position:absolute; left:calc(62% + 112px); top:88px;
        font-size:21px; font-weight:500; letter-spacing:0.32em; color: var(--orange); }
      .ttl { position:absolute; left:calc(62% + 110px); top:300px; width:500px;
        font-size:58px; font-weight:900; line-height:1.16; letter-spacing:-0.02em; color: var(--cream);
        overflow-wrap: anywhere; }
      .sub { position:absolute; left:calc(62% + 112px); top:560px; width:500px;
        font-size:27px; font-weight:500; line-height:1.6; color: var(--cream);
        background: rgba(17,17,17,0.72); padding:12px 16px; border-left:2px solid var(--orange); }
      /* 字幕只占右侧 38%，绝不压画面 */
      .subs { position:absolute; left:62%; right:0; bottom:78px;
        display:flex; flex-direction:column; align-items:flex-start; gap:10px;
        pointer-events:none; z-index:40; }
      .sub-line { max-width:640px; font-size:31px; line-height:1.42; color: var(--cream);
        text-shadow: 0 3px 14px rgba(0,0,0,.92), 0 1px 3px rgba(0,0,0,.98); }
"""

FULL_CSS = """
      .v { position:absolute; inset:0; overflow:hidden; }
      .v > video { width:100%; height:100%; object-fit:cover;
        filter: saturate(0.38) contrast(1.16) brightness(0.48); transform-origin:50% 50%; }
      .scrim { position:absolute; inset:0;
        background: linear-gradient(100deg, rgba(17,17,17,.94) 0%, rgba(17,17,17,.72) 34%, rgba(17,17,17,.12) 66%, rgba(17,17,17,0) 100%); }
      .hr { position:absolute; left:110px; right:110px; height:1px; background: var(--line); }
      .kicker { position:absolute; left:110px; top:88px;
        font-size:21px; font-weight:500; letter-spacing:0.32em; color: var(--orange); }
      .ttl { position:absolute; left:110px; top:340px; width:1000px;
        font-size:72px; font-weight:900; line-height:1.12; letter-spacing:-0.025em; color: var(--cream);
        overflow-wrap: anywhere; }
      .sub { position:absolute; left:114px; top:700px; width:880px;
        font-size:28px; font-weight:500; line-height:1.6; color: var(--cream);
        background: rgba(17,17,17,0.72); padding:12px 18px; border-left:2px solid var(--orange); }
      .subs { position:absolute; left:0; right:0; bottom:92px;
        display:flex; flex-direction:column; align-items:center; gap:10px;
        pointer-events:none; z-index:40; }
      .sub-line { max-width:1340px; text-align:center; font-size:42px; line-height:1.42; color: var(--cream);
        text-shadow: 0 3px 14px rgba(0,0,0,.92), 0 1px 3px rgba(0,0,0,.98), 0 0 22px rgba(0,0,0,.7); }
"""

# quote：同句的延续帧。基础布局与 full 一致，左侧橙线做引文引导线
QUOTE_CSS = """
      .v { position:absolute; inset:0; overflow:hidden; }
      .v > video { width:100%; height:100%; object-fit:cover;
        filter: saturate(0.30) contrast(1.14) brightness(0.52); transform-origin:50% 50%; }
      .scrim { position:absolute; inset:0;
        background: linear-gradient(100deg, rgba(17,17,17,.94) 0%, rgba(17,17,17,.74) 38%, rgba(17,17,17,.30) 70%, rgba(17,17,17,.10) 100%); }
      .hr { position:absolute; left:110px; right:110px; height:1px; background: var(--line); }
      .kicker { position:absolute; left:110px; top:88px;
        font-size:21px; font-weight:500; letter-spacing:0.32em; color: var(--orange); }
      .q { position:absolute; left:110px; top:260px; width:1000px;
        border-left:3px solid var(--orange); padding:8px 0 8px 34px; }
      .q-line { font-size:42px; font-weight:700; line-height:1.34; color: var(--cream);
        text-shadow: 0 3px 16px rgba(0,0,0,.9); }
      .q-line + .q-line { margin-top:12px; }
"""

CHAPTER_CSS = """
      .bg { position:absolute; inset:0; background: var(--orange); }
      .num { position:absolute; left:110px; top:96px;
        font-size:22px; font-weight:500; letter-spacing:0.3em; color:#111111; }
      .ttl { position:absolute; left:110px; top:380px; width:1700px;
        font-size:132px; font-weight:900; line-height:1.02; letter-spacing:-0.035em; color:#111111;
        overflow-wrap: anywhere; }
      .sub { position:absolute; left:116px; top:800px;
        font-size:26px; font-weight:500; letter-spacing:0.14em; color: rgba(17,17,17,.75); }
      .bar { position:absolute; left:110px; top:360px; width:140px; height:4px; background:#111111; }
      .subs { position:absolute; left:0; right:0; bottom:92px;
        display:flex; flex-direction:column; align-items:center; pointer-events:none; z-index:40; }
      .sub-line { max-width:1340px; text-align:center; font-size:38px; color:#111111; }
"""

# data：图表版式。图表须先经 darken_figures.py 转深色（底色=ink-black）
DATA_CSS = """
      .bg { position:absolute; inset:0; background: var(--ink); }
      .kick { position:absolute; left:96px; top:92px;
        font-size:21px; font-weight:500; letter-spacing:0.32em; color: var(--orange); }
      .ttl { position:absolute; left:96px; top:300px; width:340px;
        font-size:34px; font-weight:900; line-height:1.28; color: var(--cream); overflow-wrap:anywhere; }
      .fig { position:absolute; left:500px; top:230px; width:1310px; height:620px;
        display:flex; align-items:center; justify-content:center; }
      .fig img { max-width:100%; max-height:100%; object-fit:contain; }
      .cap { position:absolute; left:500px; bottom:22px; width:1310px;
        font-size:21px; font-weight:500; line-height:1.6; color: var(--cream-muted); }
      .subs { position:absolute; left:500px; right:110px; width:auto; bottom:92px;
        display:flex; flex-direction:column; align-items:flex-start; pointer-events:none; z-index:40; }
      .sub-line { max-width:1520px; text-align:left; font-size:30px; color: var(--cream);
        text-shadow: 0 3px 14px rgba(0,0,0,.92); }
"""

PHOTO_CSS = """
      .v { position:absolute; inset:0; overflow:hidden; }
      .v > img { width:100%; height:100%; object-fit:cover;
        filter: saturate(0.42) contrast(1.05) brightness(0.70); transform-origin:50% 50%; }
      .scrim { position:absolute; inset:0;
        background: linear-gradient(0deg, rgba(17,17,17,.9) 0%, rgba(17,17,17,.2) 44%, rgba(17,17,17,.55) 100%); }
      .hr { position:absolute; left:110px; right:110px; height:1px; background: var(--line); }
      .ttl { position:absolute; left:110px; top:420px; width:1200px;
        font-size:68px; font-weight:900; line-height:1.14; color: var(--cream); overflow-wrap:anywhere; }
      .cap { position:absolute; right:110px; bottom:110px; width:640px;
        font-size:24px; line-height:1.7; color: var(--cream-muted); text-align:right; }
      .subs { position:absolute; left:0; right:0; bottom:92px;
        display:flex; flex-direction:column; align-items:center; pointer-events:none; z-index:40; }
      .sub-line { max-width:1340px; text-align:center; font-size:42px; color: var(--cream);
        text-shadow: 0 3px 14px rgba(0,0,0,.92); }
"""

STYLE = {"split": SPLIT_CSS, "full": FULL_CSS, "quote": FULL_CSS + QUOTE_CSS,
          "chapter": CHAPTER_CSS, "data": DATA_CSS, "photo": PHOTO_CSS}

BASE_CSS = """      #root { position:relative; width:100%; height:100%; overflow:hidden;
        font-family:"Noto Sans SC", sans-serif;
        --ink:#111111; --orange:#e85d26; --cream:#f0ece5;
        --cream-muted:#888880; --cream-hint:#505048; --line:#282826; }
      #root * { box-sizing:border-box; }
"""

# ══════════════════════════════════════════════════════════════
# 工具
# ══════════════════════════════════════════════════════════════


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def load_json(path, default=None):
    p = Path(path)
    if not p.exists():
        return default if default is not None else {}
    return json.loads(p.read_text(encoding="utf-8"))


def subs_markup(cid, cues):
    """每条字幕按自己的起止时间硬切，保留语音间的空白。"""
    inner, anim = [], []
    for i, cue in enumerate(cues):
        target = f"f{cid}-s{i}"
        inner.append(f'<div class="sub-line" id="{target}" style="opacity:0;position:absolute;bottom:0">{esc(cue["text"])}</div>')
        anim.append(f'tl.set(document.getElementById("{target}"), {{opacity:1}}, {cue["t"]:.6f});')
        anim.append(f'tl.set(document.getElementById("{target}"), {{opacity:0}}, {cue["t"] + cue["d"]:.6f});')
    return '<div class="subs">' + "".join(inner) + '</div>', "\n".join(anim)


def quote_lines(vo, max_len=30, max_lines=4):
    """把旁白切成引文行：按标点断成 ≤max_len，最多 max_lines 行。

    引文是精炼，不是把整段旁白搬上屏 —— 不设上限会切出十几行压进字幕区。
    """
    out = []
    for sent in [x.strip() for x in re.split(r"[。！？；]", vo or "") if x.strip()]:
        buf = ""
        for part in re.split(r"[，、]", sent):
            if len(buf) + len(part) <= max_len:
                buf += part
            else:
                if buf:
                    out.append(buf)
                buf = part
        if buf:
            out.append(buf)
    return out[:max_lines]


def split_cue(text, max_chars=20):
    """ASR 句超长时拆字幕块（调用方需按字数瓜分该句时长）。"""
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []
    chunks, buf = [], ""
    for ch in text:
        buf += ch
        if ch in "。！？；，、,.!?;" and len(buf) >= max_chars * 0.55:
            chunks.append(buf)
            buf = ""
    if buf:
        chunks.append(buf)
    final = []
    for c in chunks:
        c = c.strip()
        while len(c) > max_chars + 8:
            final.append(c[:max_chars])
            c = c[len(final[-1]):]
        if c:
            final.append(c.strip())
    return [c for c in final if c]


def cues_in_window(flat, t0, t1):
    """保留所有与帧重叠的字幕，截断并换算成帧内秒。"""
    result = []
    for cue in flat:
        start = max(cue["t"], t0)
        end = min(cue["t"] + cue["d"], t1)
        if end > start:
            result.append({"text": cue["text"], "t": round(start - t0, 6),
                           "d": round(end - start, 6)})
    return sorted(result, key=lambda c: c["t"])


# ══════════════════════════════════════════════════════════════
# 帧生成
# ══════════════════════════════════════════════════════════════


def build_frame(n, dur, title, vo, style, media, cfg, cues, chapter=None, figure=None):
    cid = f"f{n:02d}"
    pools = cfg["pools"]
    preload = ' preload="auto"' if n in cfg["opening"]["preload_frames"] else ""
    opening = n in cfg["opening"]["frames"]
    series = esc(cfg["series_label"])
    font_dir = cfg["font_dir"]

    # 标题：栏宽决定字号上限，避免窄栏折出孤字
    box = TITLE_BOX.get(style, 1000)
    lines = (title or "").split("\n")
    if style == "data":
        ttl_html, sub_html = "<br>".join(esc(x) for x in lines), ""
    elif style == "quote":
        ttl_html, sub_html = "", ""
    elif style == "chapter":
        ttl_html = "<br>".join(esc(x) for x in lines)
        sub_html = esc(chapter[0]) if chapter else ""
    else:
        ttl_html = "<br>".join(esc(x) for x in lines)
        sub_html = ""

    # 各版式的 DOM + 动画
    vid = (f'assets/broll/{media}' if media and media.endswith(".mp4")
           else media)if media else ""

    if style == "split":
        body = f"""    <div class="v" id="f{cid}-v">
      <video id="f{cid}-video" class="clip" data-start="0" data-duration="{dur}"
        data-track-index="0" src="{esc(vid)}" muted playsinline{preload}
        data-layout-allow-overflow></video>
    </div>
    <div class="dim-l" id="f{cid}-dim"></div>
    <div class="fade-r"></div>
    <div class="seam"></div>
    <div class="hr" style="top:64px"></div>
    <div class="hr" style="bottom:64px"></div>
    <div class="kicker" id="f{cid}-kick">{series}</div>
    <div class="bar" id="f{cid}-bar"></div>
    <div class="ttl" id="f{cid}-ttl">{ttl_html}</div>
    <div class="sub" id="f{cid}-sub">{sub_html}</div>
"""
        anim = (f'        var video=document.getElementById("f{cid}-video");'
                f'var ttl=document.getElementById("f{cid}-ttl");'
                f'var bar=document.getElementById("f{cid}-bar");'
                f'var kick=document.getElementById("f{cid}-kick");'
                f'var dim=document.getElementById("f{cid}-dim");'
                + (f' tl.set(video,{{opacity:1}},0);' if opening else
                   f' tl.fromTo(video,{{clipPath:"inset(0 100% 0 0)"}},'
                   f'{{clipPath:"inset(0 0% 0 0)",duration:1.05,ease:"power3.inOut"}},0.05);')
                + f' tl.to(video,{{scale:1.08,duration:{max(dur-1.26,0.01):.2f},ease:"none"}},1.26);'
                + f' tl.fromTo(dim,{{opacity:0}},{{opacity:1,duration:0.6}},0.2);'
                + f' tl.fromTo(kick,{{opacity:0,y:-10}},{{opacity:1,y:0,duration:0.5}},0.3);'
                + f' tl.fromTo(bar,{{scaleX:0}},{{scaleX:1,duration:0.55}},0.42);'
                + f' tl.fromTo(ttl,{{opacity:0,y:40}},{{opacity:1,y:0,duration:0.85}},0.52);')

    elif style == "quote":
        ql = "".join(f'          <div class="q-line">{esc(x)}</div>' for x in quote_lines(" ".join(c["text"] for c in cues) or vo))
        body = f"""    <div class="v" id="f{cid}-v">
      <video id="f{cid}-video" class="clip" data-start="0" data-duration="{dur}"
        data-track-index="0" src="{esc(vid)}" muted playsinline{preload}
        data-layout-allow-overflow></video>
    </div>
    <div class="scrim"></div>
    <div class="hr" style="top:64px"></div>
    <div class="hr" style="bottom:64px"></div>
    <div class="kicker" id="f{cid}-kick">{series}</div>
    <div class="q" id="f{cid}-q">
{ql}
    </div>
"""
        anim = (f'        var video=document.getElementById("f{cid}-video");'
                f'var q=document.getElementById("f{cid}-q");'
                f'var kick=document.getElementById("f{cid}-kick");'
                + (f' tl.set(video,{{opacity:1}},0);' if opening else
                   f' tl.fromTo(video,{{opacity:0,scale:1.05}},{{opacity:1,scale:1,duration:1.2}},0.05);')
                + (f' tl.set(q,{{opacity:1,x:0}},0);' if opening else
                   f' tl.fromTo(q,{{opacity:0,x:-24}},{{opacity:1,x:0,duration:0.8}},0.32);')
                + (f' tl.set(kick,{{opacity:1,y:0}},0);' if opening else
                   f' tl.fromTo(kick,{{opacity:0,y:-10}},{{opacity:1,y:0,duration:0.5}},0.15);')
                + f' tl.to(video,{{scale:1.1,duration:{max(dur - 1.26, 0.01):.2f},ease:"none"}},1.26);')

    elif style == "chapter":
        body = f"""    <div class="bg"></div>
    <div class="num" id="f{cid}-num">{esc(chapter[0]) if chapter else ''}</div>
    <div class="bar" id="f{cid}-bar"></div>
    <div class="ttl" id="f{cid}-ttl">{ttl_html}</div>
    <div class="sub" id="f{cid}-sub">{sub_html}</div>
"""
        anim = (f'        var ttl=document.getElementById("f{cid}-ttl");'
                f'var bar=document.getElementById("f{cid}-bar");'
                f'var num=document.getElementById("f{cid}-num");'
                f'var sub=document.getElementById("f{cid}-sub");'
                f' tl.fromTo(num,{{opacity:0,x:-14}},{{opacity:1,x:0,duration:0.5}},0.05);'
                f' tl.fromTo(bar,{{scaleX:0}},{{scaleX:1,duration:0.6}},0.2);'
                f' tl.fromTo(ttl,{{opacity:0,y:46}},{{opacity:1,y:0,duration:0.85}},0.3);'
                f' tl.fromTo(sub,{{opacity:0,y:12}},{{opacity:1,y:0,duration:0.5}},0.95);'
                f' tl.to(ttl,{{opacity:0.06,duration:0.6}},{max(dur-0.6,0):.2f});')

    elif style == "data":
        fig_label, fig_cap = figure if figure else ("", "")
        body = f"""    <div class="bg"></div>
    <div class="kick" id="f{cid}-kick">{esc(fig_label)}</div>
    <div class="ttl" id="f{cid}-ttl">{ttl_html}</div>
    <div class="fig" id="f{cid}-fig">
      <img id="f{cid}-img" class="clip" data-start="0" data-duration="{dur}"
        data-track-index="0" src="{esc(media)}" alt="" />
    </div>
    <div class="cap" id="f{cid}-cap">{esc(fig_cap)}</div>
"""
        anim = (f'        var img=document.getElementById("f{cid}-img");'
                f'var fig=document.getElementById("f{cid}-fig");'
                f'var ttl=document.getElementById("f{cid}-ttl");'
                f'var kick=document.getElementById("f{cid}-kick");'
                f'var cap=document.getElementById("f{cid}-cap");'
                f' tl.fromTo(kick,{{opacity:0,y:-10}},{{opacity:1,y:0,duration:0.5}},0.05);'
                f' tl.fromTo(ttl,{{opacity:0,y:26}},{{opacity:1,y:0,duration:0.75}},0.15);'
                f' tl.fromTo(fig,{{opacity:0,y:30}},{{opacity:1,y:0,duration:0.95}},0.35);'
                f' tl.fromTo(img,{{scale:1.05,opacity:0.2}},{{scale:1,opacity:1,duration:1.5}},0.35);'
                f' tl.fromTo(cap,{{opacity:0,y:12}},{{opacity:1,y:0,duration:0.55}},1.3);')

    elif style == "photo":
        body = f"""    <div class="v" id="f{cid}-v">
      <img id="f{cid}-img" class="clip" data-start="0" data-duration="{dur}"
        data-track-index="0" src="{esc(media)}" alt="" />
    </div>
    <div class="scrim"></div>
    <div class="hr" style="top:64px"></div>
    <div class="hr" style="bottom:64px"></div>
    <div class="ttl" id="f{cid}-ttl">{ttl_html}</div>
    <div class="cap" id="f{cid}-cap">{esc(cfg.get("photo_caption", ""))}</div>
"""
        anim = (f'        var img=document.getElementById("f{cid}-img");'
                f'var ttl=document.getElementById("f{cid}-ttl");'
                f'var cap=document.getElementById("f{cid}-cap");'
                f' tl.fromTo(img,{{opacity:0,scale:1.03}},{{opacity:1,scale:1,duration:1.4}},0.05);'
                f' tl.to(img,{{scale:1.1,duration:{max(dur-1.46,0.01):.2f},ease:"none"}},1.46);'
                f' tl.fromTo(ttl,{{opacity:0,y:34}},{{opacity:1,y:0,duration:0.85}},0.7);'
                f' tl.fromTo(cap,{{opacity:0,y:14}},{{opacity:1,y:0,duration:0.6}},1.5);')

    else:  # full
        body = f"""    <div class="v" id="f{cid}-v">
      <video id="f{cid}-video" class="clip" data-start="0" data-duration="{dur}"
        data-track-index="0" src="{esc(vid)}" muted playsinline{preload}
        data-layout-allow-overflow></video>
    </div>
    <div class="scrim"></div>
    <div class="hr" style="top:64px"></div>
    <div class="hr" style="bottom:64px"></div>
    <div class="kicker" id="f{cid}-kick">{series}</div>
    <div class="bar" id="f{cid}-bar"></div>
    <div class="ttl" id="f{cid}-ttl">{ttl_html}</div>
    <div class="sub" id="f{cid}-sub">{sub_html}</div>
"""
        anim = (f'        var video=document.getElementById("f{cid}-video");'
                f'var ttl=document.getElementById("f{cid}-ttl");'
                f'var bar=document.getElementById("f{cid}-bar");'
                f'var kick=document.getElementById("f{cid}-kick");'
                + (f' tl.set(video,{{opacity:1}},0);' if opening else
                   f' tl.fromTo(video,{{opacity:0,scale:1.05}},{{opacity:1,scale:1,duration:1.2}},0.05);')
                + f' tl.to(video,{{scale:1.1,duration:{max(dur - 1.26, 0.01):.2f},ease:"none"}},1.26);'
                f' tl.fromTo(kick,{{opacity:0,y:-10}},{{opacity:1,y:0,duration:0.5}},0.15);'
                f' tl.fromTo(bar,{{scaleX:0}},{{scaleX:1,duration:0.55}},0.28);'
                f' tl.fromTo(ttl,{{opacity:0,y:40}},{{opacity:1,y:0,duration:0.85}},0.38);')

    subs_html, subs_anim = subs_markup(cid, cues)

    fonts = "".join(FONT_FACE.format(w=w, d=font_dir) for w in (400, 500, 700, 900))
    return f"""<template>
  <div id="{cid}" data-composition-id="{cid}"
    data-width="1920" data-height="1080" data-duration="{dur}">
    <style>
{fonts}{BASE_CSS.replace("#root", "#" + cid)}{STYLE[style]}
    </style>

{body}{subs_html}
    <script src="{cfg['gsap']}"></script>
    <script>
      (function () {{
        var root = document.getElementById("{cid}");
        if (!root) return;
        var tl = gsap.timeline({{ paused: true }});
{anim}
{subs_anim}
        window.__timelines = window.__timelines || {{}};
        window.__timelines["{cid}"] = tl;
      }})();
    </script>
  </div>
</template>
"""


# ══════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", type=Path, required=True)
    ap.add_argument("--timeline", default="audio_meta.json",
                    help="时间轴文件；缺失时回退到 timeline.json")
    ap.add_argument("--cues", default="cues-asr.json")
    ap.add_argument("--titles", default="titles.json")
    ap.add_argument("--config", default="frames.config.json")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    root = a.project.resolve()
    out_dir = root / "compositions/frames"

    cfg = dict(DEFAULT_CONFIG)
    user = load_json(root / a.config, {})
    cfg.update(user)
    # gen_voice.py 写 audio_meta.json；部分项目手工重命名成 timeline.json，两个都认。
    # load_json 在文件缺失时返回空 dict，错误信息会指错文件，所以先查存在性。
    tl_path = root / a.timeline
    if not tl_path.exists():
        alt = root / "timeline.json"
        if a.timeline != "timeline.json" and alt.exists():
            tl_path = alt
        else:
            sys.exit(f"缺时间轴文件：{tl_path}\n"
                     f"（gen_voice.py 的产物；或用 --timeline 指定）")
    audio = load_json(tl_path, {})
    tl = audio.get("timeline") or audio.get("voices") or []
    if not tl:
        sys.exit(f"时间轴里没有 timeline/voices：{tl_path}")
    cues_raw = load_json(root / a.cues, None)
    if not (root / a.cues).exists():
        sys.exit(f"缺字幕文件：{root / a.cues}")
    if isinstance(cues_raw, dict):
        cues_raw = [cue for seq in cues_raw.values() for cue in seq]
    titles = {int(k): v for k, v in load_json(root / a.titles, {}).items()}
    chapters = {int(k): tuple(v) for k, v in cfg.get("chapters", {}).items()}
    figures = cfg.get("figures", {})

    # 标题集合必须与句号对齐，否则多余键会静默失效
    if titles:
        if set(titles) != {t["line"] for t in tl}:
            sys.exit("titles.json 与音轨 Line 编号不一致")

    import math
    previous_end = 0.0
    for item in tl:
        start, span = item["start"], item["duration"]
        if not math.isfinite(start) or not math.isfinite(span) or span <= 0 or start < previous_end - 0.05:
            sys.exit("音轨时间轴必须按开始时间排序、无重叠且时长为正")
        previous_end = start + span

    # ── 切帧
    thr = cfg.get("split_thresholds", [20, 38])
    if len(thr) != 2 or not 0 < thr[0] < thr[1]:
        sys.exit("split_thresholds 必须是两个递增正数")
    frames, f = [], 0
    for t in tl:
        d = t["duration"]
        k = 1 if d <= thr[0] else (2 if d <= thr[1] else 3)
        seg = d / k
        for i in range(k):
            f += 1
            frames.append({"n": f, "dur": seg, "line": t["line"],
                           "part": f"{i+1}/{k}", "vo": t.get("voiceover") or t.get("text", ""),
                           "t0": t["start"] + i * seg})
    print(f"{len(tl)} 句 → {len(frames)} 帧")

    # ── 素材池轮转游标
    cursors = {k: 0 for k in cfg["pools"]}

    def take(pool):
        items = cfg["pools"].get(pool)
        if not items:
            sys.exit(f"素材池为空或不存在：{pool}")
        v = items[cursors[pool] % len(items)]
        cursors[pool] += 1
        return v

    # ── 逐帧
    meta, titled = [], set()
    rendered = []
    qpool = cfg.get("quote_pool", "abstract")
    rot = cfg.get("rotation") or list(cfg["pools"])
    if not rot:
        sys.exit("请在 frames.config.json 配置实际素材 pools 与 rotation")

    for fr in frames:
        n, dur, ln, vo = fr["n"], fr["dur"], fr["line"], fr["vo"]
        f0 = fr["t0"]

        # ① 字幕窗口（必须在版式判定之前算好）
        cues = cues_in_window(cues_raw, f0, f0 + dur)

        # ② 章节卡 / 图表
        is_chapter = ln in chapters
        is_fig = False
        fig_meta = None
        for path, info in figures.items():
            if isinstance(info, dict) and n in info.get("frames", []):
                is_fig, fig_meta = True, (path, info)

        # 标题只属于本 Line；图表帧也展示标题，避免串到下一句。
        title = None if ln in titled else titles.get(ln)
        if is_chapter and ln not in titled:
            title = chapters[ln][1] or title
        if title:
            titled.add(ln)

        # ④ 版式判定（优先级从高到低）
        if is_chapter and title is not None:
            style, media, chapter = "chapter", None, chapters[ln]
        elif is_fig:
            style, media, chapter = "data", fig_meta[0], None
        elif title is None and cues:
            style, media, chapter = "quote", take(qpool), None
        else:
            style = "split" if n % 3 != 2 else "full"
            media, chapter = take(rot[n % len(rot)]), None

        # ── 校验：栏宽 vs 标题字数
        if title and TITLE_BOX.get(style) in MIN_BOX_FOR_CHARS:
            need = max(len(x) for x in title.replace("\n", "|").split("|"))
            if need > MIN_BOX_FOR_CHARS[TITLE_BOX.get(style, 1000)]:
                print(f"  ⚠️ F{n:02d} {style} 标题 {need} 字可能折行（栏宽 {TITLE_BOX.get(style)}）")

        if media:
            asset = f"assets/broll/{media}" if media.endswith(".mp4") else media
            if not (root / asset).is_file():
                sys.exit(f"素材不存在：{asset}")
        slug = re.sub(r"[^a-z0-9]+", "-", str(title or f"line{ln}").lower()).strip("-")[:26] or "frame"
        path = out_dir / f"{n:02d}-{slug}.html"
        fig_arg = (fig_meta[1]["label"], fig_meta[1]["caption"]) if fig_meta else None
        rendered.append((path, build_frame(n, dur, title, vo, style, media, cfg,
                                           cues, chapter, fig_arg)))
        fr.update({"file": path.name, "style": style, "media": media,
                   "screen_title": title, "cues": len(cues), "composition_id": f"f{n:02d}"})
        meta.append(fr)

    # ── 校验：标题既不能整句丢失，也不能在多帧显示完全相同文本
    shown = {}
    for fr in meta:
        if fr.get("screen_title"):
            shown.setdefault(fr["line"], []).append(fr["screen_title"])
    lost = [ln for ln, v in titles.items() if v and ln not in shown and ln not in chapters]
    dup = {ln: ts for ln, ts in shown.items() if len(set(ts)) != len(ts)}
    if lost:
        sys.exit(f"这些 Line 的标题整句丢失了: {sorted(lost)}")
    if dup:
        sys.exit(f"这些 Line 在多帧显示了完全相同的文本: {dup}")

    # ── 校验：素材重复度（太高会显得重复）
    from collections import Counter
    used = Counter(fr["media"] for fr in meta if fr["media"])
    if used:
        worst = max(used.values())
        print(f"素材：{len(used)} 条，最大重复 {worst}×"
              + ("（偏高，考虑补素材）" if worst >= 3 else ""))

    total = max(fr["t0"] + fr["dur"] for fr in meta)
    print(f"版式分布: {dict(Counter(fr['style'] for fr in meta))}")
    print(f"总时长 {total:.2f}s（{total/60:.2f} min）")
    if not a.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
        for path, html in rendered:
            path.write_text(html, encoding="utf-8")
        (root / "frames.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print("→ frames.json（按 t0、dur、file 填写入口模板）")


if __name__ == "__main__":
    main()