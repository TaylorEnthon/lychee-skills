# tts-lychee

文本转语音（Text-to-Speech）工具，支持多种中文音色，适合短剧翻译配音工作流。

## 功能

- 将中文文本合成为 MP3 音频
- 内置音色库，覆盖基础男女声、儿童与少年、音色特质、情绪风格、角色职业、方言口音、朗读播报、助眠放松等类型
- 支持自然语言描述匹配音色（如"男童"→"小男孩声音"，"性感女声"→"性感女声"）
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

### 方式一：一键安装

```bash
npx skills add TaylorEnthon/lychee-skills --skill tts-lychee
```

安装完成后重启 AI 客户端，即可使用 `/tts-lychee` 等命令。

### 方式二：手动安装完整命令集

克隆仓库后，在仓库根目录运行：

**Windows PowerShell 5.1 / PowerShell 7+：**
```powershell
.\install.ps1
```

如果当前 PowerShell 执行策略阻止脚本运行，可改用：
```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

**macOS / Linux bash：**
```bash
bash ./install.sh
```

安装后需重启 AI 客户端（如 Claude Code）。脚本会自动安装 `tts-lychee` Skill，并复制 `/tts-lychee-list-voices` 与 `/tts-lychee-preview-match` 这两个辅助命令到 `~/.claude/commands`。

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

音色库包含大量公开音色，按类别覆盖：

- 默认与基础：默认女声、默认男声、标准普通话女声、标准普通话男声
- 女声与男声：温柔女声、甜美女声、性感女声、御姐音、青年男声、磁性男声、低沉男声、大叔音
- 儿童与少年：甜美少女音、清爽少年音、正太音、可爱萝莉、中性儿童声、小女孩声音、小男孩声音
- 朗读播报：朗读女声、新闻播报男声、播音员女声、旁白男声、有声书女声、纪录片男声
- 情绪风格：深情款款女声、欢快活泼女声、悲伤沉重男声、恐怖悬疑男声、悬疑男声、神秘诡异男声
- 角色职业：客服女声、医生问诊男声、主持人女声、导航语音男声、销售女声、虚拟主播女声
- 方言口音：四川话女声、东北话男声、河南话女声、粤语男声、天津话女声、青岛话男声

使用 `/tts-lychee-list-voices` 查看当前安装版本按类别整理的公开音色。`女`、`男`、`女声`、`御姐` 等短名字仍可精确调用，但不会在自然语言包含匹配中抢占更具体音色。方言短名省略男女时默认匹配对应男声，例如 `云南话` 会匹配 `云南话男声`。

## 自然语言匹配

| 说法 | 匹配音色 |
|------|---------|
| 男童、小男孩 | 小男孩声音 |
| 女童、小女孩 | 小女孩声音 |
| 甜妹音、甜美女生 | 甜美女声 |
| 新闻播报男声 | 新闻播报男声 |
| 小说旁白、故事旁白 | 旁白男声 |
| 性感女声、性感的女声 | 性感女声 |
| 妩媚女声、魅惑女声 | 性感女声 |
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
            └── voice_aliases.json
```

## License

MIT
