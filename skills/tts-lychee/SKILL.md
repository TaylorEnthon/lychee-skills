---
name: tts-lychee
description: Use when a user asks to synthesize, stream, play, or save speech; discover public voices; design a voice; or clone and reuse a personal voice with Lychee.
metadata:
  openclaw:
    requires:
      env: ["TTS_API_KEY"]
    primaryEnv: "TTS_API_KEY"
---

# TTS Lychee

把用户的自然语言目标转成实时语音。普通用户只需要说明文本、声音偏好、是否播放或保存；Agent 负责音色查询、技术参数、运行环境和结果解释。

典型请求包括：

- “帮我找一个适合纪录片旁白的成熟男声。”
- “用靖轩朗读这段话，边生成边播放。”
- “设计一个克制、温暖、专业的女声，先让我试听。”
- “用我保存的‘品牌旁白’朗读并保存 WAV。”

查询、选择、合成、保存和尽力播放直接执行。只有克隆、替换个人音色、重命名、删除和覆盖已有文件需要用户确认。

## 调用入口

`{baseDir}` 是本文件所在目录。按当前 Shell 选择 `<launcher>`：

```text
Windows PowerShell: powershell -NoProfile -ExecutionPolicy Bypass -File "{baseDir}/scripts/run.ps1"
Bash:               bash "{baseDir}/scripts/run.sh"
```

首次使用或调用失败提示依赖缺失时运行 `<launcher> --doctor`；只在 doctor 报告缺少核心依赖时运行 `--install-deps`，需要声卡播放且缺少播放依赖时运行 `--install-playback`。启动器自动使用 Skill 独立运行环境，默认位于 `~/.lychee/tts-lychee/runtime`，可由 `TTS_RUNTIME_HOME` 覆盖。不要让用户挑选 Python 可执行文件或虚拟环境。

## 选择音色

公共音色始终查询当前服务，不使用内置音色表。

- 用户给出已确认的公共音色名：合成时用 `--public-voice "名称"`，无需先查目录。
- 用户指定已保存的个人别名：合成时用 `--personal-voice "别名"`；不重复克隆。
- 旧脚本的 `--voice` 继续兼容，但新调用优先使用上面两个显式参数，避免公共名和个人别名混淆。
- 单个关键词可先用 `--search-voices "关键词" --compact --offset 0 --limit 100`，它会匹配名称、`description` 和语言。
- “成熟、男声、纪录片”这类自然语言偏好，用 `--list-voices --compact --offset 0 --limit 100` 分块读取实时 `description`；按 `returned` 增加 offset，直到 `has_more=false`，再做语义比较。

只向用户展示 2–5 个最相关候选及名称、描述、语言和选择理由。若候选不足，扩大到完整目录；仍没有时如实说明，不静默换成默认声音。

## 真流式朗读

公共音色示例：

```text
<launcher> --text "要朗读的文本" --public-voice "靖轩" --play --progress --output "speech.wav"
```

个人音色示例：

```text
<launcher> --text "要朗读的文本" --personal-voice "品牌旁白" --play --progress --output "speech.wav"
```

用户不需要本机播放时省略 `--play`；未指定输出路径时客户端生成唯一 WAV 文件名。除非用户确认覆盖已有文件，否则不添加 `--overwrite`。播放设备不可用时仍继续流式写 WAV，并在结果中说明未播放。

`--progress` 把增量事件写到 stderr。收到 `first_audio` 后即可告诉用户已经开始生成或播放，不必等完整文本结束。`--jsonl` 是可选的 Agent 集成模式，把进度和最终结果作为同一 stdout JSON Lines 流输出；普通使用不需要它。

## 设计、试听和克隆

先设计试听：

```text
<launcher> --design-description "克制、温暖、专业的女性声音" --design-text "晚上好，欢迎收听。"
```

向用户展示 `preview_audio_url`，等待用户确认声音本身，再执行克隆：

```text
<launcher> --clone-url "已确认的试听地址" --clone-name "品牌旁白" --confirm-clone
```

设计接口的音频 URL 长期可访问。必须按返回值原样展示和保存，包括查询参数；不要把它当成临时签名 URL 清洗。也可以用 `--clone-audio` 克隆用户提供的本地音频。

克隆响应的 `request_id` 才是 TTS 使用的 `speaker_id`；设计响应的 `request_id` 不是。客户端把它保存到个人音色注册表，对用户只暴露别名。同名别名默认拒绝替换；用户确认后再加 `--replace-personal-voice`。

## 个人音色管理

```text
<launcher> --list-personal-voices
<launcher> --rename-personal-voice "旧别名" --new-personal-voice-name "新别名" --confirm-rename
<launcher> --remove-personal-voice "别名" --confirm-remove
```

重命名和删除只修改本地别名，不代表删除服务端音色。

## 结果与失败恢复

最终 stdout 是版本化 JSON。成功朗读包含 WAV 绝对路径、音色、首音频延迟、字节数、分段数和 `played`。普通回复说明采用的音色、是否播放、WAV 路径和必要 warning；不展示 API Key、内部个人 `speaker_id` 或协议帧。

连接在首个音频字节到达前发生临时故障时，客户端会安全重试一次；收到任意音频字节后不再重试，避免重复语音。取消或中途失败时，若已收到有效 PCM，会生成可播放但可能不完整的 WAV，并在错误的 `partial_output` 中返回路径。应明确说这是部分音频，不能声称完整合成成功。

## 实现安全边界

- API：`https://voice.lycheeai.com.cn`；实时端点：`wss://voice.lycheeai.com.cn/openapi/tts/ws_binary/v2`。
- 真流式内部固定为 PCM16 单声道、16000 Hz、speed 1.0；这些不是用户选项。PCM 到达即写 WAV，可选播放通过队列并行消费。
- `TTS_API_KEY` 只从环境变量读取，不能放入参数、日志、文件或回复。
- 从 URL 克隆前校验公网地址、重定向和 WAV/MP3/M4A 文件格式，但注册表中的设计 URL 保留原值。
