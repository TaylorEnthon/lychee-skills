---
name: tts-lychee
description: 将文本合成为 mp3 语音，支持基础声线、情绪风格、角色职业、方言口音等多种预设音色。Use when the user asks for TTS, 配音, 朗读, 生成语音, text-to-speech, or using voices like 温柔女声、性感女声、东北话男声、播音员男声。
version: 1.0.0
user-invocable: true
metadata:
  openclaw:
    requires:
      bins: ["python3"]
      env: ["TTS_API_KEY"]
    primaryEnv: "TTS_API_KEY"
---

# TTS Lychee
将文本合成为 mp3 音频。正常使用时只需要接收用户文本和音色描述，调用客户端生成文件，然后告诉用户 mp3 保存路径。不要动态生成音色、不要 clone、不要写 Redis/SQLite 缓存。

## 前置要求

从 `https://shanhaistudio.lycheeai.com.cn/` 获取 API Key，并设置为系统环境变量。正常调用时只读取环境变量，不要在命令行里写出、export 或 echo API Key：

```bash
export TTS_API_KEY="your-api-key"
```

认证方式由客户端内部使用 `api_key` 请求头完成。不要向最终用户展示 API Key、请求头或认证细节。

可选环境变量：

```bash
export TTS_WS_URL="ws://shanhaistudio.lycheeai.com.cn/openapi/tts/ws_binary/v2"
```

Python 客户端需要 `websocket-client`：

```bash
python3 -m pip install websocket-client
```


## 安装自检

用户说“检查 tts-lychee 安装”或合成失败时，先运行离线自检，不要展示 API Key：

```bash
python3 {baseDir}/scripts/tts_client.py --doctor
```

Windows 也可以运行已安装目录里的 `doctor.ps1`。自检只检查 Python、依赖、环境变量是否存在、数据文件和别名匹配，不会合成音频或扣费。
## 输入

```json
{
  "text": "要合成的声音内容",
  "voice": "温柔女声"
}
```

- `text` 必填，待合成文本。
- `voice` 选填，音色名称或包含音色名称的描述；默认使用 `默认女声`。

## 输出

```json
{
  "success": true,
  "output": "D:/path/to/tts-lychee-20260519-161530.mp3",
  "voice": "温柔女声",
  "duration_ms": 3500
}
```

默认会写入当前工作目录，文件名使用时间戳和音色名，例如 `20260519-203500-甜美女声_tts.mp3`。最终回复只说明生成是否成功、mp3 保存路径、使用的用户可理解音色名。不要向最终用户暴露 `speaker_id`、`voice_id`、`matched_alias`、`instruct`、clone 音频路径、WebSocket、协议细节、源码文件名或诊断命令。


## 正常调用规则

- 直接调用 `{baseDir}/scripts/tts_client.py` 生成 mp3；不要为了确认别名、音色或实现细节去运行 `grep`、`cat`、`Select-String`、`Get-Content` 等源码/配置检查命令。
- 不要把内部检查过程、命令行细节、环境变量值、源码路径、JSON 调试字段展示给最终用户。
- 不要在 Bash/PowerShell 命令里写 `TTS_API_KEY=...`、`export TTS_API_KEY=...` 或任何真实 API Key；只调用客户端，让它从已配置环境变量读取。
- 如果用户明确指定了音色名称或描述，原样传给客户端处理，命令里必须包含 `--voice "<用户指定的音色名称或描述>"`；不要省略 `--voice` 让客户端回退到默认音色，也不要因为“常用音色”示例里没有该音色，就擅自判断不支持、改用近似音色或向用户解释“暂无”。
- 只有用户完全没有给出音色名称或音色描述时，才可以省略 `--voice` 并让客户端使用默认音色。
- 只有客户端实际返回兜底音色，或用户明确要求预览/查看音色时，才说明匹配结果；普通合成回复只报告客户端实际返回的音色名。
- 只有用户明确要求“排查/调试/检查安装/查看配置”时，才可以执行诊断命令；诊断回复也不要展示 API Key。
- 如果用户没有指定输出路径，让客户端使用默认文件名（时间戳 + 音色名 + `_tts.mp3`），并在完成后只告知实际保存路径。
## 内部执行

```bash
python3 {baseDir}/scripts/tts_client.py --text "欢迎使用短剧翻译平台" --voice "温柔女声"
```

指定输出文件：

```bash
python3 {baseDir}/scripts/tts_client.py --text "这是一段旁白" --voice "播音员男声" --output ./narration.mp3
```

## 音色匹配

1. 优先匹配明确音色名，例如 `温柔女声`。
2. 包含匹配，例如用户说 `用温柔女声朗读`，匹配 `温柔女声`。
3. 简单关键词匹配，例如 `东北话 + 男` 匹配 `东北话男声`，`播音员 + 男` 匹配 `播音员男声`。
4. 未匹配时使用兜底音色 `默认女声`。

方言音色省略男女时，客户端优先匹配对应男声，例如 `云南话` 匹配 `云南话男声`。这个优先级只用于方言短名，不要把它扩展到旁白、播音员、情绪风格等其他模糊描述。

内置音色表支持常见自然语言同义词，例如“男童”“甜妹音”“小说旁白”“新闻播报男声”“性感女声”。`女`、`男`、`女声`、`御姐` 等短名字只在用户精确指定时使用，不要把它们当作自然语言包含匹配的优先结果。下方常用音色只是示例，不是完整支持列表；正常回复中不要提内部映射文件。

## 常用音色

默认女声、默认男声、温柔女声、甜美女声、性感女声、御姐音、低沉男声、磁性男声、少年音、中性儿童声、耳语女声、四川话女声、东北话男声、河南话女声、新闻播报男声、播音员男声、旁白男声、助眠女声。

## 示例

```json
{ "text": "你终于来了。", "voice": "温柔女声" }
```

```json
{ "text": "各位观众，欢迎收看本期节目。", "voice": "播音员男声" }
```

```json
{ "text": "这事儿整得挺有意思。", "voice": "东北话男声" }
```


## 调试

默认输出只包含用户安全字段。只有用户明确要求排查匹配问题时，才可给客户端加 --debug 查看 `voice_id`、`matched_alias` 等内部字段；不要把这些字段放进普通最终回复。
