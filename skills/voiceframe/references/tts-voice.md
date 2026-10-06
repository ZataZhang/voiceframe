# 配音生成（bl TTS）

本参考描述百炼配音实现，适用于项目选择百炼时。模型和音色是既有偏好，用户可指定其他服务；其他服务的调用方式与限制按其规范处理。

## 标准配置

| 项 | 值 |
|---|---|
| CLI | `bl`（阿里云百炼） |
| 模型 | `qwen-audio-3.1-tts-flash` |
| 音色 | `xunanchuan_v3.1`（许南川，清亮自然 · 旁白/新闻播报） |
| 格式 | wav / 24000Hz |

音色由用户在 2026-10-07 四选一试听确定（同句「1988年，日本握有全球半导体的一半」，24kHz wav 对比许南川 / 安明远 / 白安然 / 龙三叔）。

## 调用形式

```bash
bl speech synthesize \
  --model qwen-audio-3.1-tts-flash \
  --voice xunanchuan_v3.1 \
  --text "口播文本" \
  --format wav --sample-rate 24000 \
  --out out.wav
```

长文本走文件：

```bash
bl speech synthesize --model qwen-audio-3.1-tts-flash --voice xunanchuan_v3.1 \
  --text-file script.txt --format wav --sample-rate 24000 --out out.wav
```

## 批量生成：必须带重试

**dashscope TTS 侧存在偶发 HTTP 400**，同一模型/音色/文本会时好时坏，CLI 不重试、直接原样抛出。批量跑必须每段重试 3–4 次。

已观察到的错误形态（全都归为偶发，不要据此改配置）：
- `url error, please check url！`
- `[cosyvoice:]Engine error [411]: TTS speak operation failed`
- `[cosyvoice:]Engine return error code: 418`

**这不是权限问题、不是参数问题、也不是文本超长。** 判断依据：同期文本模型调用正常、`base_url` 正确、同参数重试即成功。

2026-10-07 曾因此误判为「账号未开通语音权限」，浪费一轮排查 —— 遇到这三个错误码，先直接重试，不要往权限方向查。

## 已验证的参数事实

- 单次请求 **841 字通过**，不必按 600 字切段
- `wav` / `24000Hz` 可用
- `--language zh` 可用（也可省略）
- 返回直连 OSS 的 `audio_url`（48h 有效），本地 `--out` 同时落盘

## 语速与时长估算

许南川实测约 **279 字/分**（4739 字 → 1017s）。写完稿子先算一下字数，就能预估时长。

需要精确控制总时长时用 `--rate`（0.5–2.0）：

```bash
bl speech synthesize ... --rate 0.88 ...
```

注意：整体降速会压平「断言加重、数字放慢」的抑扬层次。差几分钟时，优先补写内容而不是降速。

## 拼接

```python
from pathlib import Path
fs = sorted(Path(outdir).glob("*.wav"))
Path("/tmp/fflist.txt").write_text(
    "".join(f"file '{f.resolve()}'\n" for f in fs))
```

```bash
ffmpeg -y -f concat -safe 0 -i /tmp/fflist.txt -c copy master.wav
```

段落间需要留白时，在 `concat` 列表里插入静音文件，而不是让 TTS 停连。

## 音色家族陷阱

**音色不能跨模型家族混用**。百炼有至少两份音色文档，查表前先认准页面：

| 模型家族 | 音色命名 | 含 Kai？ |
|---|---|---|
| `qwen3-tts-flash` | 英文短名：`Cherry`/`Ethan`/`Serena`/`Kai`… | ✅ 有 `Kai`(凯) |
| `qwen-audio-3.1-tts-flash` | 拼音长 ID + `_v3.1`：`xunanchuan_v3.1`/`anmingyuan_v3.1`/`baianran_v3.1`… | ❌ 没有 |

用户若指名 `Kai`，那是在指 `qwen3-tts-flash`，不能用本技能的模型去满足 —— 要么改模型，要么回到 `qwen-audio-3.1-tts-flash` 重新选音色。

查音色列表：

```bash
bl speech synthesize --list-voices --model qwen-audio-3.1-tts-flash
```

该模型无内置列表，命令只会回一条官方文档链接。实际列表在
`https://help.aliyun.com/zh/model-studio/qwen-audio-tts-voice-list`。

## 内置实现

使用 [gen_voice.py](../scripts/gen_voice.py) 抽取 `SCRIPT.md` 缩进口播文本、按段生成 WAV，并测量真实时长生成 `audio_meta.json`。支持配置模型、音色、尾部留白，以及输入指纹缓存与有上限的瞬态错误重试。先 `--dry-run` 检查，确认后再调用收费服务。详见 [模板使用](templates.md)。

## 无网/无 key 的应急备用路径：macOS `say`

**备用，不是标准路径** —— 百炼不可用且用户接受该备用音色时使用，成片音色会不同。

```bash
say -v Tingting -r 190 -o NN.aiff "台词…"    # 每条 SCRIPT line 一个文件
ffmpeg -i NN.aiff -ar 44100 -ac 1 assets/voice/NN.wav
ffprobe -v error -show_entries format=duration -of csv=p=0 NN.wav   # 拿准确时长
```

- zh_CN 可用：Tingting（女，最正）、Eddy/Flo/Reed 等（偏玩具音），**没有正式男声**
- `-r 190` ≈ 中文 4.5 字/秒；` SCRIPT.md 逐 Line 生成即可对齐帧
- 无词级时间戳 → **放弃 karaoke 字幕**（captions off），靠画面 kinetic type 承担
- Kokoro（`hyperframes tts`）中文在本机曾卡死（phonemization 挂起），且模型下载被限流到 ~16KB/s —— 双重不可用，别浪费时间

## 自备音频索引

自备音频可以按 Line 编号放入 `assets/voice/NN.wav`，运行内置脚本的 `--existing-audio` 模式测量时长。手写最小索引的示意：

```json
{ "bgm": null,
  "voices": [ { "frame": 1, "path": "assets/voice/01.wav" }, … ],
  "sfx": [] }
```

- 本模板没有外部 assembler 依赖；按索引在所选应用中放置音轨。默认场景留白为 0.7s，可按节奏调整
- `check` 会对每个 voice 报一条 `clip_media_fit` warning（媒体短于槽位）—— 这是刻意的呼吸空间，**预期内，别修**
