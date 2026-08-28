---
name: tts-lychee
description: Use when the user asks for TTS, 配音, 朗读, 生成语音, 公共音色查询, 音色设计, 语音克隆, or true streaming speech with Lychee.
version: 2.1.0
user-invocable: true
metadata:
  openclaw:
    requires:
      bins: ["python3"]
      env: ["TTS_API_KEY"]
    primaryEnv: "TTS_API_KEY"
---

# TTS Lychee

这是 Lychee 的实时语音 Skill。公共音色以服务端实时列表为准；设计或克隆得到的音色也统一进入同一条 PCM 流式合成链路。

## 硬性约束

- 服务地址是 `https://voice.lycheeai.com.cn`。
- 公共音色必须从 `/openapi/voice-list` 查询，返回项的 `name` 才是可用的公共音色标识。
- 不使用本地固定音色、别名表或默认男女声；找不到指定音色时不能静默替换。
- 实时 TTS WebSocket 是 `wss://voice.lycheeai.com.cn/openapi/tts/ws_binary/v2`。
- 流式配置固定为 `codec=pcm`、`sample_rate=16000`、`speed=1.0`。不能改为 MP3、24000 Hz 或其他语速。
- 每个音频块到达后立即播放或写入，不能等整段完成后再输出。
- 流式结果保存为单声道 PCM16 WAV；MP3 不是实时路径。
- `TTS_API_KEY` 只从环境变量读取，不写入命令行、日志或回复。

## 用户请求分流

### 查询或选择公共音色

先区分“按名称查找”和“按描述筛选”：

- 用户明确给出音色名称时，直接使用这个名称解析公共音色。
- 用户只给出一个关键词时，可以运行 `--search-voices`；客户端会先拉取完整列表，再对 `name`、`description` 和 `lang_code` 做关键词预筛。
- 用户提出“找一个适合纪录片旁白的成熟男声”这类自然语言需求时，必须运行 `--list-voices` 拉取完整列表。Agent 要阅读每个返回项的 `description`，结合语言、性别、音色特征和适用场景做语义筛选，再展示候选。

不要把完整自然语言需求直接作为服务端 `/openapi/voice-list` 的 `name` 查询；服务端的 `name` 只支持音色名称模糊匹配。关键词预筛不是最终语义判断，Agent 仍要以返回的描述为依据：

```bash
python3 {baseDir}/scripts/tts_client.py --list-voices
python3 {baseDir}/scripts/tts_client.py --search-voices "用户的搜索词"
```

只展示 `name`、描述、语言和试听地址。精确名称优先；语义筛选后展示 2-5 个候选并说明匹配理由，让用户选择。没有候选时不要静默替换音色，应扩大为完整列表后重新判断或明确告知未找到。客户端先验证实时公共音色；只有服务端明确没有该公共名称、且用户目录中存在同名个人音色时，才使用个人音色。

### 使用公共音色朗读

用户明确给出公共音色名称时，原样传给 `--voice`：

```bash
python3 {baseDir}/scripts/tts_client.py \
  --text "要朗读的文本" \
  --voice "用户指定的公共音色名称" \
  --play
```

默认生成当前目录下的 WAV。用户指定路径时使用 `--output`；除非用户明确允许覆盖，否则不要使用 `--overwrite`。

用户没有指定音色时，不要猜测。询问音色，或先列出少量实时候选；只有用户明确说“随便一个/使用默认”时，才采用当前服务端列表的第一个返回项。

### 设计并克隆个人音色

这是有副作用的操作，必须在克隆前向用户展示设计试听并获得确认；客户端还要求显式 `--confirm-clone`。

1. 设计：

```bash
python3 {baseDir}/scripts/tts_client.py \
  --design-description "自然语言音色描述" \
  --design-text "用于试听的文本"
```

2. 将返回的 `preview_audio_url` 作为试听结果，等待用户确认。
3. 确认后克隆并保存个人别名：

```bash
python3 {baseDir}/scripts/tts_client.py \
  --clone-url "已确认的试听音频地址" \
  --clone-name "用户给出的个人音色名" \
  --confirm-clone
```

也可以用 `--clone-audio` 克隆用户提供的本地参考音频。克隆响应中的 `request_id` 是后续 TTS 使用的 `speaker_id`，客户端会将它保存到用户目录的个人音色注册表；音色设计响应中的 `request_id` 不是 TTS 的 `speaker_id`。

后续用户说“用我的音色朗读”时，使用保存的个人音色名作为 `--voice`，不要重新克隆。

## 安装与自检

安装后先安装依赖：

```bash
python3 -m pip install -r {baseDir}/requirements.txt
```

检查安装：

```bash
python3 {baseDir}/scripts/tts_client.py --doctor
```

Windows 也可以运行已安装目录中的 `doctor.ps1`；macOS/Linux 可以运行 `doctor.sh`。自检不会发起 TTS 合成，但会检查核心依赖、API Key 和旧版数据是否残留。

## 输出契约

客户端标准输出最终返回一个 JSON 对象，包含：

```json
{
  "success": true,
  "output": "绝对 WAV 路径",
  "voice": "用户可理解的音色名",
  "format": "wav",
  "sample_rate": 16000,
  "first_audio_ms": 240,
  "bytes_written": 123456
}
```

普通回复只告诉用户是否成功、采用的音色名和 WAV 路径。不要展示 API Key、内部 `speaker_id`、协议事件或源码路径。生成失败时说明真实失败原因，不要声称已生成。

## 常见错误处理

- API Key 缺失：停止调用并提示配置 `TTS_API_KEY`。
- 公共音色不存在：重新查询并让用户选择，不回退。
- 公共音色匹配多个：展示候选，不自动猜测。
- 设备没有音频输出或缺少 `sounddevice`：保留 WAV 增量生成，并明确提示未播放。
- WebSocket 中途失败：删除未完成的 partial 文件，不把它当作成功音频。
- 文本过长：客户端按标点分段，仍使用同样的 PCM 16000 流式配置。
