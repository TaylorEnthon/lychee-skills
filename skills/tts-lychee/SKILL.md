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

Lychee 实时语音 Skill。核心流程与具体 Agent 无关：使用随 Skill 分发的启动脚本选择可用 Python，再调用同一套客户端。

## 启动客户端

`{baseDir}` 表示本 `SKILL.md` 所在目录；运行时不自动展开时，替换成实际绝对路径。根据当前 Shell 选择一个启动前缀，后续示例中的 `<launcher>` 均指它：

```text
Windows PowerShell: powershell -NoProfile -ExecutionPolicy Bypass -File "{baseDir}/scripts/run.ps1"
Bash:               bash "{baseDir}/scripts/run.sh"
```

不要固定调用 `python` 或 `python3`。启动脚本会验证 Python 3.8+，并避开 WindowsApps 等不可执行占位符。

首次使用先运行：

```text
<launcher> --doctor
```

缺少核心依赖时运行 `<launcher> --install-deps`。用户需要边合成边通过本机声卡播放时，再运行 `<launcher> --install-playback`；无声卡或不安装播放依赖时仍可增量生成 WAV。

## 不可变约束

- 服务地址：`https://voice.lycheeai.com.cn`。
- 公共音色来自 `/openapi/voice-list`；返回项的 `name` 是公共 `speaker_id`。
- 不使用本地固定音色表、预设男女声或静默回退。
- 实时 TTS：`wss://voice.lycheeai.com.cn/openapi/tts/ws_binary/v2`。
- 真流式固定为 `codec=pcm`、`sample_rate=16000`、`speed=1.0`。
- PCM 块到达后立即写入 WAV，并在请求播放时立即送入声卡；不能缓冲完整响应后再输出。
- 输出为单声道 PCM16 WAV；MP3 不属于实时路径。
- `TTS_API_KEY` 只从环境变量读取，不放入命令行、日志、文件或回复。

## 公共音色发现

按用户意图选择：

- 明确音色名：直接用于朗读，客户端会检查实时公共名称。
- 单个关键词：运行 `<launcher> --search-voices "关键词"`，对实时列表的名称、描述和语言做预筛。
- “适合纪录片旁白的成熟男声”这类自然语言需求：运行 `<launcher> --list-voices`，阅读完整返回项的 `description`，结合语言、性别、质感和场景语义筛选。

自然语言筛选后展示 2–5 个候选，包含名称、描述、语言、试听地址和匹配理由，让用户选择。服务端 `name` 查询只用于名称，不承担语义搜索。没有候选时扩大到完整列表重新判断；仍没有则明确告知，不能替换为固定默认音色。

## 真流式朗读

用户确认音色后运行：

```text
<launcher> --text "要朗读的文本" --voice "音色名称" --play --progress --output "speech.wav"
```

- 用户不需要本机播放时省略 `--play`，仍会边接收边写 WAV。
- 除非用户明确允许覆盖，否则不要添加 `--overwrite`。
- 用户没有指定音色时，询问或展示实时候选；只有用户明确允许任意音色时才采用实时列表第一项。
- 播放设备打开或写入失败时，WAV 继续生成；最终明确提示未播放。
- 长文本会按自然标点分段，每段保持 PCM 16000/speed 1.0；持续收到音频不会被总时长误判为超时。

`--progress` 将结构化事件写到 stderr。收到 `first_audio` 后可以立即告诉用户“已经开始播放/生成”，无需等整个文本完成。

## 设计并克隆个人音色

音色设计返回试听，不自动克隆：

```text
<launcher> --design-description "自然语言音色描述" --design-text "试听文本"
```

向用户展示 `preview_audio_url`。只有用户确认试听后才执行：

```text
<launcher> --clone-url "已确认的试听地址" --clone-name "个人音色别名" --confirm-clone
```

也可以用 `--clone-audio` 克隆用户提供的本地音频。克隆响应中的 `request_id` 才是后续 TTS 的 `speaker_id`；音色设计响应中的 `request_id` 不是。

同名个人别名不会静默覆盖。用户明确确认替换后添加 `--replace-personal-voice`。远程试听地址不能指向本机或私有网络。

## 个人音色管理

查询已保存的个人音色：

```text
<launcher> --list-personal-voices
```

后续直接把个人别名传给 `--voice`，不要重复克隆。删除只影响本地别名，执行前必须获得用户确认：

```text
<launcher> --rename-personal-voice "旧别名" --new-personal-voice-name "新别名" --confirm-rename
<launcher> --remove-personal-voice "别名" --confirm-remove
```

不要把本地别名删除描述成服务端音色删除。

## 输出与回复

标准输出最终是一个 JSON 对象。朗读成功结果包含 WAV 绝对路径、音色名、`first_audio_ms`、`end_to_end_first_audio_ms`、字节数、分段数、是否成功播放及安全 warning。

普通回复只说明：是否成功、采用的音色、是否已经播放、WAV 路径，以及必要 warning。不要展示 API Key、内部个人 `speaker_id`、协议帧或源码路径。失败时说明真实阶段和原因，不能声称已生成。

## 错误处理

- API Key 缺失：停止调用，提示配置 `TTS_API_KEY`。
- 公共音色不存在或匹配多个：展示实时候选，不自动猜测。
- 核心依赖缺失：使用启动脚本安装后重新 doctor。
- 播放依赖或设备不可用：保留 WAV，明确提示未播放。
- WebSocket 或协议失败：不提交损坏的 partial WAV。
- 操作参数冲突：拆成一次一个操作；不能依赖隐藏优先级。
