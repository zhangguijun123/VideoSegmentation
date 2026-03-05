import os
from typing import List, Dict, Any

from utils.video_utils import run_ffmpeg


def escape_drawtext(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
    )


def escape_drawtext_keep_newlines(text: str) -> str:
    placeholder = "__NL__"
    text = text.replace("\n", placeholder)
    text = escape_drawtext(text)
    return text.replace(placeholder, "\\\\n")



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


def resolve_logo_image_path(subtitle_cfg: Dict[str, Any]) -> str:
    logo_image_path = subtitle_cfg.get("logo_image_path", "")
    if not logo_image_path:
        return ""

    if os.path.isabs(logo_image_path):
        return logo_image_path if os.path.exists(logo_image_path) else ""

    candidate = os.path.join(os.getcwd(), logo_image_path)
    return candidate if os.path.exists(candidate) else ""




def build_drawtext_filter(keywords: List[str], subtitle_cfg: Dict[str, Any]) -> str:
    if not subtitle_cfg.get("show_keywords", True):
        return ""

    if not keywords:
        return ""

    text_raw = "\n".join(keywords)
    text = escape_drawtext_keep_newlines(text_raw)



    font_color = subtitle_cfg.get("font_color", "white")
    font_size = subtitle_cfg.get("font_size", 36)
    box_color = subtitle_cfg.get("box_color", "black")
    box_opacity = subtitle_cfg.get("box_opacity", 0.45)
    line_spacing = subtitle_cfg.get("line_spacing", 6)
    font_path = resolve_font_path(subtitle_cfg)
    position_expr = resolve_position(subtitle_cfg)

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


def export_scene_with_keywords(
    input_path: str,
    start: float,
    end: float,
    output_path: str,
    keywords: List[str],
    subtitle_cfg: Dict[str, Any],
    dialogue_text: str,
) -> None:
    drawtext = build_drawtext_filter(keywords, subtitle_cfg)
    dialogue_drawtext = build_dialogue_filter(dialogue_text, subtitle_cfg)
    logo_drawtext = build_logo_filter(subtitle_cfg)
    logo_image_path = resolve_logo_image_path(subtitle_cfg)

    cmd = [
        "-y",
        "-ss",
        f"{start}",
        "-to",
        f"{end}",
        "-i",
        input_path,
    ]

    filters = []
    if drawtext:
        filters.append(drawtext)
    if dialogue_drawtext:
        filters.append(dialogue_drawtext)

    if logo_image_path:
        cmd += ["-i", logo_image_path]
        logo_scale = float(subtitle_cfg.get("logo_scale", 0))
        logo_width = int(subtitle_cfg.get("logo_width", 180))
        logo_max_width = int(subtitle_cfg.get("logo_max_width", 220))
        if logo_scale > 0:
            logo_scale_expr = f"'min(iw*{logo_scale},{logo_max_width})':-1"
        else:
            logo_scale_expr = f"{logo_width}:-1"
        logo_position = subtitle_cfg.get("logo_position", "top_left")

        logo_margin = int(subtitle_cfg.get("logo_margin", subtitle_cfg.get("margin", 20)))
        overlay_pos = resolve_overlay_position(logo_position, logo_margin)

        if filters:
            filter_complex = (
                f"[0:v]{','.join(filters)}[base];"
                f"[1:v]scale={logo_scale_expr}[logo];"
                f"[base][logo]overlay={overlay_pos}[v]"
            )
        else:
            filter_complex = (
                f"[1:v]scale={logo_scale_expr}[logo];"
                f"[0:v][logo]overlay={overlay_pos}[v]"
            )


        cmd += ["-filter_complex", filter_complex, "-map", "[v]", "-map", "0:a?"]
    else:
        if logo_drawtext:
            filters.append(logo_drawtext)
        if filters:
            cmd += ["-vf", ",".join(filters)]

    cmd += ["-c:v", "libx264", "-preset", "fast", "-c:a", "aac", output_path]

    run_ffmpeg(cmd)



