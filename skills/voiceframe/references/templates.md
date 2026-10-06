# 内置模板与工具

模板随 skill 分发，路径相对于 skill 根目录。无需外部示例仓库。Python 工具只依赖标准库；音频测量需 FFprobe，实际配音还需已配置的 `bl`。

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
