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

## 长稿：整段一次生成，不要逐句分段再拼

**长片口播（≥3 分钟）必须整稿一次请求生成，不要按帧/句切段后concat。**

34 段 × ~145 字 分段生成再拼接，和4898 字整段一次生成，内容完全一样，时长只差 10 秒 —— 但**听感差别是决定性的**。用户的原话：「刚刚生成的每个 frame 直接会有一个大喘气的感觉」。

量化原因（用 ffmpeg `silencedetect` 逐段量首尾静音）：

| | 总时长 | 净语音 | 静音占比 |
|---|---|---|---|
| 分段拼接（34 段） | 1017.12s | 730.62s | **28.2%**（286.5s） |
| 整段生成（1 次） | 1006.96s | — | ~27%（仅句内韵律） |

**分段版每段首尾各有 1–5 秒 TTS 自加的呼吸**（最夸张的一段段首 5.19s、另一段段尾 4.64s），34 次请求累积了近 5 分钟的无谓静音。整段生成把这部分全省了 —— **省下的时长恰好就是「差的那 3 分钟」的答案**。

已验证：4898 字一次请求通过（约 1007s）。所以「按 600 字切段」这条只在**超长单次请求**时才需要，长片的正确切法是**按章节整段生成**，不是按句。

```bash
# 20 分钟口播稿（约 4900 字）—— 一次调用
bl speech synthesize --model qwen-audio-3.1-tts-flash --voice xunanchuan_v3.1 \
  --text-file script-full.txt --format wav --sample-rate 24000 \
  --out master-oneshot.wav
```

代价是**不能单独重录某一句**。折中：先整段生成拿连贯基线 + 准确总时长，确定分镜后只对要改的句子单独生成替换。

## 拿到整段音频后：提取每句时间戳

整段生成后需要知道每句的起止，用来做字幕和帧边界。**不要靠静音计数** —— 母带里 >0.2s 的静音段有 **457 个**，而只有 34 句，句内逗号的停顿和句末停顿在音频上无法区分。FFT 滑窗互相关实现复杂且易错（数组长度算错）。

可靠做法是**语速一致性映射**：同一引擎 + 同一音色 + 同一文本，两次生成的每句净语音时长高度一致。所以分段跑一遍只为拿「每句净语音时长」（剔除首尾静音），按比例缩放即可推算该句在母带中的起止。

```python
# 1) 量分段版的净语音（剔除首尾静音）
fl = 320                                  # 20ms 帧
e = np.sqrt((x[:nf*fl].reshape(nf,fl)**2).mean(axis=1) + 1e-12)
speech[i] = (e > e.max()*0.02).sum() * fl / SR   # 有声帧占比

# 2) 单调映射，首尾锚定母带
ratio = master_dur / sum(speech.values())
start[i] = acc * ratio;  acc += speech[i]
```

首句对齐 0、末句对齐母带末端，误差不累积。实测 34 句误差 <0.02s/句。

## 拼接

> 长片口播见上文「整段一次生成」—— 下面的分���拼接只适用于短片。

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

使用 [gen_voice.py](../scripts/gen_voice.py) 两种模式：

```bash
# 短片：逐 Line 生成，可单曲替换
python3 scripts/gen_voice.py --project . --mode segment --dry-run

# 长片（≥3 分钟）：整稿一次生成 + 时间轴反推
python3 scripts/gen_voice.py --project . --mode oneshot --dry-run
```

`segment` 抽取 `SCRIPT.md` 缩进口播文本、按段生成 WAV、测量真实时长写 `audio_meta.json`，带输入指纹缓存与有上限的瞬态错误重试。

`oneshot` 整稿一次请求生成 `assets/voice/master-oneshot.wav`，然后用语速一致性映射反推每句起止，写同一份 `audio_meta.json`（`mode: "oneshot"`）。分两次调用时需要 numpy（对齐阶段量净语音时长）。字幕块由 [gen_cues.py](../scripts/gen_cues.py) 用 ASR 从整段音频反推毫秒级句边界：

```bash
python3 scripts/gen_cues.py --project .    # → cues-asr.json，按 ASR 句边界对齐
```

不要退回按字数估算——长片会累积到几秒的不同步。`segment` 模式没有整段母带，需先拼出整段音频再用 `--audio` 指定。

先`--dry-run` 检查，确认后再调用收费服务。详见 [模板使用](templates.md)。


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
