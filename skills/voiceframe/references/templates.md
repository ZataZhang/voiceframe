# 内置模板与工具

模板随 skill 分发，路径相对于 skill 根目录。无需外部示例仓库。Python 工具只依赖标准库；音频测量需 FFprobe；AI 配音与可选 ASR 需已配置的 `bl`，整段 AI 配音的辅助测量还需 FFmpeg 与 NumPy。

## 初始化

```bash
python3 /path/to/voiceframe/scripts/init_project.py /path/to/new-video
```

目标目录必须不存在，工具不会覆盖已有项目。默认输出需求简报、设计系统、分镜、口播与 `PRODUCTION.md`，不预选制作应用。填写 Markdown 后审阅，保留确认记录。

## 配音与准确时长

```bash
python3 /path/to/voiceframe/scripts/gen_voice.py --project /path/to/new-video --dry-run
# 剧本确认后执行：会调用 bl 生成配音
python3 /path/to/voiceframe/scripts/gen_voice.py --project /path/to/new-video
# 自录音频按 Line 编号提供 assets/voice/01.wav 等文件：不调用 bl
python3 /path/to/voiceframe/scripts/gen_voice.py --project /path/to/new-video --existing-audio
```

可用参数：`--script SCRIPT.md`、`--model`、`--voice`、`--tail 0.7`、`--attempts 4`。口播仅取 `## Line N` 下四空格缩进文字；Line 编号必须唯一，每段非空。`(Frame N)` 可将多段口播映射到同一帧，未填写则以 Line 编号作为 Frame 编号。

AI 配音缓存用文本、模型、音色及采样率的指纹判定，改稿后会重新生成。写入新音频成功前保留旧文件；某段失败会停止，并保留已完成段落，下次可继续。索引仅在全部成功后更新，失败后不要把旧索引当作最新结果。

`audio_meta.json` 包含 `voices`、`bgm`、`sfx`、总 `duration`；每段有 `line`、`frame`、`path`、`start`、`audio_duration` 与含留白的 `duration`。这些 start 是顺序播放独立音频段的时间，不能用于对齐另一条独立录制或独立合成的母带。背景音乐和音效默认为空。

## 可选 HyperFrames 模板

仅在选择 HyperFrames 时附加专属骨架：

```bash
python3 /path/to/voiceframe/scripts/init_project.py /path/to/new-video --adapter hyperframes
```

详见 [HyperFrames 适配指南](adapters/hyperframes.md)。将 `.template` 复制为 `.html` 后替换变量，准备本地 GSAP 和字体并通过该应用的检查。模板没有可直接交付的成片。

## 其他应用与跨应用流程

在 `PRODUCTION.md` 记录各阶段应用、输入输出、版本与交接方法。分镜的 `src` 可以是媒体路径、应用中的场景或序列标识，不要求 HTML；设计系统不要求 GSAP。

使用 [制作与交付](production.md) 的通用约定安排素材、音轨与时间轴。音频索引可供程序读取或人工对齐，但没有保证第三方应用自动导入；按目标应用实际能力选择操作方式，并验证结果。

## 内置建帧脚本

`build_frames.py` 读取 `audio_meta.json`（`timeline` 或 `voices`）、字幕和标题映射，输出子帧 HTML 与 `frames.json`。整段母带的 Line 边界来自比例估算，需先听音校对；ASR 只校准字幕句边界，不会自动校准 Line 边界。

以下命令在本仓库根目录运行；将 `../my-video` 替换为项目路径：

```bash
# 1. 音频：先预览，确认脚本及百炼调用授权后去掉 --dry-run 执行
python3 skills/voiceframe/scripts/gen_voice.py --project ../my-video --mode oneshot --dry-run

# 2. 可选：SVG 图表转换。保留原图，彩色数据标记保持原色
python3 skills/voiceframe/scripts/darken_figures.py --input ../my-video/assets/figures --output ../my-video/assets/dark

# 3. 默认离线字幕：按实测音轨时长分配文本；发布前需试听校对
python3 skills/voiceframe/scripts/gen_cues.py --project ../my-video
# 可选 ASR：经授权后调用百炼，母带默认 assets/voice/master-oneshot.wav
python3 skills/voiceframe/scripts/gen_cues.py --project ../my-video --asr

# 4. 配置实际素材池和 titles.json 后建帧。离线模式默认读取 cues.json
python3 skills/voiceframe/scripts/build_frames.py --project ../my-video --dry-run
python3 skills/voiceframe/scripts/build_frames.py --project ../my-video
# ASR 模式改用 --cues cues-asr.json

# 5. 按 frames.json 填写入口模板，再在项目目录运行 lint / check
```

`darken_figures.py` 仅处理 SVG 的常见中性色与绘制属性；嵌入图片、渐变和外部 CSS 等复杂图表须检查转换结果。输出目录必须与原图目录分开。

入口模板的 host `id` 与 `data-composition-id` 使用 `frames.json` 中的 `composition_id`，`data-start` 使用 `t0`，`data-duration` 使用 `dur`，`data-composition-src` 为 `compositions/frames/` 加 `file`。总时长取所有帧结束时间的最大值；旁白按 `audio_meta.json` 加入音轨（母带只加入一次）。仓库目前不提供自动组装入口脚本。准备本地 GSAP 和字体后，在项目目录执行 `npx hyperframes lint`、`npx hyperframes check`，再抽帧检查。

### 项目配置

`frames.config.json`（制作前配置真实素材；不内置示例媒体）：

```json
{
  "chapters": {"10": ["二、检验", "焦虑要不要紧"]},
  "figures": {"assets/dark/fig1.svg": {
      "label": "图 01 · 标题", "caption": "图注。", "frames": [8]}},
  "pools": {
    "study": ["n5-notes.mp4", "n9-drawing.mp4"],
    "book": ["n3-reading.mp4"],
    "abstract": ["n4-texture.mp4"]
  },
  "quote_pool": "abstract",
  "rotation": ["study", "book"],
  "series_label": "系列名 · 副题"
}
```

`pools` 是**按语义分组**的，不是按外观 —— 讲学习方法就配书本笔记，配服务器机房是语义错位。分组还决定重复度：池内素材用满一轮才换下一条，脚本会报告最大重复次数，`>= 3` 就该补素材。

### 脚本内建的校验

脚本提供以下检查；具体布局与对比度仍由 HyperFrames 门禁和抽帧确认：

| 校验 | 挡住的问题 |
|---|---|
| `titles.json` 与 timeline 句号必须一致 | 多余键静默失效（实测一次写多 15 条） |
| 每句标题要么出现一次要么刻意不出现 | 整句标题丢失（跨帧归属被渲染决策带跑） |
| 同句多帧不能显示完全相同文本 | 标题重复上屏 |
| 栏宽 vs 标题字数（警告） | 提示长标题需要排版校对 |
| 素材最大重复次数（提示） | 池太小导致同一素材反复出现 |
| 时间轴与素材存在性 | 时间重叠、无效时长、缺失素材 |

### 版式

`split`（左视频右字）/ `full`（满屏+左暗角）/ `quote`（引文式，填同句延续帧的空白）/ `chapter`（橙场章节卡）/ `data`（图表）/ `photo`（满屏照片）。

每句标题只显示一次；延续帧可使用 `quote` 提炼当前字幕，引文不能替代逐句字幕。所有版式保留字幕，并跨帧截断其显示时间。`photo` 可供手工调用建帧函数使用，批量脚本目前自动选择其余五种版式。

CSS 都定义在脚本内的 `STYLE` 字典里，**新增版式时把基础布局整段复制再追加差异** —— 只加独有元素会漏掉 `.v` / `.scrim` 等，表现为「元素存在但样式全无」，对比度掉到 1.07:1。
