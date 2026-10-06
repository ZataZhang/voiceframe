# 音频后期（自录口播 → 可用音轨）

处理用户自己录的口播：单次录音、手机/会议麦、含环境噪声或串音。

> **⚠️ 状态：方法未实测。** 本技能记录的是待验证的方案，不是已验证的流程。
> 首次实战后请回来更新本文，并把跑通的命令固化下来。

## 输入与目标

**输入**：用户自录口播（wav/m4a/mp3），可能带：
- 空调、风扇、键盘等稳态底噪
- 背景音乐、电视声
- 房间混响
- 手机自动增益造成的忽大忽小
- 其他人串音

**目标**：一条能进成片、与 `SCRIPT.md` 逐句对齐、响度一致的口播音轨。

## 待验证的处理链

按顺序，每步都先试听再往下：

```bash
# 1. 底噪分析 —— 先看噪声底有多高，决定降噪强度
ffmpeg -i in.wav -af "afftdn=nt=0.008" -ar 24000 -ac 1 denoised.wav

# 2. 响度归一到 -16 LUFS（口播标准），峰值限 -1.5 dBTP
ffmpeg -i denoised.wav -af "loudnorm=I=-16:TP=-1.5:LRA=11" -ar 24000 -ac 1 normalized.wav

# 3. 句间静音切分，导出每句的精确起止时间
ffmpeg -i normalized.wav -af "silencedetect=n=-35dB:d=0.35" -f null - 2>&1 | grep silence_
```

**降噪强度是最需要判断的一步**。`nt` 取值过大，人声会出金属味（水下音）。先分析噪声底，再从小值试起：

```bash
# 估计噪声底（取开头 0.5 秒的音量，代表静音段）
ffmpeg -i in.wav -af "atrim=0:0.5,volumedetect" -f null - 2>&1 | grep mean_volume
```

`silencedetect` 的输出直接给出每句时间戳 —— 这是「音频反推分镜」的原料，见 [分镜与脚本](storyboard.md) 的「先做音频，再定时长」。

## 待解决的关键问题

1. **背景音乐怎么处理** —— 若音乐和人声混录，`afftdn` 会把人声一起损伤。可能需要 Demucs 分离人声后再合成？未验证成本。
2. **多轨拼接的间隙标准** —— 句间留多少呼吸。短视频和长片答案不同。
3. **降噪后是否需要补气息** —— 长录音里降噪会让人声显得「空」。
4. **串音（其他人说话）** —— 是删除、降噪，还是重录？倾向让用户重录。

## 参考

自录 → AI 音色的可能性（**未验证**）：如果用户不接受自己的声音，可按 [配音生成](tts-voice.md) 用 AI 音色重念 `SCRIPT.md`，此时自录只作节奏参考。

已知 `bl` 有ASR 能力可做转写校对：

```bash
bl speech recognize --url ./recording.m4a --model fun-asr --language zh --out transcript.json
```
