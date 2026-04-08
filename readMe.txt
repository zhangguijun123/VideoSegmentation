视频语言检测、翻译与字幕添加工具

## 功能特性
- 自动检测视频语音语言（日语/英语）
- 语音识别（Whisper）并显示原文字幕
- 自动翻译检测到的语言到中文（支持其他语言）
- 双语字幕显示（原文在上，译文在下）
- 多语言关键词提取（日语动词、英语名词/动词）
- 场景自动分割
- Logo动画叠加

## 快速开始
1. 安装依赖：
   ```
   pip install -r requirements.txt
   ```

2. 配置 `config.yaml`：
   - 设置输入视频路径或通过命令行参数 `--input` 指定
   - 调整字幕位置、字体、颜色等
   - 启用/禁用翻译功能

3. 运行处理：
   ```
   python main.py --input "你的视频文件.mp4"
   ```

## 配置文件说明 (config.yaml)

### 语音识别
```yaml
speech_recognition:
  model: "base"           # Whisper模型大小 (tiny, base, small, medium, large)
  language: "ja"          # 默认语言，设为 "auto" 以自动检测
  auto_detect: true       # 是否自动检测语言
```

### 翻译功能
```yaml
translation:
  enabled: true           # 启用翻译
  target_language: "zh-CN" # 目标语言 (zh-CN: 简体中文)
  show_original: true     # 是否显示原文
  translator: "googletrans" # 翻译引擎
  api_timeout: 10         # API超时时间
```

### 关键词提取
```yaml
keywords:
  max_keywords_per_scene: 8     # 每场景最大关键词数
  parts_of_speech: ["動詞"]     # 日语词性，英语会自动映射
  min_frequency: 1              # 最小出现频率
  stopwords_path: "data/stopwords_ja.txt" # 停用词文件
```

### 字幕设置
```yaml
subtitle:
  show_dialogue: true           # 显示对话字幕
  show_keywords: false          # 显示关键词
  dialogue_position: "bottom_center" # 字幕位置
  dialogue_font_size: 24        # 对话字体大小
  dialogue_max_chars_per_line: 18 # 每行最大字符数
  dialogue_max_lines: 2         # 最大行数（双语字幕建议设为4）
```

## 支持的语言
- 语音识别：Whisper支持的所有语言
- 翻译：Google翻译支持的所有语言
- 关键词提取：日语、英语

## 输出文件
处理完成后，在 `output/` 目录下生成：
- `scenes/`：处理后的视频片段（带字幕）
- `transcripts/`：原始转录文本
- `keywords/`：关键词JSON文件（包含语言和翻译信息）

## 高级用法
### 仅处理日语视频（禁用自动检测）
```yaml
speech_recognition:
  language: "ja"
  auto_detect: false
translation:
  enabled: false
```

### 仅显示译文（不显示原文）
```yaml
translation:
  enabled: true
  show_original: false
```

### 调整双语字幕行数
```yaml
subtitle:
  dialogue_max_lines: 4  # 原文2行 + 译文2行
```

## 注意事项
1. 首次使用英语关键词提取时会自动下载nltk数据
2. 翻译功能需要网络连接
3. 建议使用GPU加速Whisper识别
4. 字幕行数过多可能导致显示不全，请调整 `dialogue_max_lines` 和 `dialogue_max_chars_per_line`

## 示例命令
```bash
# 处理日语视频，自动翻译中文，显示双语字幕
python main.py --input "japanese_video.mp4"

# 处理英语视频，提取英语关键词
python main.py --input "english_video.mp4"

# 使用自定义配置文件
python main.py --config "my_config.yaml" --input "video.mp4"
```

## 版本历史
- v1.0: 初始版本，日语视频处理
- v2.0: 新增语言检测、翻译、双语字幕、英语关键词提取