# tts-lychee

文本转语音（Text-to-Speech）工具，支持多种中文音色，适合短剧翻译配音工作流。

## 功能

- 将中文文本合成为 MP3 音频
- 内置 76 种音色，覆盖女声、男声、儿童声、耳语、方言、播音员、旁白、助眠等类型
- 支持自然语言描述匹配音色（如"男童"→"小男孩声音"，"性感女声"→"御姐音"）
- 提供辅助命令：
  - `tts-lychee-preview-match` - 预览音色匹配结果（不合成音频）
  - `tts-lychee-list-voices` - 列出所有支持的音色

## 环境要求

- Python 3.8+
- `websocket-client` 包

## 安装依赖

```bash
python -m pip install websocket-client
```

## 安装

### 方式一：一键安装（Claude Code）

```bash
npx skills add TaylorEnthon/lychee-skills --skill tts-lychee
```

安装完成后重启 Claude Code，即可使用 `/tts-lychee` 命令。如需辅助命令（`/tts-lychee-preview-match`、`/tts-lychee-list-voices`），请使用方式二手动安装。

### 方式二：手动安装完整命令集

克隆仓库后，在仓库根目录运行：

**Windows PowerShell：**
```powershell
.\install.ps1
```

**macOS / Linux：**
```bash
bash ./install.sh
```

安装后需重启 AI 客户端（如 Claude Code）。脚本会自动将技能和命令文件复制到 `~/.claude/skills/tts-lychee` 和 `~/.claude/commands`。

## 配置 API Key

从 https://shanhaistudio.lycheeai.com.cn/ 获取 API Key，设置到环境变量 `TTS_API_KEY`。

**Windows PowerShell：**
```powershell
setx TTS_API_KEY "你的API密钥"
```

**macOS / Linux：**
```bash
export TTS_API_KEY="你的API密钥"
```

设置完成后重启 AI 客户端，使其继承新的环境变量。

## 使用方式

### AI 对话中触发

生成播音员男声：
```
/tts-lychee 用播音员男声说：各位观众，欢迎收看本期节目。
```

指定输出路径：
```
/tts-lychee 用温柔女声生成 mp3，保存到 ./welcome.mp3：欢迎回来。
```

预览音色匹配（不合成）：
```
/tts-lychee-preview-match 性感女声
```

列出所有音色：
```
/tts-lychee-list-voices
```

### 直接调用 Python 客户端

```bash
python ~/.claude/skills/tts-lychee/scripts/tts_client.py --text "欢迎使用" --voice "温柔女声"
```

指定输出文件：
```bash
python ~/.claude/skills/tts-lychee/scripts/tts_client.py --text "这是一段旁白" --voice "播音员男声" --output ./narration.mp3
```

## 默认输出

未指定输出路径时，文件保存在当前目录，命名为：
```
20260519-203500-甜美女声_tts.mp3
```

## 安装检查

**Windows PowerShell：**
```powershell
~/.claude/skills/tts-lychee/doctor.ps1
```

**macOS / Linux：**
```bash
~/.claude/skills/tts-lychee/doctor.sh
```

自检会验证 Python 环境、依赖包、环境变量、数据文件和音色匹配功能，不会合成音频或产生费用。

## 支持音色

### 默认

默认女声、默认男声

### 女声

温柔女声、温柔姐姐、知性女声、成熟女声、甜美女声、可爱女声、少女音、萝莉音、元气少女、御姐音、低沉女声、冷艳女声、老奶奶声音、奶奶音

### 男声

青年男声、正常男声、阳光男声、低沉男声、磁性男声、大叔音、霸道总裁音、少年音、清爽少年音、老爷爷声音、爷爷音

### 儿童

儿童声、小孩声音、小女孩声音、小男孩声音

### 高低音

高音女声、超高音女声、低音男声、超低音男声

### 耳语

耳语女声、耳语男声、悄悄话女声、悄悄话男声

### 方言

四川话女声、四川女生、四川妹子、四川话男声、四川大叔、东北话男声、东北老铁、东北话女声、河南话男声、河南大叔、河南话女声、陕西话男声、陕西话女声、贵州话女声、贵州话男声、云南话女声、云南话男声、甘肃话男声、甘肃话女声、宁夏话男声、宁夏话女声、青岛话男声、青岛话女声、石家庄话男声、石家庄话女声、济南话男声、济南话女声、桂林话男声、桂林话女声

### 用途

客服女声、客服男声、播音员女声、播音员男声、纪录片男声、旁白男声、助眠女声、助眠男声

## 自然语言匹配

| 说法 | 匹配音色 |
|------|---------|
| 男童、小男孩 | 小男孩声音 |
| 女童、小女孩 | 小女孩声音 |
| 甜妹音、甜美女生 | 甜美女声 |
| 新闻播报男声 | 播音员男声 |
| 小说旁白、故事旁白 | 旁白男声 |
| 性感女声、妩媚女声 | 御姐音 |
| 性感男声 | 磁性男声 |

## 安全注意

- 不要将真实 API Key 提交到代码仓库
- 不要在命令行中明文传递 API Key
- 客户端从环境变量读取 API Key，不会向用户展示

## 项目结构

```
lychee-skills/
├── README.md
├── LICENSE
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

## License

MIT