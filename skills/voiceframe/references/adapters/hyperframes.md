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

## check 门禁的「几何模型」

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

## preview 优先，render 最后

**1007s / 67 帧的成片，`preview` 迭代、`render` 只跑一次。** render 要 13m50s（`-w 3`：capture 10m26s + encode 1m59s + assemble 38s），改一帧就重跑 14 分钟；而 preview 是浏览器实时播放，改完刷新就更新。

```
npx hyperframes preview    # 常驻后台，改文件自动重载
npx hyperframes preview "<项目绝对路径>" --stop
```

Studio 在 `http://localhost:3003/#project/<project>`（project 名取 `package.json` 的 `name`）。

### 必须硬刷新浏览器

Studio 会缓存已加载的 composition。**删掉/替换帧文件后普通刷新可能仍显示旧内容**，必须 Cmd+Shift+R。判断「我改的东西到底生效没有」的方法：直接 `curl` Studio 端口上的帧文件，grep 一个新加的标记，确认服务端返回的是新内容，再去要求用户硬刷新。

### 遗留文件会污染 Studio

批量生成帧后**立刻删掉上一批的旧帧文件**。Studio 的帧列表会把目录里所有 HTML 都列出来（未必只列 index 引用的），用户可能点开一个早已不参与渲染的旧文件，然后误报「我改的东西没生效」。同理，`hyperframes lint/check <file>` 只接受**目录**，不接受单个文件路径。

## 长片铺素材：文案主导会拍成文字墙

**只做「分镜里的图解」几乎必然做成满屏文字。** 一次 20 分钟 / 67 帧的初稿全是「巨字 + 标注 + 图解」，被要求改混剪。

**成片必须以真实画面承载，文字降到 30% 以下。** 「低密度、一帧一陈述」的设计原则不等于「一帧只有字」—— 低密度指的是**元素少**，不是**没有图像**。

### 文字帧判据

写分镜时逐帧问：**这一帧去掉所有文字后还剩什么？** 如果答案是「什么都没有」，这一帧就是文字墙。

### 免费实拍素材来源

| 站点 | 可用性 |
|---|---|
| **Mixkit** | ✅ 直链可下，无需 API key |
| Coverr | ✅ 可达 |
| Pexels / Pixabay | ❌ 403 挡爬虫 |

Mixkit 直链模式（详情页 slug 里的数字即video id）：

```
https://assets.mixkit.co/videos/<id>/<id>-720.mp4     # 720p，单条 4–12MB
https://assets.mixkit.co/videos/<id>/<id>-1080.mp4    # 1080p，单条可达 185MB
```

抓取分类页拿slug 列表，再逐个拼直链批量下。**720p 足够**：progressive JPEG 截图/网页视频最终都是 720p 观感，1080p 只在源足够锐利时才值那 20 倍体积。

**下载前先把 id 写进素材库台账。** id 拼 URL 只要三秒，不记就永久丢失，只剩一个被截断的英文 slug（`b19-close-up-of-electronic-circu` 这种），既查不回原页也无法确认许可。批量下的时候先存下id 与详情页 URL，再开始下载。

清单要按**语义位置**分组，不是按外观（`city` / `circuit` / `data` / `code` / `abstract` / `office`），这样按帧号轮转时同一主题不会连续出现。

**素材放仓库级共享库，不要每个项目各下一份。** 见[制作与交付](../production.md)的「素材来源当场记」。项目用软链接指过去，`frames.config.json` 的 pools 路径保持相对项目根不变。

### 素材覆盖率要算

`Σ素材时长 / 成片时长` 低于 ~70% 就会被迫循环复用，观感上是明显的重复。下载前先按目标时长算缺口，别下十几条就开工。

## 调色：不要用 grayscale「统一」

**「统一色调」≠「压成黑白」。** 模板里给所有素材写了 `filter: grayscale(1)`，理由是「压掉杂色只保留品牌色」—— 结果 44 条素材全部变成黑白，被直接指出「视频怎么都是黑白的」。素材原色（霓虹、数据中心蓝、电路板青绿）本来就有信息量，压掉是净损失。

正确做法 —— **降饱和 + 压暗，保留色相**：

```css
/* split 版式：文字区占 38%，画面可以稍亮 */
filter: saturate(0.62) contrast(1.16) brightness(0.66);
/* full 版式：满屏压更多，文字压在上面 */
filter: saturate(0.58) contrast(1.18) brightness(0.5);
/* 彩色照片 */
filter: saturate(0.5) contrast(1.05) brightness(0.72);
```

`saturate(0.5~0.6)` 既压掉杂色又保留语义色，与设计系统不冲突；`brightness` 压到 0.5–0.7 保证白字可读。**确需中性色时用 `grayscale(0.2)` 局部，不要上1.0。**

## broll 版式：半屏元素，不是背景板

**禁止「broll 铺满全屏 + 居中压字幕」** —— 这是最低效的混剪，画面在动但没人看，因为观众的眼睛无处可落。

四种可用版式（`split` 29 帧 / `full` 19 / `chapter` 10 / `data` 5 / `photo` 4 跑通的一组配比）：

| 版式 | 结构 | 用在 |
|---|---|---|
| `split` | 左 62% 视频 + 右 38% 深色文字区，1px hairline 接缝，右侧渐变遮罩过渡 | **默认版式**，大多数帧 |
| `full` | 满屏视频 + 左侧线性暗角 scrim，文字压左侧 | 纯抽象纹理素材 |
| `chapter` | 纯色场 + 巨字（橙场用 ink 字，深场用 cream） | 章节卡，全片 6–10 个 |
| `data` | 图表 SVG 分层揭示 + 窄标题栏 | 有原始数据图表时 |
| `photo` | 满屏照片 + 极慢 Ken Burns（12s 推 6%） | 实拍照片帧 |

**满屏 broll 只在素材本身是抽象纹理、且配色与设计系统同源时用**（例：橙色光斑 + 黑立方体隧道）。这类素材压字是强化而非低效。

## 字幕必须做，位置随版式

用户看完第一版成片的第二个反馈是「没有字幕」。**旁白视频默认需要硬字幕**，不是可选项。

字幕切分规则：按 `。！？；` 切主块 → 超过 18 字按 `，、` 再切 → 仍超长的硬拆。**单块 ≤18 字**。

**时间基准必须是 ASR 的实测句边界，不是字数估算。**`gen_cues.py` 已改为只走 ASR（输出 `cues-asr.json`）：估算基准与真实语速不同，长片累积到几秒就肉眼可见不同步（见下方「字幕不同步」的教训）。

```python
# 关键：一条 ASR 句拆成多块时，按字数瓜分该句时长——
# 否则所有块共用同一个 t，会同时出现在画面上
span = (s['end_time'] - s['begin_time']) / 1000
```

版式差异：

```css
/* split：字幕只占右侧 38%，绝不压画面 */
.subs { left: 62%; bottom: 78px; }
.sub-line { max-width: 640px; font-size: 31px; text-align: left; }
/* full / photo / data / chapter：全宽居中 */
.subs { left: 0; right: 0; bottom: 92px; }
.sub-line { max-width: 1340px; font-size: 42px; text-align: center; }
.sub-line { text-shadow: 0 3px 14px rgba(0,0,0,.92), 0 1px 3px rgba(0,0,0,.98), 0 0 22px rgba(0,0,0,.7); }
```

三重 text-shadow 是白字压实拍画面可读的前提。`z-index: 40` + `pointer-events: none`。

`split` 的字幕覆写必须写在基础 `.subs` 规则**之后**（同优先级靠后），否则被基础规则覆盖 —— 表现为「字幕生成了但看不见」。

## 批量生成帧的工程做法

长片可用内置 `build_frames.py`：读取 `audio_meta.json`、字幕、标题和素材配置，生成子帧与 `frames.json`，再按清单填写入口模板。当前未提供自动组装入口脚本，完整参数见 [模板使用](../templates.md)。

生成时的两个必查项：

- **帧内 `data-composition-id` 必须与 index 里的完全一致**，否则 lint 报 `timeline_id_mismatch`（注册名 `"01-city"` 对不上 `"01"`）。统一用纯数字 `"{cid}"`
- **生成器里的 f-string 与 `replace` 容易出静默 bug**（如 `f"id=\"x-{t:.2f}\".replace('."','')` 会把 f-string 提前求值）。批量改文件前先备份，修完用脚本校验结构（帧数 / 字段完整 / 时长闭合）而不是肉眼扫

## 校验脚本要按 Frame 块解析

`re.findall(r'^- duration: ([\d.]+)s', s, re.M)` 会把 frontmatter、chapter map 表格里的数字一起数进去，得出「68 帧 / 时长 1022s」这种假报错。正解是按块切：

```python
for m in re.finditer(r'^## Frame (\d+).*?\n(.*?)(?=^## |\Z)', s, re.M | re.S):
    d = float(re.search(r'^- duration: ([\d.]+)s', m.group(2), re.M).group(1))
```

## snapshot 抽帧会骗人

**抽帧采样可能恰好落在两句字幕的间隙**，看起来「字幕没生效」，实际是采样时机问题。验证字幕要按 cue 的具体 `t` 值定点抽帧，或把采样密度调到足以覆盖最短字幕时长。

## 从SCRIPT 直接建帧，不必先写 STORYBOARD（方法论类内容）

有完整 `SCRIPT.md` + 实测 `audio_meta.json` 时，**可以跳过 STORYBOARD 直接建帧** —— 时间轴由音频决定，场景标题从 `SCRIPT.md` 的 `## Line N — 标题` 直接取。省掉一轮「分镜表 ↔ 时间轴」的双向同步。

实测：37 句 3549 字 → 64 帧 / 865s，平均 13.5s/帧，版式分布 split 34 / full 18 / chapter 9 / data 3。

切帧规则（与句长挂钩，不看字数）：

```python
k = 1 if dur <= 20 else (2 if dur <= 38 else 3)
```

### 帧标题的清洗

`SCRIPT.md` 的标题常带内部标记，直接上屏会露出工程痕迹：

```
## Line 6 — 另一个人 (Frame 4)   →   标题显示「另一个人 (Frame 4)」  ✗
```

生成时必须剥掉尾部标记与全角括号后缀：

```python
raw = re.sub(r'\s*\(Frame[^)]*\)\s*$', '', title)
raw = re.split(r'[（(]', raw)[0].strip()
```

副题同理——**不能与标题重复**。取旁白里第一个不等于标题的完整句：

```python
parts = [x.strip() for x in re.split(r'[。！？；]', voiceover) if len(x.strip()) >= 6]
sub = next((c[:40] for c in parts if c not in title), '')
```

副题在实拍画面上必须加底衬，否则压不住：

```css
.sub { background: rgba(17,17,17,0.72); padding: 12px 16px; border-left: 2px solid var(--orange);
       color: var(--cream); font-weight: 500; }
```

## 素材的色相冲突：降饱和压不住，必须换素材

`saturate()` 只能压彩度，**压不掉色相**。紫红/洋红调素材（彩色数据 HUD、crypto 图形、霓虹营销页）在橙+黑系统里即使 `saturate(0.26)` 仍然是明显的一块紫 —— 与品牌橙直接冲突。

**判断标准**：素材里有没有与品牌色竞争的第二个高饱和色相。有就换素材，不要试图用滤镜救。

做法：在素材池常量里直接注释掉冲突项，并在池旁写明原因，让后来者知道是筛过的：

```python
# 剔除紫红调素材（b10/b11/b20/b21/b26/b31）—— 与橙+黑系统冲突，
# 降饱和也压不住色相，只能换素材。
"office": ["b12-…", "b13-…", "b16-…"],
```

遇到这类素材，`saturate` 的安全下限是 0.26–0.30；再低画面会发灰失去质感。

## 系列标签是内容不是装饰

帧里的 `kicker`（左上角系列标识）必须**按项目改**，不要沿用模板或上一个项目的文案。跨项目复用生成脚本时最容易漏掉这一项 —— 出来的片子会带着上一个系列的标签。生成脚本里用项目名拼：

```python
f'学不完才是常态 · AI 时代的学习判断'# 换项目时必改
```

## 字幕必须用 ASR 反推，不能按字数估算

用户看完第一版给的唯一反馈之一是「字幕不同步」。**按字数比例分配时间轴必然会漂移** —— 估算基准与真实语音语速不同，长片累积到几秒后就肉眼可见。

**正确做法：先渲染音频，再用 ASR 反推字幕时间。** `gen_cues.py` 已封装这一步，直接调用即可（见[模板使用](../templates.md)）；下面是它内部的命令，用于理解或排错：

```bash
bl speech recognize --url assets/voice/master-oneshot.wav \
  --model fun-asr --language zh --out asr-raw.json
```

`transcripts[0].sentences[]` 直接给出毫秒级句边界（`begin_time` / `end_time` / `text`），14 分钟音频约 145 句。这是唯一可靠的时间基准。

流程因此变成：**TTS → ASR → 字幕 → 建帧 → 渲染**，而不是「估算时间轴 → 建帧 → 渲染」。

### 一条 ASR 句拆多块时要瓜分时长

ASR 句子常超过字幕长度上限（20 字）。**如果拆出来的多块共用同一个 `t`，它们会同时出现在画面上**：

```python
pieces = split_piece(text, max_chars)
span = (e - b) / 1000
weights = [max(len(x), 1) for x in pieces]
acc = b / 1000
for piece, w in zip(pieces, weights):
    cues.append({'text': piece, 't': round(acc, 3), 'd': round(span * w / sum(weights), 3)})
    acc += span * w / sum(weights)
```

生成后必须校验单调性 —— `monotonic: OK` 才算通过。

### 帧内相对时间只能减一次

字幕 cue 有两套时间基准：全局（ASR 绝对秒）和帧内（相对秒）。`cues_in_window()` 已经换算过一次，如果 `subs_markup()` 里再减一次 `FRAME_T0[n]`，**所有字幕时间都会变成 0**，表现为「所有字幕同时出现」。症状是抽帧看到多条字幕叠在一起。

约定：**进入 `subs_markup()` 的 cue.t 必须是帧内相对时间**，函数内部不再做换算。

## 上屏标题必须是论点，不是结构标记

第二个致命问题：把 `SCRIPT.md` 的 `## Line N — 标题` 直接当上屏标题。那些标题是**写作时的结构标记**，观众看不懂：

```
## Line 6 — 另一个人 (Frame 4)      → 观众看到「另一个人」，完全不知道在讲什么
## Line 14 — 四种迹象 (Frame 8)      → 观众看到「四种迹象」，不知道是哪四种
## Line 19 — 第一个：三个月 (Frame 9) → 这是提纲，不是结论
```

配上不相干的 broll 更糟 —— **画面在动，标题在传递混乱，观众无处可落**。

### 判据

标题必须能回答「所以呢」。结构标记一律不上屏。

| SCRIPT 标题 | 上屏标题 |
|---|---|
| 另一个人 (Frame 4) | 重要的知识 / 是相对目标说的 |
| 四种迹象 (Frame 8) | 任务 + 缺口 + 后果 |
| 两个例子 (Frame 3) | 值得知道 / 不等于现在深入学 |
| 结语 (Frame 19) | 不是追上所有更新 / 是多一点把握 |

把映射写成独立的 `titles.json`（Line → 标题或 `None`），生成时读它，别把映射硬编进生成器 —— 硬编的版本会漏掉句号对齐检查。

```python
titles = {1: None, 2: '学不完不是错觉', 3: '该对能力缺口警觉\n不必对清单焦急', ...}
```

`None` 表示该句不上标题（纯画面 + 字幕）。**一句话拆成多帧时，只有第一帧上标题**，其余留空，否则同一个标题连着出现两次。

### 映射必须与SCRIPT 句号对齐

写完映射先断言，避免多余键静默生效：

```python
assert set(titles) == {t['line'] for t in timeline}
```

（实测写多了 15 条映射，就是靠这个断言发现的。）

## f-string 里不要放JS 注释

Python f-string 生成 JS 时，`{{}}` 转义和注释混在一起会产生 `invalid_inline_script_syntax`。踩了两次的形态：

```python
# ✗ 注释里的花括号和中文标点一起进了 JS，语法直接崩
if ({n} == 1):
  // 开场帧不做揭开动画：第 0 秒必须已经有画面，否则片头是黑的

# ✓ 先算成纯 JS 布尔常量，注释留在 Python 侧
var opening = {str(n == 1).lower()};
if (opening) {{
```

## 开场第 0 秒必须有画面

第 0 秒抽出来全黑 —— 视频元素刚创建，首帧还没解码。三个改动一起做才有效：

**`preload="auto"` 只能给开场帧加，绝不能全局加。** 全局加会让渲染器为每个视频预提取帧（实测 52 个视频 → 提取 19032 帧、`authoredTimedClipCount: 121`），浏览器直接超时：

```
[FrameCapture] window.__hf not ready after 45000ms.
Page must expose window.__hf = { duration, seek }.
```

而且 `check` 门禁**查不出这个问题** —— 只有真渲染才暴露。生成器里按帧号条件注入：

```python
muted
playsinline{' preload="auto"' if n == 1 else ''}
```

```js
var opening = true;
if (opening) {
  tl.set(video, { opacity: 1 }, 0);   // 不是 fromTo，直接落到可见
}
```

`tl.fromTo(video, {opacity: 0}, {opacity: 1, duration: 0.5}, 0)` 在 t=0 时首帧仍未解码，抽帧照样是黑的。`tl.set()` 无过渡、无补间，才保证第 0 帧可见。

验证方式：`snapshot --frames 12` 后直接看 `frame-00-at-0s.png`，不要只看 contact sheet（采样点通常不在 0）。

## 「该不该显示」和「能不能显示」必须分开（生成器陷阱）

用户报「有一段是空的」，追下去是：某个句子的标题**整句丢失**了20 秒。根因是把两件不同的事混用一个变量：

```python
# ✗ 一个 None 同时表达「这句不需要标题」和「这个版式不显示标题」
title = None if ln in titled else titles.get(ln)
if title: titled.add(ln)
if style == "data": title = None      # ← 这一句顺手把「已消费」标记也带走了
```

一句 20 秒的旁白拆成两帧：第1 帧是图表（自带标题文字，屏上不再重复），第 2 帧是普通画面。第 1 帧把标题消费掉了却自己不显示，第 2 帧就以为「这句已上过标题」而留空 —— **整句无标题**。

修法：把「归属」和「渲染」分开，用pending 传递。

```python
if style == "data":
    pending_title = title      # 交给下一帧接手
    title = None               # 自己不显示
elif pending_title is not None:
    title, pending_title = pending_title, None
```

### 必须在生成后断言

这类 bug 门禁查不出来（check 只看单帧，不看跨帧序列）。生成脚本末尾强制校验：

```python
shown = {}
for m in meta:
    if m.get("screen_title"):
        shown[m["line"]] = shown.get(m["line"], 0) + 1
lost = [ln for ln, v in titles.items() if v and ln not in shown and ln not in exempt]
dup = {ln: n for ln, n in shown.items() if n > 1}
if lost: raise SystemExit(f"标题整句丢失: {lost}")
if dup:  raise SystemExit(f"标题重复上屏: {dup}")
```

**一个渲染决策不能连带改变数据归属。** 凡是「消费/标记」与「显示/隐藏」共用的变量，都要拆开。

## 跨媒介素材必须先做风格迁移

文章配图、网页截图、PDF 导出的图表 —— 这些是为**白底阅读**做的，直接贴进深色视频就是一块刺眼的补丁。

**不要重新生成，也不要加边框衬底。** 最省力且效果最好的是**把底色改成目标底色**，让边界自然消失：

```python
PALETTE = {
    '#f7f5f0': '#111111',   # 网页浅底 → ink-black（与画面同色，边界消失）
    '#25364a': '#f0ece5',   # 深字 → cream
    '#5c7180': '#888880',   # 次级 → cream-muted
    '#c0c9ca': '#282826',   # 弱线 → line
    '#e3a86e': '#e85d26',   # 橙块 → 品牌橙
}
```

三步：换色板→ 字号放大 1.5×（网页靠字小精致，视频是远看）→ 裁掉 viewBox 四周空白（网页图表留白多，不裁会显得图形偏小偏移）。

顺手删掉图内的 `<text class="title">` 与 `class="small"` —— 屏上已有左上角标签和底部图注，重复三份会让视觉重心偏移。

裁 viewBox 时注意 SVG 元素结构不止一种，实测要覆盖：

```python
for pat in (r'<circle[^>]*cx="([\d.]+)"[^>]*cy="([\d.]+)"[^>]*r="([\d.]+)"',
            r'<rect[^>]*x="([\d.]+)"[^>]*y="([\d.]+)"[^>]*width="([\d.]+)"[^>]*height="([\d.]+)"',
            r'<line[^>]*x1="([\d.]+)"[^>]*y1="([\d.]+)"[^>]*x2="([\d.]+)"[^>]*y2="([\d.]+)"'):
    ...
```

只用 `<circle>` + `<rect>` 会漏掉用 `<line>` 画坐标轴的象限图，裁剪直接抛 `min() arg is an empty sequence`。

## 版式参数必须跟着栏宽走

五种版式的标题栏宽从 290px 到 1700px 不等，却共用同一套标题字符串 ——`<br>` 硬拆的行在窄栏里会二次折行，孤字掉到第三行（「值得知道 / 不等于现在深入 / 学」）。

排版参数与内容格式要一起按版式分支，不要指望一套默认值通吃。

## 同一句拆多帧时，第二帧要有不同的承载（quote 版式）

「一句话只上标题一次，后续帧留纯画面+字幕」是错的判断。实测25/64 帧（39%）这样处理，用户反馈「留空不太好」—— 画面在动、字幕在跑、什么都没有，观感就是空。

**延续帧改用引文版式**：满屏视频 + 左侧暗角，左边一条橙线做引文引导线，42px cream 粗体放整句旁白（按标点断行，最多 4 行）。

```css
.q { position: absolute; left: 110px; top: 260px; width: 1000px;
     border-left: 3px solid var(--orange); padding: 8px 0 8px 34px; }
.q-line { font-size: 42px; font-weight: 700; line-height: 1.34; color: var(--cream);
          text-shadow: 0 3px 16px rgba(0,0,0,0.9); }
```

这个改动**一箭三雕**：
- 上部空间被占据，不再空
- 原来那条孤立的装饰横线/竖线变成了引文的引导线，有了依附
- 下部留白成为「给引文呼吸的空间」，而不是「忘了放内容」

当前内置脚本从本帧字幕窗口提炼引文，限制最多四行，并保留逐条定时字幕。引文属于摘要，不能替代完整字幕；发布前检查两者位置与内容。

### 引文行数必须设上限

不设上限时某些句子会切出 8 行，直接压进底部字幕区触发 `content_overlap`：

```python
qlines = qlines[:4]     # 引文是精炼，不是把整段搬上屏
```

## 新增版式时，CSS 必须是「基础布局 + 独有元素」的完整集

加 `quote` 版式时只把 `full` 的 CSS 改了个名字、另加 `.q`，结果**漏了 `.v` / `.scrim` / `.hr` / `.kicker` 的定义**。这些类没有样式 → 视频没有暗角遮罩 → 文字直接压在亮画面上 → 对比度掉到 **1.07:1**（门禁报了一整串）。

```python
QUOTE_CSS = """      /* 必须先有基础布局（与 full 一致），再加独有元素 */
      .v { position: absolute; inset: 0; overflow: hidden; }
      .v > video { ... }
      .scrim { ... }
      .hr { ... }
      .kicker { ... }
      .q { ... }          # ← 只有这一条是新的
"""
```

**规则：复制一个已有版式改写时，把基础布局整段复制过来，只追加差异。** 漏一条的表现是「元素存在但样式全无」，比元素缺失更难查。

## 版式判定所依赖的变量，必须在判定之前算好

引文判定用 `cs`（该帧的字幕窗口）来确认「这一帧有没有内容」，但 `cs` 的计算写在版式判定之后 —— 表现是 `NameError: local variable 'cs' referenced before assignment`。

生成器的执行顺序要显式排好：**帧起始秒 → 字幕窗口 → 版式判定 → 标题归属 → 生成 HTML**。同一批变量反复挪位置很容易漏。

自查：版式判定里引用的每个变量，都能在上方找到赋值。

## 用内置脚本，别手写生成器

`scripts/build_frames.py` 已把这几轮的坑固化为代码 + 校验：批量建帧、五种版式、ASR 字幕挂载、标题归属、素材轮转、深色图表。

```bash
python3 /path/to/voiceframe/scripts/build_frames.py --project /path/to/video --dry-run
```

详见 [模板使用](../templates.md)。自己写生成器的话，至少校验句号对齐与标题不丢不重，并报告素材重复度—— 这三类 bug 门禁都查不出来。
