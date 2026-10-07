# 使用指南

[← 返回 Voiceframe](../README.md)

以下命令均从仓库根目录执行。

## 快速开始

### 1. 安装 Skill

将整个 [`skills/voiceframe/`](../skills/voiceframe/) 文件夹复制到 Agent 的 Skill 目录，保留其中的脚本、模板与参考文档。

例如，在 Codex 的默认个人 Skill 目录中安装（从本仓库根目录执行，目标目录应尚不存在）：

```bash
cp -R skills/voiceframe ~/.codex/skills/voiceframe
```

然后在支持 Skill 调用的 Agent 中输入：

```text
$voiceframe 把这篇文章做成一个 3 分钟的中文讲解视频。
先给我剧本和分镜草稿，画面风格简洁，使用 AI 旁白。
```

也可以只指定一个阶段：

```text
$voiceframe 根据现有 SCRIPT.md 生成配音，并整理音频时间轴。
```

### 2. 初始化制作项目

以下命令均从本仓库根目录执行。初始化目标目录必须不存在。

```bash
python3 skills/voiceframe/scripts/init_project.py ../my-video
```

生成五份项目文档：

| 文件 | 用途 |
| :--- | :--- |
| `BRIEF.md` | 目标、受众与交付要求 |
| `frame.md` | 画面风格与设计系统 |
| `STORYBOARD.md` | 分镜、画面与场景安排 |
| `SCRIPT.md` | 可直接念出的口播文本 |
| `PRODUCTION.md` | 制作应用、阶段交接与交付记录 |

在 `SCRIPT.md` 中用 `## Line N` 标记段落，口播正文使用 **四个空格缩进**；可用 `(Frame N)` 指定对应分镜：

```markdown
## Line 1 — 开场 (Frame 1)

    一个好的讲解视频，从一个值得回答的问题开始。

## Line 2 — 展开 (Frame 2)

    先把故事讲清楚，再让声音和画面一起向前。
```

### 3. 预览配音输入

```bash
python3 skills/voiceframe/scripts/gen_voice.py \
  --project ../my-video --dry-run
```

`--dry-run` 用于检查剧本解析与调用配置，不会调用配音服务。审阅剧本后，选择下面适合的音轨模式。

## 内置工具

初始化与字幕切分使用 Python 3 标准库。音频时长测量需要 **FFprobe**；AI 配音需要已安装并配置鉴权的百炼 **`bl` CLI**。AI 整段模式的辅助对齐还需要 **FFmpeg** 和 **NumPy**。

### 短片：逐段配音

每个 Line 生成独立 WAV，适合需要逐段修改的短片：

```bash
python3 skills/voiceframe/scripts/gen_voice.py \
  --project ../my-video --mode segment
```

默认使用 `qwen-audio-3.1-tts-flash` / `xunanchuan_v3.1`，可通过 `--model` 和 `--voice` 更改。每段默认预留 `0.7` 秒，可用 `--tail` 调整；指定瞬态错误最多尝试四次。

### 长片：整段母带

对于三分钟及以上的旁白，项目指南要求使用整段模式，以保持叙述连贯：

```bash
python3 skills/voiceframe/scripts/gen_voice.py \
  --project ../my-video --mode oneshot --dry-run

python3 skills/voiceframe/scripts/gen_voice.py \
  --project ../my-video --mode oneshot
```

该模式生成 `assets/voice/master-oneshot.wav`，并额外生成辅助分段音频，按净语音时长比例估算母带中的句子边界，因此会产生额外配音调用。母带总时长为实测值，句子边界仍需试听校对。

### 自备音频：建立索引

按 Line 编号将录音放入项目的 `assets/voice/01.wav`、`02.wav` 等位置，然后运行：

```bash
python3 skills/voiceframe/scripts/gen_voice.py \
  --project ../my-video --existing-audio
```

已有整段录音可使用 `--mode oneshot --existing-audio`，默认读取 `assets/voice/master-oneshot.wav`。此时句子边界按文本字数比例估算。自录音频的降噪与后期方案见[音频后期](../skills/voiceframe/references/audio-post.md)，目前尚未实测。

### 字幕：生成时间块

音轨索引完成后，按标点与字数切分字幕：

```bash
python3 skills/voiceframe/scripts/gen_cues.py --project ../my-video
```

输出 `cues.json`，每块包含文本、开始时间与时长。时间按字数比例分配，适合作为字幕编排起点；默认模式不调用语音识别，发布前需要校对。

可选 ASR 模式使用 `--asr`，需要已配置的百炼 `bl`，调用前确认费用授权。默认识别 `assets/voice/master-oneshot.wav` 并输出 `cues-asr.json`；也可通过 `--audio` 指定音频。ASR 句内拆块仍按字数分配时长，不提供词级强制对齐。

## 制作应用与交付

默认项目模板保持应用中立。你可以使用不同的生成服务、动画框架和剪辑应用，并在 `PRODUCTION.md` 中记录交接约定。

如果选择 HyperFrames，可以在初始化时附带专属模板：

```bash
python3 skills/voiceframe/scripts/init_project.py \
  ../my-hyperframes-video --adapter hyperframes
```

HTML 骨架仍需替换模板变量、准备本地资源并完成制作。具体检查与渲染方式见 [HyperFrames 适配指南](../skills/voiceframe/references/adapters/hyperframes.md)。

其他应用通过通用文档、媒体素材和音频索引交接；目前没有内置自动导入转换器。配音脚本产出的 `audio_meta.json` 与 `cues.json` 是制作中间产物，最终成片需在所选应用中合成、检查并导出。

## 上传与发布成片

可以直接从现有成片开始，无需重新制作：

```text
$voiceframe 用 Edge 把 /绝对路径/final.mp4 上传到抖音，填好标题和封面，先保存草稿。

$voiceframe 把这个已确认的成片发布到抖音和哔哩哔哩，沿用项目里的发布文案。
```

默认使用 Edge，优先复用已有创作者页面。Skill 先检查浏览器连接与登录状态；未登录时请你在浏览器内登录，完成后重新检查并继续。浏览器工具必须支持并能连接所选浏览器；网页发布是操作指南，抖音在 macOS Edge 上已实测上传并进入编辑页，正式发布尚未验证；哔哩哔哩尚未实测，没有内置发布脚本。

“上传”默认一并准备对应封面、标题与作品描述，并保存草稿；明确要求“发布/投稿”时才提交，并区分审核中与已公开。多个平台分别核对账号、文案、封面和设置，将结果记录在 `PRODUCTION.md`。详细约定见 [平台发布](../skills/voiceframe/references/publishing.md)。
