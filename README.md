# Qwen3 ASR API - 长音视频语音识别系统

一个基于阿里云通义千问3 ASR Flash模型的长音视频语音识别系统，支持超过3分钟音频的智能分段识别和上下文管理。

## ✨ 特性

- 🎵 **多格式音频支持**：支持MP3、WAV、M4A、FLAC等常见音频格式
- 🔄 **智能音频转换**：自动转换为Opus格式以优化API调用
- 🎯 **VAD语音检测**：使用Silero-VAD进行精确的语音活动检测
- 📝 **智能分段处理**：将长音频分割为<3分钟片段，确保API兼容性
- 🧠 **上下文管理**：维护前文上下文，提高识别准确性
- ⚙️ **灵活配置**：支持命令行参数和配置文件
- 📊 **多种输出格式**：支持TXT、JSON、Markdown等输出格式
- 🔧 **错误恢复**：断点续传和智能重试机制

## 🚀 快速开始

### 环境要求

- Python 3.11+
- FFmpeg（用于音频转换）
- 阿里云DashScope API Key

### GUI 界面（wxPython）

项目提供 wxPython 图形界面：

```bash
# 启动 GUI（推荐用 uv）
uv run python run_gui.py

# 或模块方式
uv run python -m src.gui_wx.app
```

**GUI 特性**:
- 🎨 现代化界面设计（wxPython）
- 🌍 完整中文支持
- 📊 实时进度可视化
- ⚙️ 可配置参数（本地 JSON 配置）

### 安装

1. **克隆项目**
```bash
git clone <repository-url>
cd Qwen3_ASR_API
```

2. **安装依赖**
```bash
# 使用uv（推荐）
uv sync

# 或使用pip
pip install -r requirements.txt
```

3. **配置 API 密钥和设置**
```bash
# 复制配置模板文件
cp config/wx_gui_api_keys.example.json config/wx_gui_api_keys.json
cp config/wx_gui_config.example.json config/wx_gui_config.json

# 编辑配置文件，填入你的 API Key 和个人设置
# config/wx_gui_api_keys.json - 填入真实的 DashScope API Key
# config/wx_gui_config.json - 调整默认设置
```

**重要提醒**：配置文件已在 .gitignore 中忽略，不会被提交到版本控制，请放心填入真实密钥。

4. **依赖自动下载**
- 首次启动时会自动下载 Silero VAD 模型到 external/silero_vad/
- ffmpeg 优先使用系统 PATH；如未安装且在 Windows 上，可设置环境变量 FFMPEG_ZIP_URL 为包含 ffmpeg.exe/ffprobe.exe 的 ZIP，脚本会自动下载到 external/ffmpeg/
- 也可手动执行：
```bash
uv run python -m scripts.download_external
```

### 基本使用

```bash
# 基本用法
uv run main.py input.mp3

# 指定输出目录
uv run main.py input.mp3 --output-dir ./results

# 使用配置文件
uv run main.py input.mp3 --config config.json

# 批量处理
uv run main.py *.mp3 --batch
```

## 📖 详细使用说明

### 命令行参数

```bash
uv run main.py [音频文件] [选项]

必需参数:
  input_path              输入音频文件路径

可选参数:
  -o, --output-dir        输出目录 (默认: ./data/output)
  -c, --config           配置文件路径
  --format               输出格式 (txt|json|markdown, 默认: txt)
  --scene-description    场景描述

  --vad-threshold       VAD阈值 (0.0-1.0, 默认: 0.5)
  --max-segment-duration 最大片段时长(秒, 默认: 180)
  --preserve-silence    保留静音片段
  --batch               批量处理模式
  --verbose             详细输出
  --help                显示帮助信息
```

### 配置文件

创建JSON配置文件来保存常用设置：

```json
{
  "api": {
    "dashscope_api_key": "your_api_key",
    "asr_model": "qwen3-asr-flash"
  },
  "processing": {
    "max_segment_duration": 180,
    "max_segment_size": 10485760,
    "max_context_tokens": 9000
  },
  "vad": {
    "threshold": 0.5,
    "min_silence_duration": 0.5,
    "preserve_silence": false
  },
  "output": {
    "format": "txt",
    "include_timestamps": true,
    "include_confidence": true
  }
}
```

### 使用示例

查看 `scripts/example_usage.py` 了解更多使用示例：

```bash
# 运行示例脚本
uv run scripts/example_usage.py
```

## 🏗️ 项目架构

```
Qwen3_ASR_API/
├── src/                    # 源代码
│   ├── core/              # 核心业务逻辑
│   │   ├── audio_converter.py    # 音频格式转换
│   │   ├── vad_processor.py      # VAD语音活动检测
│   │   ├── segment_manager.py    # 音频片段管理
│   │   ├── asr_client.py         # ASR API客户端
│   │   ├── context_manager.py    # 上下文管理
│   │   └── pipeline.py           # 主流程编排
│   ├── utils/             # 工具函数
│   ├── config/            # 配置管理
│   └── models/            # 数据模型
├── data/                  # 数据目录
│   ├── input/            # 输入音频
│   └── output/           # 输出结果（CLI 未指定时默认写到音/视频同目录）
├── [系统临时目录]/qwen3_asr_api/  # 运行期临时文件（自动创建，可清理）
│   ├── converted/        # 转换后的 opus 临时文件
│   └── combined/         # 组合后的片段临时文件
├── external/             # 外部依赖
├── tests/               # 测试文件
├── scripts/             # 脚本文件
└── main.py              # 主程序入口
```

详细架构说明请参考 [architecture.md](architecture.md)

## 🔧 开发指南

### 运行测试

```bash
# 运行所有测试
uv run pytest

# 运行特定测试
uv run pytest tests/test_pipeline.py

# 运行端到端测试
uv run pytest tests/test_end_to_end.py
```

### 代码格式化

```bash
# 格式化代码
uv run black src/ tests/
uv run isort src/ tests/

# 检查代码质量
uv run flake8 src/ tests/
```

## 📊 性能特性

- **智能分段**：自动将长音频分割为最优大小的片段
- **并发处理**：支持多片段并行识别（可配置并发数）
- **内存优化**：流式处理，避免大文件内存占用
- **缓存机制**：已识别片段避免重复处理
- **断点续传**：支持中断后继续处理

## 🛠️ 故障排除

### 常见问题

1. **FFmpeg未找到**
   ```bash
   # Windows (使用Chocolatey)
   choco install ffmpeg
   
   # macOS (使用Homebrew)
   brew install ffmpeg
   
   # Linux (Ubuntu/Debian)
   sudo apt install ffmpeg
   ```

2. **API Key错误**
   - 确保在.env文件中正确设置了DASHSCOPE_API_KEY
   - 检查API Key是否有效且有足够余额

3. **模型下载失败**
   ```bash
   # 手动下载Silero VAD模型
   uv run scripts/download_silero_vad.py --force
   ```

4. **内存不足**
   - 减少max_segment_duration参数
   - 降低并发处理数量
   - 确保有足够的磁盘空间用于临时文件

### 日志调试

```bash
# 启用详细日志
uv run main.py input.mp3 --verbose

# 查看处理日志
tail -f data/output/process.log
```

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

## 🤝 贡献

欢迎提交Issue和Pull Request！

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启Pull Request

## 📞 支持

如果您遇到问题或有建议，请：

- 提交 [Issue](../../issues)
- 查看 [Wiki](../../wiki) 文档
- 参考 [FAQ](../../wiki/FAQ)

## 🙏 致谢

- [阿里云通义千问](https://dashscope.aliyun.com/) - 提供ASR API服务
- [Silero VAD](https://github.com/snakers4/silero-vad) - 语音活动检测模型
- [FFmpeg](https://ffmpeg.org/) - 音频处理工具

---

**注意**：使用本系统需要阿里云DashScope API Key，请确保遵守相关服务条款和使用限制。