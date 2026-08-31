---
description: 对 tts-lychee 当前公共音色的名称、描述和语言做关键词预筛
allowed-tools: Bash(bash:*)
---

使用已安装 Skill 的客户端实时获取公共音色，并对名称、描述和语言做关键词预筛。客户端会先拉取完整列表，不要把关键词当作服务端 `name` 查询；不要合成音频，不要使用本地固定音色，不要展示 API Key 或内部标识。

如果用户提出的是“适合纪录片旁白的成熟男声”这类自然语言需求，应改用分块的 `--list-voices --compact`，由 Agent 阅读完整列表中的 `description` 后做语义筛选；本命令只提供关键词预筛，不代替 Agent 的语义判断。

调用：

```bash
bash "${CLAUDE_HOME:-$HOME/.claude}/skills/tts-lychee/scripts/run.sh" --search-voices "$ARGUMENTS" --compact --offset 0 --limit 100
```

如果 `has_more` 为 true，继续增加 offset。没有匹配项时明确告诉用户当前服务端没有返回候选，不要静默替换音色。
