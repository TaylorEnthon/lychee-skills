---
description: 查询 tts-lychee 当前可用的公共音色列表
allowed-tools: Bash(python:*), Bash(python3:*)
---

使用已安装 Skill 的客户端实时调用公共音色接口展示当前可用音色。自然语言选音色时，Agent 必须阅读返回项的 `description`，结合用户的场景和音色要求筛选候选。不要合成音频，不要读取源码或本地配置，不要展示 API Key 或内部标识。

需要已配置 `TTS_API_KEY`；如果未配置，直接说明无法查询，不要猜测或展示旧列表。

调用：

```bash
python3 {baseDir}/scripts/tts_client.py --list-voices
```

按名称、语言和简短描述用简洁列表回复用户。
