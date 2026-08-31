# lychee-skills

通用 Lychee TTS Agent Skill：实时查询公共音色，支持音色设计、语音克隆，并通过 PCM 16000 Hz WebSocket 边合成、边播放、边写 WAV。

## 核心能力

- 公共音色实时来自 `GET https://voice.lycheeai.com.cn/openapi/voice-list`，不打包固定音色表。
- 支持按名称、描述和语言预筛；自然语言需求由 Agent 阅读实时描述后做最终语义选择。
- 公共音色和个人音色显式区分，同时保留旧 `--voice` 调用兼容性。
- 支持 `POST /openapi/voice-design` 设计试听和 `POST /openapi/tts/clone` 克隆。
- 克隆响应的 `request_id` 保存为个人音色的 TTS `speaker_id`。
- TTS 使用 `wss://voice.lycheeai.com.cn/openapi/tts/ws_binary/v2`。
- 真流式参数固定为 PCM、16000 Hz、speed 1.0；首块音频立即写入，播放由独立队列消费。
- 长文本按自然标点分段；播放设备失败不会破坏 WAV，中途断流会保留可播放的部分 WAV。
- 结果、事件和错误使用版本化 Agent 契约，也可选择 JSON Lines 增量输出。

## Agent 兼容性

Skill 核心遵循通用 Agent Skills 目录结构，不依赖 Claude、Codex 或某一种 Shell。安装 Adapter 支持：

| target | 默认目录 | 适用范围 |
|---|---|---|
| `claude` | `~/.claude/skills` | Claude Code；同时安装 Claude 辅助命令 |
| `codex` | `~/.codex/skills` | Codex |
| `agents` | `~/.agents/skills` | 支持通用 Agent Skills 目录的运行时，如 Codex、Copilot CLI、Gemini CLI |
| `all` | 上述全部 | 同一台机器需要多个运行时 |

其他实现 Agent Skills 规范的运行时也可以直接安装 `skills/tts-lychee` 目录。Agent 专属差异只存在于安装位置和启动 Adapter，TTS 实现保持一致。

## 环境要求

- Python 3.8+
- 环境变量 `LYCHEE_API_KEY`
- 核心依赖：`websocket-client`、`requests`
- 可选实时声卡播放：`sounddevice`

不要直接假设系统命令叫 `python` 或 `python3`。Skill 内的 `scripts/run.ps1` 和 `scripts/run.sh` 会探测并验证可执行的 Python，也会避开 WindowsApps 占位程序。安装依赖后默认使用 `~/.lychee/tts-lychee/runtime/venv` 隔离环境；可通过 `TTS_RUNTIME_HOME` 改变位置，显式 `TTS_PYTHON` 仍具有最高优先级。

## 安装

### 方式一：skills CLI

```bash
npx skills add TaylorEnthon/lychee-skills --skill tts-lychee
```

这是支持该 CLI 的 Agent 的推荐方式。安装后使用 Skill 目录中的启动脚本安装依赖并运行 doctor。

### 方式二：Windows PowerShell 5.1 / PowerShell 7+

不传 `-Target` 时仍按原有行为安装到 Claude：

```powershell
.\install.ps1
```

安装到指定 Agent：

```powershell
.\install.ps1 -Target codex
.\install.ps1 -Target agents
.\install.ps1 -Target all
```

自定义目录仍可使用 `-ClaudeHome`，也支持 `-CodexHome` 和 `-AgentsHome`。执行策略阻止脚本时：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Target agents
```

### 方式三：macOS / Linux / Git Bash

不传参数时仍默认安装到 Claude：

```bash
bash ./install.sh
```

安装到指定 Agent：

```bash
bash ./install.sh --target codex
bash ./install.sh --target agents
bash ./install.sh --target all
```

可通过 `CLAUDE_HOME`、`CODEX_HOME`、`AGENTS_HOME` 覆盖目标目录。

## 安装依赖与 doctor

在 Skill 安装目录中运行相应启动脚本。

Windows：

```powershell
& "$env:USERPROFILE\.agents\skills\tts-lychee\scripts\run.ps1" --install-deps
& "$env:USERPROFILE\.agents\skills\tts-lychee\scripts\run.ps1" --install-playback  # 可选
& "$env:USERPROFILE\.agents\skills\tts-lychee\scripts\run.ps1" --doctor
```

macOS/Linux/Git Bash：

```bash
bash "$HOME/.agents/skills/tts-lychee/scripts/run.sh" --install-deps
bash "$HOME/.agents/skills/tts-lychee/scripts/run.sh" --install-playback  # 可选
bash "$HOME/.agents/skills/tts-lychee/scripts/run.sh" --doctor
```

使用 `claude` 或 `codex` target 时，把示例中的 `.agents` 换成对应目录。launcher 会自动创建和复用 Skill 自己的 venv，不修改项目环境。doctor 不调用在线 TTS，也不产生音频费用。

## 配置 API Key

从 [voice.lycheeai.com.cn](https://voice.lycheeai.com.cn/) 获取 API Key，并设置为 `LYCHEE_API_KEY`。

Windows：

```powershell
setx LYCHEE_API_KEY "你的API密钥"
```

macOS/Linux 当前 Shell：

```bash
export LYCHEE_API_KEY="你的API密钥"
```

重启 Agent，使它继承新的环境变量。不要把真实 Key 放进命令参数、日志或仓库。

## 对话式使用

安装后，用户直接表达目标即可，例如：

```text
查询当前有哪些适合纪录片旁白的成熟男声。
用靖轩朗读“欢迎使用实时语音合成”，边生成边播放。
设计一个克制、温暖、专业的女性音色，先让我试听。
列出我已经保存的个人音色。
用“我的专业女声”朗读这段内容并保存 WAV。
```

未指定音色时，Skill 会查询实时 `description` 并展示 2–5 个候选；不会使用固定默认音色。普通查询、合成、保存和播放无需技术确认。音色设计会先返回长期可访问的试听 URL，保留全部查询参数，用户确认声音后才克隆。

## 客户端操作

下面用 `<launcher>` 表示当前平台的 `scripts/run.ps1` 或 `scripts/run.sh`。

```text
<launcher> --list-voices --compact --offset 0 --limit 100
<launcher> --search-voices "纪录片" --compact --offset 0 --limit 100
<launcher> --list-personal-voices
<launcher> --text "欢迎使用实时语音合成。" --public-voice "靖轩" --play --progress --output "welcome.wav"
<launcher> --text "欢迎回来。" --personal-voice "我的专业女声" --output "personal.wav"
<launcher> --design-description "清晰、亲切、专业的女性声音" --design-text "晚上好，今天辛苦了。"
<launcher> --clone-url "设计接口返回的试听地址" --clone-name "我的专业女声" --confirm-clone
<launcher> --rename-personal-voice "旧名字" --new-personal-voice-name "新名字" --confirm-rename
<launcher> --remove-personal-voice "不再使用的别名" --confirm-remove
```

同名个人音色默认拒绝覆盖；用户明确确认后为克隆命令添加 `--replace-personal-voice`。删除操作只删除 `~/.lychee/tts-lychee/voices.json` 中的本地别名，不代表删除服务端音色。

## 真流式结果

标准输出最终返回带 `schema_version`、`type`、`operation` 和 `run_id` 的 JSON；旧业务字段保持不变。`--progress` 会把连接、发送文本、首块音频和分段完成事件增量写到 stderr。需要单一机器可读流时可选 `--jsonl`。主要字段包括：

- `output`：最终 WAV 绝对路径。
- `first_audio_ms`：进入 WebSocket 流程后的首音频耗时。
- `end_to_end_first_audio_ms`：包含音色解析的端到端首音频耗时。
- `segments`、`bytes_written`、`total_duration_ms`。
- `played`：本机声卡播放是否完整成功。
- `warnings`：播放降级等不影响 WAV 的提示。

首个音频字节前的临时连接错误会自动重试一次；收到音频后不再重试。取消或中途失败且已有有效 PCM 时，错误结果通过 `partial_output` 返回一个可播放但可能不完整的 WAV。可选播放失败不会中断网络接收或 WAV 写入，只会返回 warning。

## 开发验证

```bash
python -m pytest -q
bash -n install.sh skills/tts-lychee/doctor.sh skills/tts-lychee/scripts/run.sh
```

CI 在 Python 3.8、3.11、3.13 和 Windows PowerShell 5.1/7 上验证核心测试、安装脚本及运行启动器。

## License

MIT
