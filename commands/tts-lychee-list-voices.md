---
description: 查询 tts-lychee 当前可用的公共音色列表
allowed-tools: Bash(bash:*)
---

使用已安装 Skill 的客户端实时调用公共音色接口。自然语言选音色时，Agent 必须阅读返回项的 `description`，结合用户的场景和音色要求做语义比较。不要合成音频，不要读取源码或本地配置，不要展示 API Key 或内部标识。

需要已配置 `LYCHEE_API_KEY`；如果未配置，直接说明无法查询，不要猜测或展示旧列表。

调用：

```bash
bash "${CLAUDE_HOME:-$HOME/.claude}/skills/tts-lychee/scripts/run.sh" --list-voices --compact --offset 0 --limit 100
```

如果结果的 `has_more` 为 true，按 `returned` 增加 offset 继续读取，直到完整比较目录。最终只按名称、语言、描述和匹配理由展示 2–5 个最相关候选。
