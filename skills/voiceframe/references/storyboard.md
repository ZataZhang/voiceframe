# 分镜与脚本

把一篇文案变成「可以按帧施工」的计划层。**先出分镜，再制作画面** —— 顺序不能反。

## 产出物

| 文件 | 内容 | 时机 |
|---|---|---|
| `BRIEF.md` | 需求简报：受众、目标、时长、平台 | 最先 |
| `frame.md` | 设计系统：`design.md` 的视频化改写，色板/字体/尺度 | 写稿前 |
| `STORYBOARD.md` | 分镜表：一帧一个关键时刻 | 与 SCRIPT 同批 |
| `SCRIPT.md` | 锁定旁白稿，供 TTS 消费 | 与 STORYBOARD 同批 |

流程：`BRIEF → frame.md → (STORYBOARD + SCRIPT) → 在所选应用制作场景`

## STORYBOARD.md 格式

Frontmatter 定全局：

```yaml
---
format: 1920x1080
duration: 161s          # advisory，不是硬门禁
message: "这条视频要传达的那一句"
arc: "Hook → 论点 → 牌面 → 反转 → 收据"
audience: "关注……的中文读者"
mode: autonomous
music: none
---
```

然后每帧一节：

```markdown
## Frame 1 — 半壁江山

- scene: 画面上有什么
- voiceover: "这一帧的旁白"
- duration: 7.2s
- transition_in: cut
- status: outline
- src: 待填素材路径或应用场景标识

- type: hook
- persuasion: Statistical proof + counterintuitive claim
- beat: "Surprise + recognition"
- blueprint: dataviz-countup (Reproduce)
- focal: 巨型数字 51% → 收回 9%
- roles: 巨型数字 = foreground subject · 份额条 = supporting · 深色场 = background
- sfx: impact-low, tick

narrativeRole: 用一个无可争辩的数字把观众钉进事实，并立刻用反转制造认知缺口。
keyMessage: 一句话说清这一帧要让观众记住什么。

Scene 1 (0–2s): 深色场；巨型 "51%" 居中偏左、占画布约 55%；右上角 mono 标记 "1988"。只此三项。
Scene 2 (2–4.5s): 份额条上"日本"橙段落定、标注 51%；`/` 标记引出 "美国 37%"。数字稳定保持，不下落。
Scene 3 (4.5–7.2s): 同一构图右移换位，51% 段蜷缩成一小截，数字从 51 递减到 9。
```

### 状态机

`outline → built → animated`

- `outline` —— 分镜已定，画面未制作
- `built` —— **画面或场景工程存在且布局已确认**（线框稿或更好），尚未加动效
- `animated` —— 动效已完成

布局确认是显式关卡，不是写完就算。

## SCRIPT.md 格式

给 TTS 消费，**口播文字必须放在缩进代码块里**（纯文本，无 markdown 标记）：

```markdown
# SCRIPT —标题

**Voice:** qwen-audio-3.1-tts-flash · xunanchuan_v3.1
**Voice direction:** 冷静、克制、有史观的重量；不煽情、不喊口播。

---

## Line 1 — 半壁江山 (Frame 1)

**Delivery:** 数字落定时加重，「不足一成」放慢制造反转。

    1988 年，日本握有全球半导体的一半。
    三十七年后，不足一成。
```

`Delivery:` 行写语气指示 —— 它不进 TTS，但下一棒（人工重录或改稿）要靠它。

## 口播稿要写成「能念出来」的

数字和符号必须转成口语形态，否则 TTS 会念错或念得别扭：

| 写成 | 念出来 |
|---|---|
| `51%` | `百分之五十一` |
| `1.72兆日元` | `一点七二万亿日元` |
| `i-mode` | `i-mode`（保留，或「爱模式」） |
| `261%` | `百分之二百六十一` |

`2026-10-07` 的 20 分钟版里，这条规则把 4700 字原文全部改写了一遍。

## 长片：时长反推 + 分章

按叙事节奏和真实音轨确定场景数量，不固定每分钟帧数。长片按章节组织，每章可以独立制作、验证和导出；具体工程结构由应用决定。场景编号不等同于编码帧。

### 先做音频，再定时长

口播稿定稿后**先生成全部配音，拿到准确总时长，再回填分镜的 `duration` 和帧边界**。否则帧时长全是估算，改一帧牵动全片。

反过来（先写分镜再配音）的代价：分镜时长是估值，成片一旦对不上要返工。

## 反面清单

分镜里的禁止项，直接抄：

- 禁止 front-load-then-freeze —— 先全摆出来再冻住，PPT 感
- 禁止 everything-floating —— 屏保感
- 禁止纯文字墙 —— 每帧至少一个 ≥40% 画布的主视觉
- 禁止把原文段落按顺序念一遍
- 使用程序化动画时按相应引擎保证可复现；具体渲染约束见所选应用适配指南

## 流程铁律：草稿 → 确认 → 生成

用户要求（2026-10-06 明确）：**贵的步骤（TTS/渲染）之前必须有可审的草稿并获确认**。「不要问问题」≠ 跳过审稿，而是"别让我做选择题，给我看草稿"。

```
1. 剧本草稿：叙事线 + 每帧一句话 + 旁白文本      （文字，快改）
2. 画面草稿：简笔线框联络表，或 bl 概念图（下节）  （← 确认关卡）
3. 确认/圈改某几帧 → 再跑 TTS、建帧、渲染，中间不再打扰
```

## 画面草稿：bl 概念图（逐帧 AI 出图）

```bash
bl image generate --prompt "<该帧构图描述>，<统一风格尾缀>" \
  --size 16:9 --watermark false --out-dir drafts/concepts --out-prefix NN-slug
```

- 统一风格尾缀保证 15 张一致（例）：`扁平编辑海报风格，深墨黑背景，奶油白粗体中文标题，唯一强调色火橙色，1px 细线分隔，无阴影无渐变，极简排版，杂志海报质感，16:9`
- **并发 3-5 路约 1/3 会 FAIL（限流），失败的串行重试即可**；个别 prompt 换措辞再试
- 联络表：`ffmpeg -pattern_type glob -i 'drafts/concepts/*.png' -vf "scale=560:315,tile=3x5:padding=6:color=0x222222" -frames:v 1 concept-sheet.jpg`
- **审稿口径必须向用户声明**：AI 图只确认构图/风格，图内文字数据是编造的，成片文字一律代码绘制
- 出图前跑 bl 协议预检（`bl --version` vs skill 版本 vs npm latest），旧了先问用户是否升级

## 内置模板

复制 [项目模板](../assets/project/STORYBOARD.md) 与 [口播模板](../assets/project/SCRIPT.md)，按当前主题填写。完整初始化与工具用法见 [模板使用](templates.md)。
