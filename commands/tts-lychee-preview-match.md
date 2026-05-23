---
description: 预览一段音色描述会匹配到哪个 tts-lychee 公开音色
allowed-tools: Bash(python:*), Bash(python3:*)
---

使用 `tts-lychee` 的离线预览能力判断 `$ARGUMENTS` 会匹配到哪个公开音色。不要合成音频，不需要 API Key，不要读取源码或配置文件，不要展示内部字段。

最终只告诉用户会使用的公开音色名；如果返回 used_default_voice=true，补一句“未识别到更具体音色，使用返回的默认音色”。
