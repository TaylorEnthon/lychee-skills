# tts-lychee

`tts-lychee` is a Claude Code Skill for generating MP3 speech from Chinese text with preset voices for short-drama translation and dubbing workflows.

## Features

- Generate MP3 speech from text.
- Use preset voices such as 温柔女声, 甜美女声, 小男孩声音, 低沉男声, 东北话男声, 播音员男声, 旁白男声, 助眠女声.
- Supports natural voice descriptions such as 男童, 甜妹音, 小说旁白, 新闻播报男声, 性感女声.
- Provides slash commands:
  - `/tts-lychee` - generate MP3 speech.
  - `/tts-lychee-preview-match` - preview which public voice a description will use without synthesis.
  - `/tts-lychee-list-voices` - list supported public voices.

## Requirements

- Claude Code
- Python 3.8+
- Python package: `websocket-client`
- A TTS API Key from `https://shanhaistudio.lycheeai.com.cn/`

Install the Python dependency:

```bash
python -m pip install websocket-client
```

## Install

Windows PowerShell:

```powershell
.\install.ps1
```

macOS/Linux:

```bash
bash ./install.sh
```

The installer copies the Skill to:

```text
~/.claude/skills/tts-lychee
```

It also installs the helper slash commands to:

```text
~/.claude/commands
```

Restart Claude Code after installation.

## Configure API Key

Set `TTS_API_KEY` as a system/user environment variable. Do not paste the API Key into Claude Code chat or command lines.

Windows PowerShell:

```powershell
setx TTS_API_KEY "your-api-key"
```

macOS/Linux:

```bash
export TTS_API_KEY="your-api-key"
```

After setting it, restart Claude Code so it can inherit the environment variable.

## Usage

Generate speech:

```text
/tts-lychee 用播音员男声说：各位观众，欢迎收看本期节目。
```

Generate with a specified output path:

```text
/tts-lychee 用温柔女声生成 mp3，保存到 ./welcome.mp3：欢迎回来。
```

Preview voice matching without synthesis:

```text
/tts-lychee-preview-match 性感女声
```

List supported voices:

```text
/tts-lychee-list-voices
```

## Default Output

If no output path is specified, the generated file is saved in Claude Code's current working directory with a name like:

```text
20260519-203500-甜美女声_tts.mp3
```

## Install Check

Run the offline doctor check:

Windows PowerShell:

```powershell
~/.claude/skills/tts-lychee/doctor.ps1
```

macOS/Linux:

```bash
~/.claude/skills/tts-lychee/doctor.sh
```

The doctor check verifies Python, `websocket-client`, `TTS_API_KEY`, local data files, and voice matching. It does not synthesize audio and does not print the API Key.

## Supported Voice Groups

- 默认: 默认女声, 默认男声
- 女声: 温柔女声, 温柔姐姐, 知性女声, 成熟女声, 甜美女声, 可爱女声, 少女音, 萝莉音, 元气少女, 御姐音, 低沉女声, 冷艳女声, 老奶奶声音, 奶奶音
- 男声: 青年男声, 正常男声, 阳光男声, 低沉男声, 磁性男声, 大叔音, 霸道总裁音, 少年音, 清爽少年音, 老爷爷声音, 爷爷音
- 儿童: 儿童声, 小孩声音, 小女孩声音, 小男孩声音
- 高低音: 高音女声, 超高音女声, 低音男声, 超低音男声
- 耳语: 耳语女声, 耳语男声, 悄悄话女声, 悄悄话男声
- 方言: 四川话女声, 四川女生, 四川妹子, 四川话男声, 四川大叔, 东北话男声, 东北老铁, 东北话女声, 河南话男声, 河南大叔, 河南话女声, 陕西话男声, 陕西话女声, 贵州话女声, 贵州话男声, 云南话女声, 云南话男声, 甘肃话男声, 甘肃话女声, 宁夏话男声, 宁夏话女声, 青岛话男声, 青岛话女声, 石家庄话男声, 石家庄话女声, 济南话男声, 济南话女声, 桂林话男声, 桂林话女声
- 用途: 客服女声, 客服男声, 播音员女声, 播音员男声, 纪录片男声, 旁白男声, 助眠女声, 助眠男声

## Security Notes

- Do not commit real API Keys.
- Do not pass `TTS_API_KEY` inline in shell commands.
- The client reads `TTS_API_KEY` from the environment and uses it internally.
- Normal output hides internal fields such as `speaker_id`, `voice_id`, and alias matching details.
## Project Structure

```text
tts-lychee/
├── README.md
├── install.ps1
├── install.sh
├── commands/
│   ├── tts-lychee-preview-match.md
│   └── tts-lychee-list-voices.md
└── skills/
    └── tts-lychee/
        ├── SKILL.md
        ├── doctor.ps1
        ├── doctor.sh
        ├── scripts/
        │   └── tts_client.py
        └── data/
            ├── alias_map.json
            ├── presets.json
            ├── speaker_ids.json
            └── voice_aliases.json
```