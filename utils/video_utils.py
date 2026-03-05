import os
import shutil
import subprocess
from typing import List


def ensure_ffmpeg() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("未检测到 ffmpeg/ffprobe，请先安装并配置到 PATH。")


def run_ffmpeg(args: List[str]) -> None:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error"] + args
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())


def normalize_input_video(
    input_path: str,
    temp_dir: str,
    enabled: bool = True,
    target_format: str = "mp4",
) -> str:
    if not enabled:
        return input_path

    ext = os.path.splitext(input_path)[1].lower().lstrip(".")
    if ext == target_format.lower():
        return input_path

    os.makedirs(temp_dir, exist_ok=True)
    output_path = os.path.join(temp_dir, f"normalized_input.{target_format}")
    if os.path.exists(output_path):
        return output_path

    cmd = [
        "-y",
        "-i",
        input_path,
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        output_path,
    ]
    run_ffmpeg(cmd)
    return output_path


def extract_audio_segment(input_path: str, start: float, end: float, output_dir: str, name: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, name)
    cmd = [
        "-y",
        "-ss",
        f"{start}",
        "-to",
        f"{end}",
        "-i",
        input_path,
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-sample_fmt",
        "s16",
        output_path,
    ]
    run_ffmpeg(cmd)
    return output_path

