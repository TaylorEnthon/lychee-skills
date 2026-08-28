# lychee-skills

Lychee TTS Skill：实时查询公共音色，支持音色设计、语音克隆，并通过 PCM 16000 Hz WebSocket 真流式播放和保存 WAV。

## 能力

- 公共音色来自 `GET https://voice.lycheeai.com.cn/openapi/voice-list`，不打包固定音色表。
- 公共音色返回项的 `name` 直接作为 TTS `speaker_id`。
- 支持 `POST /openapi/voice-design` 设计试听音色。
- 支持 `POST /openapi/tts/clone` 克隆本地或设计试听音频。
- 克隆返回的 `request_id` 保存为个人音色的 TTS `speaker_id`。
- TTS 使用 `wss://voice.lycheeai.com.cn/openapi/tts/ws_binary/v2`。
- 流式配置固定为 PCM、16000 Hz、speed 1.0；首个音频块到达后立即播放，并增量写入 WAV。

## 环境要求

- Python 3.8+
- `TTS_API_KEY`
- Python 依赖：`websocket-client`、`requests`、`sounddevice`

安装依赖：

```bash
python -m pip install -r skills/tts-lychee/requirements.txt
```

没有音频设备或不需要播放时，可以不安装 `sounddevice`，客户端仍会增量生成 WAV。

## 安装

### 方式一：skills CLI

```bash
npx skills add TaylorEnthon/lychee-skills --skill tts-lychee
```

安装完成后安装 Skill 依赖，并重启 AI 客户端。

### 方式二：Windows PowerShell 5.1 / PowerShell 7+

```powershell
.\install.ps1
python -m pip install -r "$env:USERPROFILE\.claude\skills\tts-lychee\requirements.txt"
```

如果执行策略阻止脚本运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

### 方式三：macOS / Linux Bash

```bash
bash ./install.sh
python3 -m pip install -r "$HOME/.claude/skills/tts-lychee/requirements.txt"
```

安装脚本会复制 Skill、PowerShell/Bash 自检脚本、Python 模块和两个辅助命令，并清理已安装目录中的旧版固定音色数据及旧匹配命令。

## 配置 API Key

从 [voice.lycheeai.com.cn](https://voice.lycheeai.com.cn/) 获取 API Key，并设置为 `TTS_API_KEY`。

Windows：

```powershell
setx TTS_API_KEY "你的API密钥"
```

macOS/Linux 当前 Shell：

```bash
export TTS_API_KEY="你的API密钥"
```

重启 AI 客户端，使其继承新的环境变量。不要把真实 Key 放进命令行、日志或仓库。

## 使用

### 对话中

```text
/tts-lychee 查询当前公共音色
/tts-lychee 用指定的公共音色朗读：欢迎使用。
/tts-lychee 设计一个清晰、亲切、专业的女性音色
```

用户未指定音色时，Skill 会询问或展示实时候选；不会偷偷使用固定默认音色。设计音色会先返回试听，得到用户确认后才执行克隆。

### 直接调用

查询全部公共音色：

```bash
python ~/.claude/skills/tts-lychee/scripts/tts_client.py --list-voices
```

按名称或描述搜索：

```bash
python ~/.claude/skills/tts-lychee/scripts/tts_client.py --search-voices "温柔"
```

流式朗读并播放：

```bash
python ~/.claude/skills/tts-lychee/scripts/tts_client.py \
  --text "欢迎使用实时语音合成。" \
  --voice "服务端返回的音色名称" \
  --play \
  --output ./welcome.wav
```

不播放时省略 `--play`，仍会边接收边写 WAV。输出文件不会默认覆盖已有文件。

设计音色：

```bash
python ~/.claude/skills/tts-lychee/scripts/tts_client.py \
  --design-description "清晰、亲切、专业的女性声音" \
  --design-text "晚上好，今天辛苦了。"
```

用户确认试听后克隆并保存个人音色：

```bash
python ~/.claude/skills/tts-lychee/scripts/tts_client.py \
  --clone-url "设计接口返回的试听地址" \
  --clone-name "我的专业女声" \
  --confirm-clone
```

也可以将本地音频传给 `--clone-audio`。个人音色注册表保存在 `~/.lychee/tts-lychee/voices.json`，只保存别名和服务端返回的标识，不保存 API Key。

## 自检

```powershell
~/.claude/skills/tts-lychee/doctor.ps1
```

```bash
~/.claude/skills/tts-lychee/doctor.sh
```

也可以直接运行：

```bash
python ~/.claude/skills/tts-lychee/scripts/tts_client.py --doctor
```

自检不发起 TTS 合成，不产生音频费用；它会检查 Python、依赖、API Key 和旧版数据是否残留。

## 辅助命令

- `/tts-lychee-list-voices`：查询并展示当前公共音色。
- `/tts-lychee-search-voices <关键词>`：按名称搜索当前公共音色。

## 项目结构

```text
lychee-skills/
├── README.md
├── LICENSE
├── install.ps1
├── install.sh
├── .github/workflows/installers.yml
├── commands/
│   ├── tts-lychee-list-voices.md
│   └── tts-lychee-search-voices.md
├── skills/tts-lychee/
│   ├── SKILL.md
│   ├── requirements.txt
│   ├── doctor.ps1
│   ├── doctor.sh
│   └── scripts/
│       ├── tts_client.py
│       └── lychee_tts/
│           ├── api.py
│           ├── protocol.py
│           ├── sinks.py
│           ├── streaming.py
│           └── registry.py
└── tests/
    ├── conftest.py
    ├── test_api_contract.py
    ├── test_streaming_contract.py
    ├── test_sinks.py
    └── test_registry_contract.py
```

## License

MIT
