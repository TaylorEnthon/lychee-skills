---
description: 按名称或描述搜索 tts-lychee 当前公共音色
allowed-tools: Bash(python:*), Bash(python3:*)
---

使用已安装 Skill 的客户端实时搜索公共音色。将 `$ARGUMENTS` 作为搜索词传给接口；不要合成音频，不要使用本地固定音色，不要展示 API Key 或内部标识。

调用：

```bash
python3 {baseDir}/scripts/tts_client.py --search-voices "$ARGUMENTS"
```

如果没有匹配项，明确告诉用户当前服务端没有返回候选，不要静默替换音色。
