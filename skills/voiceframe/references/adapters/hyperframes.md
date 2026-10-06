# HyperFrames 制作适配

仅在项目选用 HyperFrames 时读取。这里的 CLI 版本、性能和本机环境是既有项目记录，执行前以当前环境与官方规范核对。

## 环境

本机**没有 bun**，用 npx：

```bash
npx hyperframes@0.8.137 lint      # 静态结构检查
npx hyperframes@0.8.137 check     # 浏览器门禁：运行时报错、布局、动效、对比度
npx hyperframes@0.8.137 preview   # 浏览器实时预览
npx hyperframes@0.8.137 render    # 渲染 MP4
npx hyperframes@0.8.137 snapshot # 抽帧截图
```

要求 Node.js 22+、FFmpeg。

**开发 HyperFrames 本体仓库时另说** —— 那时用 `bun install` / `bun run build` / `bun run test`，且新 worktree 里必须先 `bun run build` 一次。

## 两道门禁不可跳过

```bash
npx hyperframes lint   # 静态 HTML 结构
npx hyperframes check  # 无头 Chrome：运行时错误、布局、动效、WCAG 对比度
```

改完任何 `.html` composition，两者都过才算完成。`check` 常抓出肉眼看不见的问题 —— 深色场上的 ink-box 几何、对比度不足、动画未注册。

## composition 骨架

```html
<div id="stage" data-composition-id="launch" data-start="0" data-width="1920" data-height="1080">
  <h1 id="title" class="clip" data-start="1" data-duration="4" data-track-index="1">Launch day</h1>
  <audio data-start="0" data-duration="6" data-track-index="2" data-volume="0.5" src="music.wav"></audio>
  <script src="assets/gsap-3.14.2.min.js"></script>
  <script>
    const tl = gsap.timeline({ paused: true });
    tl.from("#title", { opacity: 0, y: 40, duration: 0.8 }, 1);
    window.__timelines = window.__timelines || {};
    window.__timelines.launch = tl;
  </script>
</div>
```

硬性规则：

- 动画必须 **`paused: true`** 并注册到 `window.__timelines[compositionId]` —— 渲染器靠逐帧 seek 定位
- 手动加入根时间线的场景时间线**不能是 paused**，否则 seek 时不推进
- 元素需要 `class="clip"` 才有时间轴语义
- **确定性**：禁止 `Date.now()`、无种子 `Math.random()`、渲染期网络请求

## 长片渲染

20 分钟量级没有时长上限，但有两个真约束。

### 磁盘：必须走 streaming

落盘路径是 `帧数 × w × h × 4`，1080p30 约 **25 GB/分钟**。20 分钟 ≈ **500 GB**。

默认的 streaming 模式（单 worker）不落全部帧，**必须用它**。分段模式（`HF_SEGMENTED_CAPTURE`）会丢 worker-encode 流水线，慢一倍且「没有 orchestrator 级fallback」，编码或拼接失败即终止整个 render。

### 时间：可接受

实测 300s / 1080p30 单 worker streaming 耗时 **2m43s**（≈0.55× 实时）。推算 1200s 单 worker 约 11 分钟，`-w 3` 约 8–12 分钟。

```bash
npx hyperframes@0.8.137 render --workers 3 --quality draft
```

先跑 `--quality draft` 验证，确认无误再出终版。

### 超时的真实含义

所有超时都是**per-call / 空闲性质**，不是总时长限制：`ffmpegStreamingTimeout: 600_000`、`protocolTimeout` 默认 300s（随像素面积放大，绝对上限 30 分钟）。渲染跑很久不代表卡住了。

### snapshot

`--frames` 默认 5，无上限，纯按总时长均分采样。20 分钟下采样间隔会拉到 75s，短 beat 会被跳过 —— 需要细看就显式加大 `--frames`（160s 用 16 张是合适的）。

## 分章长片的施工顺序

```
1. 音频先定稿 → 拿到准确时长（见 [分镜与脚本](../storyboard.md)）
2. 逐章：写 HTML → lint → check → snapshot 确认布局
3. 逐章 render（改一章只重跑一章）
4. ffmpeg 拼接各章
5. 整片 render（streaming, -w 3）
```

低内存主机（≤8GB）会自动降级为单 worker。注意低内存检测读宿主 RAM 而非 cgroup，Docker 里需手动设`PRODUCER_LOW_MEMORY_MODE`。

## 素材复用

50+ 现成 block（转场、字幕、图表、地图、效果）：

```bash
npx hyperframes@0.8.137 catalog   # 搜
npx hyperframes@0.8.137 add <name> # 装
```

**手写任何具名视觉之前先搜 catalog。**

## 内置建帧模板

[入口骨架](../../assets/adapters/hyperframes/index.html.template) 与 [子帧骨架](../../assets/adapters/hyperframes/compositions/frames/frame.html.template) 提供主 composition、子帧时间槽与旁白音轨结构。复制后替换变量，准备本地 GSAP 与覆盖当前文字的字体，再通过 lint/check；模板不含旧项目专属视觉或媒体。详见 [模板使用](../templates.md)。

---

## check 门禁的「几何模型」（2026-10-06 殷鉴01 实战）

布局审计把文字 ink box 当作 **~1.4×font-size、以行框为中心**（CSS `line-height:0.82` 也照算）。实用推论：

- **大号数字（900 weight、负 line-height）上下各留 ≥0.45em 真空带**，否则 `content_overlap` 报错。修法是缩字号 + 拉开分带，别 suppress
- 每个文字块独占一个纵向 band；kicker/标题/正文/图表带间距宁大勿小
- 帧内换组元素前，旧元素先 0.25s 淡出**完成**再进新的 —— 新旧文字同框 0.2s 就会被抓
- 对比度实测：深底（#111111）上文字只许 `#F0ECE5`（cream）或 `#888880`（muted）；`#505048`（cream-hint）/`#282826`（line）是 2.37:1，只能做细线和条形填充
- 动效：同 target 多次 `fromTo` 要 `immediateRender:false`（只留最早一个）；同 prop 相邻 tween 留 ≥0.01s 间隙，否则 `overlapping_gsap_tweens`
- 转场交叠期两帧同屏出现的 `info` 级 overlap 是**正常现象**，不要去修

## 中文项目：CJK 字体必须随项目自带

渲染机视为干净 headless Chrome，**没有任何系统中文字体**，lint 拦 `font_family_without_font_face`。

1. 下载 OTF（注意是 `NotoSansCJKsc-*`，`NotoSansSC-*` 是 404）：
   `github.com/notofonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-{Regular,Medium,Bold,Black}.otf`
2. fonttools+brotli 子集化 → `assets/fonts/notosanssc-{400,500,700,900}.woff2`（~330KB/字重）
   - **文件名必须以规范化族名开头（`notosanssc`）+ 数字字重** —— captions/字体发现逻辑靠前缀匹配
   - 子集范围 = 扫全项目文本（md/html/json/txt）的字符 ∪ ASCII ∪ 全角标点；**建完帧再重跑一次**
3. 每帧 HTML 内联 @font-face 四个字重；全片只用这一族，数字 `tabular-nums`
4. GSAP 本地 vendor：`assets/gsap-3.14.2.min.js`，帧内 `<script src="assets/gsap-3.14.2.min.js">`（勿用 CDN URL）

## 多帧并行施工（frame-packets + sub-agent）

15 帧级别项目的打法（15/15 首轮 lint 干净）：

```
storyboard 定稿 → frame-packets 生成每帧 packet（含 blueprint + 动效规则内联）
→ 先手写 1 个参考帧过 lint+check（golden sample）
→ 每 frame 一个 sub-agent 并行构建（prompt = _role.md + packet + frame.md + 参考帧路径 + 硬约束清单）
→ assemble → lint/check → 按报错逐帧修
```

硬约束清单要点：单 `<template>` 碎片、根用 `#root` 选择器、全出血背景是独立 `class="clip"` 子元素（不放 #root）、id 加帧前缀、narration 不上屏、图片根相对路径 `public/…`（**中文名先改成 ASCII**）。

## 环境补充

- 本机 Chrome 首次渲染要下载 chrome-headless-shell，node 直连被限流（~30KB/s）；curl 直链 `storage.googleapis.com/chrome-for-testing-public/<ver>/mac-arm64/…` 有 ~5MB/s，或用 `HYPERFRAMES_BROWSER_PATH` 指向已装的 Chrome
- 160s 成片下载完成后 capture+encode 仅 ~2min，慢只在下载
