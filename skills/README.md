# voiceframe skill

[`voiceframe`](voiceframe/SKILL.md) 将文案或自录口播组织成有旁白的视频制作流程，可使用不同生成服务、动画框架与剪辑应用，也可跨应用协作。

```text
skills/voiceframe/
├── SKILL.md                 # 统一入口：内容流程与工具选择
├── scripts/                 # 项目初始化、百炼配音、音频时间轴
├── assets/
│   ├── project/             # 应用中立的文档与交接模板
│   └── adapters/hyperframes/ # 按需选择的 HTML 骨架
└── references/
    ├── storyboard.md        # 剧本与分镜
    ├── production.md        # 制作、应用交接与交付
    ├── tts-voice.md         # 百炼配音实现
    ├── audio-post.md        # 自录处理（尚未实测）
    ├── templates.md         # 内置模板与工具用法
    └── adapters/hyperframes.md
```

安装或分发整个 `voiceframe/` 文件夹，调用 `$voiceframe`。默认初始化不绑定应用；指定 `--adapter hyperframes` 才附带其骨架。其他应用目前通过通用文档、素材和音频索引交接，未内置自动转换器。

用法见 [模板说明](voiceframe/references/templates.md)。
