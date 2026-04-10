import os
import subprocess
import json
from typing import List, Dict, Any, Optional

from utils.logger import get_logger
from utils.video_utils import run_ffmpeg
from modules.keyword_extractor import filter_keywords_by_kanji_priority


def escape_drawtext(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
    )


def escape_drawtext_for_filter_complex(text: str) -> str:
    """
    专门为 -filter_complex 模式的 drawtext 转义文本。
    
    与 escape_drawtext() 的关键区别：
    - filter_complex 中的 drawtext text 参数通常用单引号包裹
    - FFmpeg 的单引号字符串解析器不支持 \\' 转义
    - 因此必须将单引号替换为 Unicode 右单引号（U+2019），避免破坏语法
    
    同时保留 : 和 % 的转义，以及 \\ 的转义。
    """
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        # 将 ASCII 单引号替换为 Unicode 右单引号，避免破坏 FFmpeg 单引号字符串语法
        .replace("'", "\u2019")
        .replace("%", "\\%")
    )


def escape_drawtext_keep_newlines(text: str) -> str:
    """
    保留换行符的 drawtext 文本转义。
    
    使用 escape_drawtext_for_filter_complex() 替代原来的 escape_drawtext()，
    因为 -filter_complex 模式下的单引号字符串不支持 \\' 转义，
    必须将单引号替换为 Unicode 字符（U+2019）以避免破坏 FFmpeg 滤镜语法。
    """
    # 先将换行符替换为特殊标记，避免被转义处理
    placeholder = "___NEWLINE___"
    text = text.replace("\n", placeholder)
    # 使用安全的 filter_complex 版本转义（单引号 → Unicode 右单引号）
    text = escape_drawtext_for_filter_complex(text)
    # 将标记替换为实际的换行字符（ASCII 10）
    return text.replace(placeholder, "\n")


def get_video_resolution(video_path: str) -> tuple[int, int]:
    """
    获取视频分辨率（宽度, 高度）
    
    Args:
        video_path: 视频文件路径
        
    Returns:
        (width, height) 元组
    """
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            "-select_streams", "v:0",
            video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return 1920, 1080  # 默认分辨率
        
        data = json.loads(result.stdout)
        if data.get("streams") and len(data["streams"]) > 0:
            stream = data["streams"][0]
            width = stream.get("width", 1920)
            height = stream.get("height", 1080)
            return width, height
        return 1920, 1080
    except Exception:
        return 1920, 1080  # 出错时返回默认分辨率


def resolve_font_path(subtitle_cfg: Dict[str, Any]) -> str:
    font_path = subtitle_cfg.get("font_path", "")
    if font_path:
        return font_path

    candidates = [
        r"C:\\Windows\\Fonts\\meiryo.ttc",
        r"C:\\Windows\\Fonts\\msgothic.ttc",
        r"C:\\Windows\\Fonts\\YuGothM.ttc",
        r"C:\\Windows\\Fonts\\msyh.ttc",
    ]


    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    return ""


def resolve_logo_image_path(subtitle_cfg: Dict[str, Any]) -> str:
    logo_image_path = subtitle_cfg.get("logo_image_path", "")
    if not logo_image_path:
        return ""

    if os.path.isabs(logo_image_path):
        return logo_image_path if os.path.exists(logo_image_path) else ""

    candidate = os.path.join(os.getcwd(), logo_image_path)
    return candidate if os.path.exists(candidate) else ""


def resolve_japanese_font_path(subtitle_cfg: Dict[str, Any]) -> str:
    """
    解析日文字体路径
    优先使用配置中的japanese_font_path，否则检查常见日文字体
    """
    font_path = subtitle_cfg.get("japanese_font_path", "")
    if font_path:
        return font_path
    
    # 常见日文字体候选
    candidates = [
        r"C:\\Windows\\Fonts\\meiryo.ttc",
        r"C:\\Windows\\Fonts\\msgothic.ttc",
        r"C:\\Windows\\Fonts\\YuGothM.ttc",
        r"C:\\Windows\\Fonts\\YuMincho.ttc",
        r"C:\\Windows\\Fonts\\MSMINCHO.TTF",
        r"C:\\Windows\\Fonts\\MSGOTHIC.TTC",
    ]
    
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    
    # 回退到通用字体路径
    return resolve_font_path(subtitle_cfg)

def resolve_chinese_font_path(subtitle_cfg: Dict[str, Any]) -> str:
    """
    解析中文字体路径
    优先使用配置中的chinese_font_path，否则检查常见中文字体
    """
    font_path = subtitle_cfg.get("chinese_font_path", "")
    if font_path:
        return font_path
    
    # 常见中文字体候选
    candidates = [
        r"C:\\Windows\\Fonts\\msyh.ttc",           # 微软雅黑
        r"C:\\Windows\\Fonts\\simhei.ttf",         # 黑体
        r"C:\\Windows\\Fonts\\simsun.ttc",         # 宋体
        r"C:\\Windows\\Fonts\\simkai.ttf",         # 楷体
        r"C:\\Windows\\Fonts\\simfang.ttf",        # 仿宋
        r"C:\\Windows\\Fonts\\Deng.ttf",           # 等线
        r"C:\\Windows\\Fonts\\Dengb.ttf",          # 等线 Bold
    ]
    
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    
    # 回退到通用字体路径
    return resolve_font_path(subtitle_cfg)


def resolve_keywords_position(subtitle_cfg: Dict[str, Any]) -> str:
    """
    解析关键词显示位置，支持垂直左侧布局
    如果logo位于左上角，关键词将显示在logo下方
    """
    position = subtitle_cfg.get("keywords_position", "left_vertical")
    margin = subtitle_cfg.get("margin", 20)
    
    # 计算logo影响的高度
    logo_y_offset = 0
    logo_position = subtitle_cfg.get("logo_position", "top_left")
    logo_image_path = resolve_logo_image_path(subtitle_cfg)
    
    if logo_image_path and logo_position == "top_left":
        # 估算logo高度
        logo_max_width = subtitle_cfg.get("logo_max_width", 60)
        logo_scale = subtitle_cfg.get("logo_scale", 0.04)
        logo_width = subtitle_cfg.get("logo_width", 180)
        
        # 优先使用logo_max_width作为logo宽度
        logo_w = logo_max_width if logo_max_width > 0 else logo_width
        # 假设logo为正方形，高度等于宽度
        estimated_logo_height = logo_w
        # 加上logo_margin
        logo_margin = subtitle_cfg.get("logo_margin", margin)
        logo_y_offset = logo_margin + estimated_logo_height + 10  # 10像素间距
    
    if position == "left_vertical":
        # 左侧垂直排列，从顶部开始，考虑logo偏移
        y = margin + logo_y_offset
        return f"x={margin}:y={y}"
    elif position == "top_right":
        return f"x=w-tw-{margin}:y={margin}"
    elif position == "top_left":
        # 左上角位置，也考虑logo偏移
        y = margin + logo_y_offset
        return f"x={margin}:y={y}"
    elif position == "top_center":
        return f"x=(w-tw)/2:y={margin}"
    elif position == "bottom_left":
        return f"x={margin}:y=h-th-{margin}"
    elif position == "bottom_center":
        return f"x=(w-tw)/2:y=h-th-{margin}"
    elif position == "none":
        return ""  # 空字符串表示不显示
    else:
        # 默认使用左侧垂直布局
        y = margin + logo_y_offset
        return f"x={margin}:y={y}"

def resolve_position(subtitle_cfg: Dict[str, Any]) -> str:
    position = subtitle_cfg.get("position", "bottom_right")
    margin = subtitle_cfg.get("margin", 20)

    if position == "top_right":
        return f"x=w-tw-{margin}:y={margin}"
    if position == "top_left":
        return f"x={margin}:y={margin}"
    if position == "top_center":
        return f"x=(w-tw)/2:y={margin}"
    if position == "bottom_left":
        return f"x={margin}:y=h-th-{margin}"
    if position == "bottom_center":
        return f"x=(w-tw)/2:y=h-th-{margin}"

    return f"x=w-tw-{margin}:y=h-th-{margin}"


def resolve_overlay_position(position: str, margin: int) -> str:
    if position == "top_right":
        return f"main_w-overlay_w-{margin}:{margin}"
    if position == "top_left":
        return f"{margin}:{margin}"
    if position == "top_center":
        return f"(main_w-overlay_w)/2:{margin}"
    if position == "bottom_left":
        return f"{margin}:main_h-overlay_h-{margin}"
    if position == "bottom_center":
        return f"(main_w-overlay_w)/2:main_h-overlay_h-{margin}"

    return f"main_w-overlay_w-{margin}:main_h-overlay_h-{margin}"


def parse_overlay_position(position_str: str) -> tuple[str, str]:
    """
    解析overlay位置字符串，返回(x_expr, y_expr)元组
    """
    if ":" in position_str:
        x_expr, y_expr = position_str.split(":", 1)
        return x_expr.strip(), y_expr.strip()
    return "0", "0"


def build_drawtext_filter(keywords: List[str], subtitle_cfg: Dict[str, Any]) -> str:
    if not subtitle_cfg.get("show_keywords", True):
        return ""

    if not keywords:
        return ""

    # 检查关键词位置配置，如果为"none"则不显示
    keywords_position = subtitle_cfg.get("keywords_position", "left_vertical")
    if keywords_position == "none":
        return ""

    # 应用汉字优先级筛选和数量限制
    max_display = subtitle_cfg.get("keywords_max_display", 10)
    filtered_keywords = filter_keywords_by_kanji_priority(keywords, max_display)
    
    if not filtered_keywords:
        return ""

    text_raw = "\n".join(filtered_keywords)
    text = escape_drawtext_keep_newlines(text_raw)

    # 获取字体颜色，优先使用关键词专用颜色配置
    font_color = subtitle_cfg.get("keywords_font_color", subtitle_cfg.get("font_color", "white"))
    # 获取字体大小，优先使用关键词专用字体大小配置
    font_size = subtitle_cfg.get("keywords_font_size", subtitle_cfg.get("font_size", 36))
    font_weight = subtitle_cfg.get("keywords_font_weight", subtitle_cfg.get("font_weight", "normal"))
    box_color = subtitle_cfg.get("box_color", "black")
    box_opacity = subtitle_cfg.get("box_opacity", 0.45)
    line_spacing = subtitle_cfg.get("line_spacing", 6)
    font_path = resolve_font_path(subtitle_cfg)  # 使用通用字体路径，关键词用日文字体
    position_expr = resolve_keywords_position(subtitle_cfg)
    keywords_box_enabled = subtitle_cfg.get("keywords_box_enabled", False)  # 默认禁用背景框
    
    # 字体效果配置
    outline_enabled = subtitle_cfg.get("keywords_font_outline_enabled", True)
    outline_color = subtitle_cfg.get("keywords_font_outline_color", "black@0.8")
    outline_width = subtitle_cfg.get("keywords_font_outline_width", 2)
    shadow_enabled = subtitle_cfg.get("keywords_font_shadow_enabled", True)
    shadow_x = subtitle_cfg.get("keywords_font_shadow_x", 2)
    shadow_y = subtitle_cfg.get("keywords_font_shadow_y", 2)
    shadow_color = subtitle_cfg.get("keywords_font_shadow_color", "black@0.6")
    
    # 如果位置表达式为空（例如配置为"none"），则不显示
    if not position_expr:
        return ""

    parts = [
        "drawtext=",
    ]

    if font_path:
        parts.append(f"fontfile='{escape_drawtext(font_path)}':")

    # 构建滤镜参数
    filter_parts = [
        f"text='{text}':fontcolor={font_color}:fontsize={font_size}:"
    ]
    
    if keywords_box_enabled:
        # 启用背景框
        filter_parts.append(f"box=1:boxcolor={box_color}@{box_opacity}:boxborderw=10:")
    else:
        # 透明背景，根据配置添加描边和阴影
        filter_parts.append(f"box=0:")
        
        if outline_enabled:
            filter_parts.append(f"bordercolor={outline_color}:borderw={outline_width}:")
        
        if shadow_enabled:
            filter_parts.append(f"shadowx={shadow_x}:shadowy={shadow_y}:shadowcolor={shadow_color}:")
    
    filter_parts.append(f"line_spacing={line_spacing}:{position_expr}")
    
    parts.append("".join(filter_parts))

    return "".join(parts)


def resolve_logo_font_path(subtitle_cfg: Dict[str, Any]) -> str:
    logo_font_path = subtitle_cfg.get("logo_font_path", "")
    if logo_font_path:
        return logo_font_path

    candidates = [
        r"C:\\Windows\\Fonts\\msyh.ttc",
        r"C:\\Windows\\Fonts\\simhei.ttf",
        r"C:\\Windows\\Fonts\\simsun.ttc",
    ]

    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    return resolve_font_path(subtitle_cfg)


def wrap_logo_text(text: str, max_chars_per_line: int) -> str:
    if max_chars_per_line <= 0 or len(text) <= max_chars_per_line:
        return text

    lines = [text[i : i + max_chars_per_line] for i in range(0, len(text), max_chars_per_line)]
    return "\n".join(lines)


def wrap_dialogue_text(text: str, max_chars_per_line: int, max_lines: int) -> str:
    if not text:
        return ""

    if max_chars_per_line <= 0:
        return text

    lines = [text[i : i + max_chars_per_line] for i in range(0, len(text), max_chars_per_line)]
    if max_lines > 0:
        lines = lines[:max_lines]
    return "\n".join(lines)



def build_logo_filter(subtitle_cfg: Dict[str, Any]) -> str:
    logo_text = subtitle_cfg.get("logo_text", "")
    if not logo_text:
        return ""

    logo_position = subtitle_cfg.get("logo_position", "top_left")
    logo_margin = subtitle_cfg.get("logo_margin", subtitle_cfg.get("margin", 20))
    logo_max_chars = subtitle_cfg.get("logo_max_chars_per_line", 0)

    position_cfg = {"position": logo_position, "margin": logo_margin}
    position_expr = resolve_position(position_cfg)

    text_raw = wrap_logo_text(logo_text, logo_max_chars)
    text = escape_drawtext_keep_newlines(text_raw)

    font_color = subtitle_cfg.get("logo_font_color", subtitle_cfg.get("font_color", "white"))
    font_size = subtitle_cfg.get("logo_font_size", max(24, int(subtitle_cfg.get("font_size", 36) * 0.8)))
    box_color = subtitle_cfg.get("logo_box_color", subtitle_cfg.get("box_color", "black"))
    box_opacity = subtitle_cfg.get("logo_box_opacity", subtitle_cfg.get("box_opacity", 0.45))
    font_path = resolve_logo_font_path(subtitle_cfg)


    parts = [
        "drawtext=",
    ]

    if font_path:
        parts.append(f"fontfile='{escape_drawtext(font_path)}':")

    parts.append(
        f"text='{text}':fontcolor={font_color}:fontsize={font_size}:"
        f"box=1:boxcolor={box_color}@{box_opacity}:boxborderw=10:"
        f"{position_expr}"
    )

    return "".join(parts)





def build_dialogue_filter(dialogue_text: str, subtitle_cfg: Dict[str, Any]) -> str:
    if not subtitle_cfg.get("show_dialogue", True):
        return ""

    if not dialogue_text:
        return ""

    dialogue_position = subtitle_cfg.get("dialogue_position", "bottom_center")
    dialogue_margin = subtitle_cfg.get("dialogue_margin", subtitle_cfg.get("margin", 20))
    dialogue_max_chars = subtitle_cfg.get("dialogue_max_chars_per_line", 18)
    dialogue_max_lines = subtitle_cfg.get("dialogue_max_lines", 2)

    position_cfg = {"position": dialogue_position, "margin": dialogue_margin}
    position_expr = resolve_position(position_cfg)

    text_raw = wrap_dialogue_text(dialogue_text, dialogue_max_chars, dialogue_max_lines)
    text = escape_drawtext_keep_newlines(text_raw)

    font_color = subtitle_cfg.get("dialogue_font_color", subtitle_cfg.get("font_color", "white"))
    font_size = subtitle_cfg.get("dialogue_font_size", subtitle_cfg.get("font_size", 24))
    font_weight = subtitle_cfg.get("dialogue_font_weight", subtitle_cfg.get("font_weight", "normal"))
    box_color = subtitle_cfg.get("dialogue_box_color", subtitle_cfg.get("box_color", "black"))
    box_opacity = subtitle_cfg.get("dialogue_box_opacity", subtitle_cfg.get("box_opacity", 0.45))
    line_spacing = subtitle_cfg.get("dialogue_line_spacing", subtitle_cfg.get("line_spacing", 6))
    font_path = resolve_font_path(subtitle_cfg)

    parts = [
        "drawtext=",
    ]

    if font_path:
        parts.append(f"fontfile='{escape_drawtext(font_path)}':")

    parts.append(
        f"text='{text}':fontcolor={font_color}:fontsize={font_size}:"
        f"box=1:boxcolor={box_color}@{box_opacity}:boxborderw=10:"
        f"line_spacing={line_spacing}:{position_expr}"
    )

    return "".join(parts)

def resolve_bilingual_position(subtitle_cfg: Dict[str, Any]) -> tuple[str, str]:
    """
    返回双语字幕的位置表达式：(original_position, translation_position)
    原文在上，译文在下，垂直堆叠
    """
    dialogue_position = subtitle_cfg.get("dialogue_position", "bottom_center")
    dialogue_margin = subtitle_cfg.get("dialogue_margin", subtitle_cfg.get("margin", 20))
    
    # 计算基线位置（译文的位置）
    if dialogue_position == "bottom_center":
        base_x = f"(w-tw)/2"
        base_y = f"h-th-{dialogue_margin}"
    elif dialogue_position == "bottom_left":
        base_x = f"{dialogue_margin}"
        base_y = f"h-th-{dialogue_margin}"
    elif dialogue_position == "bottom_right":
        base_x = f"w-tw-{dialogue_margin}"
        base_y = f"h-th-{dialogue_margin}"
    elif dialogue_position == "top_center":
        base_x = f"(w-tw)/2"
        base_y = f"{dialogue_margin}"
    elif dialogue_position == "top_left":
        base_x = f"{dialogue_margin}"
        base_y = f"{dialogue_margin}"
    elif dialogue_position == "top_right":
        base_x = f"w-tw-{dialogue_margin}"
        base_y = f"{dialogue_margin}"
    else:
        # 默认底部居中
        base_x = f"(w-tw)/2"
        base_y = f"h-th-{dialogue_margin}"
    
    # 原文在译文上方，需要知道译文文本高度
    # 由于无法预先知道译文高度，我们使用估计值：字体大小 + 行间距
    font_size = subtitle_cfg.get("dialogue_font_size", subtitle_cfg.get("font_size", 24))
    line_spacing = subtitle_cfg.get("dialogue_line_spacing", subtitle_cfg.get("line_spacing", 6))
    # 估计行高：字体大小 + 行间距
    line_height = font_size + line_spacing
    
    # 原文位置：在译文上方一个行高处
    # 注意：th是文本高度，但每个文本不同。我们使用固定偏移量
    # 使用表达式：y = base_y - line_height
    original_y = f"({base_y})-{line_height}"
    
    original_pos = f"x={base_x}:y={original_y}"
    translation_pos = f"x={base_x}:y={base_y}"
    
    return original_pos, translation_pos

def build_original_text_filter(original_text: str, subtitle_cfg: Dict[str, Any]) -> str:
    """
    构建原文（日文）字幕滤镜
    """
    if not original_text:
        return ""
    
    # 检查是否显示对话字幕
    if not subtitle_cfg.get("show_dialogue", True):
        return ""
    
    # 根据显示模式决定是否显示原文
    display_mode = subtitle_cfg.get("dialogue_display_mode", "both")
    if display_mode not in ["both", "original_only"]:
        return ""
    
    # 文本换行处理
    max_chars = subtitle_cfg.get("dialogue_max_chars_per_line", 18)
    max_lines = subtitle_cfg.get("original_max_lines", subtitle_cfg.get("dialogue_max_lines", 1))
    text_raw = wrap_dialogue_text(original_text, max_chars, max_lines)
    if not text_raw:
        return ""
    
    text = escape_drawtext_keep_newlines(text_raw)
    
    # 样式配置
    font_color = subtitle_cfg.get("dialogue_font_color", subtitle_cfg.get("font_color", "white"))
    font_size = subtitle_cfg.get("dialogue_font_size", subtitle_cfg.get("font_size", 24))
    font_weight = subtitle_cfg.get("dialogue_font_weight", subtitle_cfg.get("font_weight", "normal"))
    box_color = subtitle_cfg.get("dialogue_box_color", subtitle_cfg.get("box_color", "black"))
    box_opacity = subtitle_cfg.get("dialogue_box_opacity", subtitle_cfg.get("box_opacity", 0.45))
    line_spacing = subtitle_cfg.get("dialogue_line_spacing", subtitle_cfg.get("line_spacing", 6))
    font_path = resolve_japanese_font_path(subtitle_cfg)  # 使用日文字体
    
    # 获取位置
    original_pos, _ = resolve_bilingual_position(subtitle_cfg)
    
    parts = [
        "drawtext=",
    ]
    
    if font_path:
        parts.append(f"fontfile='{escape_drawtext(font_path)}':")
    
    parts.append(
        f"text='{text}':fontcolor={font_color}:fontsize={font_size}:"
        f"box=1:boxcolor={box_color}@{box_opacity}:boxborderw=10:"
        f"line_spacing={line_spacing}:{original_pos}"
    )
    
    return "".join(parts)

def build_translation_text_filter(translation_text: str, subtitle_cfg: Dict[str, Any]) -> str:
    """
    构建译文（中文）字幕滤镜
    """
    if not translation_text:
        return ""
    
    # 检查是否显示对话字幕
    if not subtitle_cfg.get("show_dialogue", True):
        return ""
    
    # 根据显示模式决定是否显示译文
    display_mode = subtitle_cfg.get("dialogue_display_mode", "both")
    if display_mode not in ["both", "translation_only"]:
        return ""
    
    # 文本换行处理
    max_chars = subtitle_cfg.get("dialogue_max_chars_per_line", 18)
    max_lines = subtitle_cfg.get("translation_max_lines", subtitle_cfg.get("dialogue_max_lines", 1))
    text_raw = wrap_dialogue_text(translation_text, max_chars, max_lines)
    if not text_raw:
        return ""
    
    text = escape_drawtext_keep_newlines(text_raw)
    
    # 样式配置
    font_color = subtitle_cfg.get("dialogue_font_color", subtitle_cfg.get("font_color", "white"))
    font_size = subtitle_cfg.get("dialogue_font_size", subtitle_cfg.get("font_size", 24))
    font_weight = subtitle_cfg.get("dialogue_font_weight", subtitle_cfg.get("font_weight", "normal"))
    box_color = subtitle_cfg.get("dialogue_box_color", subtitle_cfg.get("box_color", "black"))
    box_opacity = subtitle_cfg.get("dialogue_box_opacity", subtitle_cfg.get("box_opacity", 0.45))
    line_spacing = subtitle_cfg.get("dialogue_line_spacing", subtitle_cfg.get("line_spacing", 6))
    font_path = resolve_chinese_font_path(subtitle_cfg)  # 使用中文字体
    
    # 获取位置
    _, translation_pos = resolve_bilingual_position(subtitle_cfg)
    
    parts = [
        "drawtext=",
    ]
    
    if font_path:
        parts.append(f"fontfile='{escape_drawtext(font_path)}':")
    
    parts.append(
        f"text='{text}':fontcolor={font_color}:fontsize={font_size}:"
        f"box=1:boxcolor={box_color}@{box_opacity}:boxborderw=10:"
        f"line_spacing={line_spacing}:{translation_pos}"
    )
    
    return "".join(parts)

def export_scene_with_keywords(
    input_path: str,
    start: float,
    end: float,
    output_path: str,
    keywords: List[str],
    subtitle_cfg: Dict[str, Any],
    dialogue_text: str,
    translated_text: Optional[str] = None,
    segments: Optional[List[Dict[str, Any]]] = None,
    translated_segments: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """
    导出带关键词和双语字幕的视频场景
    
    Args:
        input_path: 输入视频路径
        start: 开始时间（秒）
        end: 结束时间（秒）
        output_path: 输出视频路径
        keywords: 关键词列表
        subtitle_cfg: 字幕配置
        dialogue_text: 原文对话文本（向后兼容）
        translated_text: 译文对话文本（可选，向后兼容）
        segments: 原文分段列表，每个元素包含 start, end, text
                  start和end是相对于整个视频的绝对时间
        translated_segments: 译文分段列表，每个元素包含 start, end, text
    """
    # 构建关键词滤镜
    logger = get_logger()
    
    # 获取视频分辨率并自适应缩放配置
    video_width, video_height = get_video_resolution(input_path)
    # 以1080p为基准（高度1080），计算缩放因子
    scale_factor = video_height / 1080.0
    
    # 创建缩放后的配置副本
    scaled_cfg = subtitle_cfg.copy()
    
    # 缩放字体相关尺寸
    font_keys = [
        "font_size", "dialogue_font_size", "logo_font_size", "keywords_font_size",
        "keywords_font_outline_width", "keywords_font_shadow_x", "keywords_font_shadow_y"
    ]
    for key in font_keys:
        if key in scaled_cfg and isinstance(scaled_cfg[key], (int, float)):
            scaled_cfg[key] = int(round(scaled_cfg[key] * scale_factor))
    
    # 缩放边距相关尺寸
    margin_keys = [
        "margin", "dialogue_margin", "logo_margin",
        "keywords_font_outline_width", "keywords_font_shadow_x", "keywords_font_shadow_y"
    ]
    for key in margin_keys:
        if key in scaled_cfg and isinstance(scaled_cfg[key], (int, float)):
            scaled_cfg[key] = int(round(scaled_cfg[key] * scale_factor))
    
    # 缩放logo相关尺寸（像素值部分）
    if "logo_max_width" in scaled_cfg and isinstance(scaled_cfg["logo_max_width"], (int, float)):
        scaled_cfg["logo_max_width"] = int(round(scaled_cfg["logo_max_width"] * scale_factor))
    if "logo_width" in scaled_cfg and isinstance(scaled_cfg["logo_width"], (int, float)):
        scaled_cfg["logo_width"] = int(round(scaled_cfg["logo_width"] * scale_factor))
    
    logger.debug(f"视频分辨率: {video_width}x{video_height}, 缩放因子: {scale_factor:.3f}")
    
    # 使用缩放后的配置替换原始配置
    subtitle_cfg = scaled_cfg
    
    drawtext = build_drawtext_filter(keywords, subtitle_cfg)
    
    filters = []
    
    # 调试信息：输出分段信息
    logger.debug(f"字幕分段模式: segments={segments}, translated_segments={translated_segments}")
    
    # 判断是否使用分段模式
    use_segmented_mode = segments is not None and len(segments) > 0
    logger.debug(f"分段模式启用: {use_segmented_mode}, 分段数量: {len(segments) if segments else 0}")
    
    if use_segmented_mode:
        # 分段模式：为每个分段构建带时间控制的字幕滤镜
        for i, seg in enumerate(segments):
            seg_start = seg.get("start", 0)
            seg_end = seg.get("end", 0)
            seg_text = seg.get("text", "").strip()
            
            if not seg_text:
                continue
            
            # 将绝对时间转换为相对于场景开始的时间
            # 因为FFmpeg命令使用了-ss start，所以时间轴从0开始
            rel_start = seg_start - start
            rel_end = seg_end - start
            
            # 确保时间在场景范围内且有效
            if rel_start < 0:
                rel_start = 0
            if rel_end > (end - start):
                rel_end = end - start
            if rel_start >= rel_end:
                continue
            
            logger.debug(f"分段 {i}: 绝对时间 [{seg_start:.2f}-{seg_end:.2f}], 相对时间 [{rel_start:.2f}-{rel_end:.2f}], 文本: {seg_text[:50]}{'...' if len(seg_text) > 50 else ''}")
            
            # 构建原文字幕滤镜
            original_filter = build_timed_original_filter(seg_text, rel_start, rel_end, subtitle_cfg)
            if original_filter:
                filters.append(original_filter)
            
            # 构建译文字幕滤镜（如果有对应的译文分段）
            if translated_segments and i < len(translated_segments):
                trans_seg = translated_segments[i]
                trans_text = trans_seg.get("text", "").strip()
                if trans_text:
                    # 使用相同的时间范围
                    translation_filter = build_timed_translation_filter(trans_text, rel_start, rel_end, subtitle_cfg)
                    if translation_filter:
                        filters.append(translation_filter)
            elif translated_text:
                # 向后兼容：如果没有译文分段但有整个译文文本，使用整个译文
                # 注意：这会将整个译文用于所有分段，可能不是最佳效果
                translation_filter = build_timed_translation_filter(translated_text, rel_start, rel_end, subtitle_cfg)
                if translation_filter:
                    filters.append(translation_filter)
    else:
        # 向后兼容：旧模式，整个场景显示相同的字幕
        # 构建双语字幕滤镜
        original_filter = build_original_text_filter(dialogue_text, subtitle_cfg)
        
        # 根据是否有译文决定如何构建译文滤镜
        if translated_text:
            translation_filter = build_translation_text_filter(translated_text, subtitle_cfg)
        else:
            # 如果没有译文，根据显示模式决定是否显示原文
            # 如果显示模式是 translation_only，则不显示任何字幕
            display_mode = subtitle_cfg.get("dialogue_display_mode", "both")
            if display_mode == "translation_only":
                original_filter = ""
            # 否则使用旧的单语字幕滤镜作为回退
            translation_filter = ""
            # 如果原文滤镜为空，则使用旧的字幕滤镜
            if not original_filter:
                original_filter = build_dialogue_filter(dialogue_text, subtitle_cfg)
        
        if original_filter:
            filters.append(original_filter)
        if translation_filter:
            filters.append(translation_filter)
    
    # 添加关键词滤镜
    if drawtext:
        filters.append(drawtext)
    
    logo_drawtext = build_logo_filter(subtitle_cfg)
    logo_image_path = resolve_logo_image_path(subtitle_cfg)

    # 格式化时间参数，避免浮点数表示误差
    start_str = format(start, '.6f').rstrip('0').rstrip('.')
    end_str = format(end, '.6f').rstrip('0').rstrip('.')
    cmd = [
        "-y",
        "-ss",
        start_str,
        "-to",
        end_str,
        "-i",
        input_path,
    ]

    if logo_image_path:
        cmd += ["-i", logo_image_path]
        logo_scale = float(subtitle_cfg.get("logo_scale", 0))
        logo_width = int(subtitle_cfg.get("logo_width", 180))
        logo_max_width = int(subtitle_cfg.get("logo_max_width", 220))
        # 格式化logo_scale，避免浮点数表示误差和末尾的.0导致解析问题
        if logo_scale.is_integer():
            logo_scale_str = str(int(logo_scale))
        else:
            # 使用固定小数点格式，去除多余的尾随零
            logo_scale_str = format(logo_scale, '.6f').rstrip('0').rstrip('.')
        if logo_scale > 0:
            logo_scale_expr = f"'min(iw*{logo_scale_str},{logo_max_width})':-1"
        else:
            logo_scale_expr = f"{logo_width}:-1"
        logo_position = subtitle_cfg.get("logo_position", "top_left")

        logo_margin = int(subtitle_cfg.get("logo_margin", subtitle_cfg.get("margin", 20)))
        overlay_pos = resolve_overlay_position(logo_position, logo_margin)
        
        # 处理logo动画
        logo_animation = subtitle_cfg.get("logo_animation", "none")
        duration = end - start
        # 格式化持续时间，避免浮点数表示误差和末尾的.0导致解析问题
        if duration.is_integer():
            duration_str = str(int(duration))
        else:
            # 使用固定小数点格式，去除多余的尾随零
            duration_str = format(duration, '.6f').rstrip('0').rstrip('.')
        
        # 初始化filter_complex变量
        filter_complex = None
        
        if logo_animation == "slide_right" and duration > 0:
            # 从静态位置提取y表达式
            if ":" in overlay_pos:
                y_expr = overlay_pos.split(":", 1)[1]
            else:
                y_expr = "0"
            # 构建动态x表达式：从左侧外部移动到右侧外部
            # x = -w + t*(W + w)/duration
            overlay_expr = f"x='-w + t*(W + w)/{duration_str}':y={y_expr}"
            
            # 过滤有效的滤镜元素（必须是字符串且非空）
            valid_filters = [f.strip() for f in filters if isinstance(f, str) and f.strip()]
            
            if valid_filters:
                filter_complex = (
                    f"[0:v]{','.join(valid_filters)}[base];"
                    f"[1:v]scale={logo_scale_expr}[logo];"
                    f"[base][logo]overlay={overlay_expr}[v]"
                )
            else:
                filter_complex = (
                    f"[1:v]scale={logo_scale_expr}[logo];"
                    f"[0:v][logo]overlay={overlay_expr}[v]"
                )
                
        elif logo_animation == "slide_left" and duration > 0:
            # 从右侧外部移动到左侧外部
            if ":" in overlay_pos:
                y_expr = overlay_pos.split(":", 1)[1]
            else:
                y_expr = "0"
            overlay_expr = f"x='W - t*(W + w)/{duration_str}':y={y_expr}"
            
            # 过滤有效的滤镜元素（必须是字符串且非空）
            valid_filters = [f.strip() for f in filters if isinstance(f, str) and f.strip()]
            
            if valid_filters:
                filter_complex = (
                    f"[0:v]{','.join(valid_filters)}[base];"
                    f"[1:v]scale={logo_scale_expr}[logo];"
                    f"[base][logo]overlay={overlay_expr}[v]"
                )
            else:
                filter_complex = (
                    f"[1:v]scale={logo_scale_expr}[logo];"
                    f"[0:v][logo]overlay={overlay_expr}[v]"
                )
                
        elif logo_animation == "bounce_right" and duration > 0:
            # 双Logo模式：静态Logo + 动态往复Logo
            # 获取动画速度参数（默认为2.0）
            animation_speed = float(subtitle_cfg.get("logo_animation_speed", 2.0))
            if animation_speed.is_integer():
                animation_speed_str = str(int(animation_speed))
            else:
                # 使用固定小数点格式，去除多余的尾随零
                animation_speed_str = format(animation_speed, '.6f').rstrip('0').rstrip('.')
            
            # 解析静态位置
            static_x_expr, static_y_expr = parse_overlay_position(overlay_pos)
            
            # 静态Logo缩放表达式（原始大小）
            static_scale_expr = logo_scale_expr
            
            # 动态Logo缩放表达式（缩小50%）
            # 计算缩小50%后的缩放参数
            if logo_scale > 0:
                dynamic_scale = logo_scale * 0.5
                if dynamic_scale.is_integer():
                    dynamic_scale_str = str(int(dynamic_scale))
                else:
                    # 使用固定小数点格式，去除多余的尾随零
                    dynamic_scale_str = format(dynamic_scale, '.6f').rstrip('0').rstrip('.')
                dynamic_max_width = logo_max_width // 2 if logo_max_width > 0 else 0
                dynamic_scale_expr = f"'min(iw*{dynamic_scale_str},{dynamic_max_width})':-1"
            else:
                dynamic_width = logo_width // 2 if logo_width > 0 else 0
                dynamic_scale_expr = f"{dynamic_width}:-1"
            
            # 构建滤镜图
            # 过滤有效的滤镜元素（必须是字符串且非空）
            valid_filters = [f.strip() for f in filters if isinstance(f, str) and f.strip()]
            
            if valid_filters:
                filter_complex = (
                    f"[0:v]{','.join(valid_filters)}[base];"
                    f"[1:v]scale={static_scale_expr}[static_logo];"
                    f"[1:v]scale={dynamic_scale_expr}[dynamic_logo];"
f"[base][static_logo]overlay={overlay_pos}[base_with_static];"
f"[base_with_static][dynamic_logo]overlay="
f"x='{static_x_expr}+2*w + abs(mod(t*{animation_speed_str}*(W+w)/{duration_str}, 2*(W-{static_x_expr}-3*w)) - (W-{static_x_expr}-3*w))':"
f"y={static_y_expr}[v]"
                )
            else:
                filter_complex = (
                    f"[1:v]scale={static_scale_expr}[static_logo];"
                    f"[1:v]scale={dynamic_scale_expr}[dynamic_logo];"
f"[0:v][static_logo]overlay={overlay_pos}[base_with_static];"
f"[base_with_static][dynamic_logo]overlay="
f"x='{static_x_expr}+2*w + abs(mod(t*{animation_speed_str}*(W+w)/{duration_str}, 2*(W-{static_x_expr}-3*w)) - (W-{static_x_expr}-3*w))':"
f"y={static_y_expr}[v]"
                )
                
        else:
            # 无动画或未知动画类型，使用静态位置
            overlay_expr = overlay_pos
            
            # 过滤有效的滤镜元素（必须是字符串且非空）
            valid_filters = [f.strip() for f in filters if isinstance(f, str) and f.strip()]
            
            if valid_filters:
                filter_complex = (
                    f"[0:v]{','.join(valid_filters)}[base];"
                    f"[1:v]scale={logo_scale_expr}[logo];"
                    f"[base][logo]overlay={overlay_expr}[v]"
                )
            else:
                filter_complex = (
                    f"[1:v]scale={logo_scale_expr}[logo];"
                    f"[0:v][logo]overlay={overlay_expr}[v]"
                )

        # 如果构建了filter_complex，添加到命令
        if filter_complex:
            cmd += ["-filter_complex", filter_complex, "-map", "[v]", "-map", "0:a?"]
    else:
        if logo_drawtext:
            filters.append(logo_drawtext)
        if filters:
            # 过滤掉非字符串和空字符串的滤镜
            valid_filters = []
            for f in filters:
                if isinstance(f, str) and f.strip():
                    valid_filters.append(f.strip())
                else:
                    logger.warning(f"无效的滤镜元素被跳过: {repr(f)} (类型: {type(f).__name__})")
            
            if valid_filters:
                logger.debug(f"有效的滤镜数量: {len(valid_filters)}")
                logger.debug(f"滤镜列表: {valid_filters}")
                cmd += ["-vf", ",".join(valid_filters)]
            else:
                logger.debug("没有有效的滤镜，跳过 -vf 参数")

    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "aac", "-b:a", "192k", output_path]

    logger.debug(f"FFmpeg command: {cmd}")
    run_ffmpeg(cmd)


def build_timed_original_filter(segment_text: str, start_time: float, end_time: float, subtitle_cfg: Dict[str, Any]) -> str:
    """
    构建带时间控制的原文字幕滤镜
    start_time和end_time是相对于场景开始的时间（秒）
    """
    if not segment_text:
        return ""
    
    # 检查是否显示对话字幕
    if not subtitle_cfg.get("show_dialogue", True):
        return ""
    
    # 根据显示模式决定是否显示原文
    display_mode = subtitle_cfg.get("dialogue_display_mode", "both")
    if display_mode not in ["both", "original_only"]:
        return ""
    
    # 文本换行处理
    max_chars = subtitle_cfg.get("dialogue_max_chars_per_line", 18)
    max_lines = subtitle_cfg.get("original_max_lines", subtitle_cfg.get("dialogue_max_lines", 1))
    text_raw = wrap_dialogue_text(segment_text, max_chars, max_lines)
    if not text_raw:
        return ""
    
    text = escape_drawtext_keep_newlines(text_raw)
    
    # 样式配置
    font_color = subtitle_cfg.get("dialogue_font_color", subtitle_cfg.get("font_color", "white"))
    font_size = subtitle_cfg.get("dialogue_font_size", subtitle_cfg.get("font_size", 24))
    font_weight = subtitle_cfg.get("dialogue_font_weight", subtitle_cfg.get("font_weight", "normal"))
    box_color = subtitle_cfg.get("dialogue_box_color", subtitle_cfg.get("box_color", "black"))
    box_opacity = subtitle_cfg.get("dialogue_box_opacity", subtitle_cfg.get("box_opacity", 0.45))
    line_spacing = subtitle_cfg.get("dialogue_line_spacing", subtitle_cfg.get("line_spacing", 6))
    font_path = resolve_japanese_font_path(subtitle_cfg)  # 使用日文字体
    
# 获取位置
    original_pos, _ = resolve_bilingual_position(subtitle_cfg)

    # 构建enable表达式，格式化时间参数避免浮点数表示误差
    start_time_str = format(start_time, '.6f').rstrip('0').rstrip('.')
    end_time_str = format(end_time, '.6f').rstrip('0').rstrip('.')
    enable_expr = f"enable='between(t,{start_time_str},{end_time_str})'"
    
    parts = [
        "drawtext=",
    ]
    
    if font_path:
        parts.append(f"fontfile='{escape_drawtext(font_path)}':")
    
    parts.append(
        f"text='{text}':fontcolor={font_color}:fontsize={font_size}:"
        f"box=1:boxcolor={box_color}@{box_opacity}:boxborderw=10:"
        f"line_spacing={line_spacing}:{original_pos}:{enable_expr}"
    )
    
    return "".join(parts)


def build_timed_translation_filter(segment_text: str, start_time: float, end_time: float, subtitle_cfg: Dict[str, Any]) -> str:
    """
    构建带时间控制的译文字幕滤镜
    start_time和end_time是相对于场景开始的时间（秒）
    """
    if not segment_text:
        return ""
    
    # 检查是否显示对话字幕
    if not subtitle_cfg.get("show_dialogue", True):
        return ""
    
    # 根据显示模式决定是否显示译文
    display_mode = subtitle_cfg.get("dialogue_display_mode", "both")
    if display_mode not in ["both", "translation_only"]:
        return ""
    
    # 文本换行处理
    max_chars = subtitle_cfg.get("dialogue_max_chars_per_line", 18)
    max_lines = subtitle_cfg.get("translation_max_lines", subtitle_cfg.get("dialogue_max_lines", 1))
    text_raw = wrap_dialogue_text(segment_text, max_chars, max_lines)
    if not text_raw:
        return ""
    
    text = escape_drawtext_keep_newlines(text_raw)
    
    # 样式配置
    font_color = subtitle_cfg.get("dialogue_font_color", subtitle_cfg.get("font_color", "white"))
    font_size = subtitle_cfg.get("dialogue_font_size", subtitle_cfg.get("font_size", 24))
    font_weight = subtitle_cfg.get("dialogue_font_weight", subtitle_cfg.get("font_weight", "normal"))
    box_color = subtitle_cfg.get("dialogue_box_color", subtitle_cfg.get("box_color", "black"))
    box_opacity = subtitle_cfg.get("dialogue_box_opacity", subtitle_cfg.get("box_opacity", 0.45))
    line_spacing = subtitle_cfg.get("dialogue_line_spacing", subtitle_cfg.get("line_spacing", 6))
    font_path = resolve_chinese_font_path(subtitle_cfg)  # 使用中文字体
    
# 获取位置
    _, translation_pos = resolve_bilingual_position(subtitle_cfg)

    # 构建enable表达式，格式化时间参数避免浮点数表示误差
    start_time_str = format(start_time, '.6f').rstrip('0').rstrip('.')
    end_time_str = format(end_time, '.6f').rstrip('0').rstrip('.')
    enable_expr = f"enable='between(t,{start_time_str},{end_time_str})'"
    
    parts = [
        "drawtext=",
    ]
    
    if font_path:
        parts.append(f"fontfile='{escape_drawtext(font_path)}':")
    
    parts.append(
        f"text='{text}':fontcolor={font_color}:fontsize={font_size}:"
        f"box=1:boxcolor={box_color}@{box_opacity}:boxborderw=10:"
        f"line_spacing={line_spacing}:{translation_pos}:{enable_expr}"
    )
    
    return "".join(parts)



