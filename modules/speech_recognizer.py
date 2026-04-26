import subprocess
import time
from typing import Any, Dict, List, Tuple

from faster_whisper import WhisperModel

from utils.logger import get_logger

logger = get_logger()


def load_whisper_model(
    model_name: str = "large-v3",
    device: str = "auto",
    compute_type: str = "int8_float16",
) -> Any:
    # Try user-configured compute_type first, then gracefully fallback for compatibility.
    fallback_types = [compute_type]
    if compute_type != "int8":
        fallback_types.append("int8")
    if compute_type != "float32":
        fallback_types.append("float32")

    last_error: Exception = RuntimeError("Unknown model initialization error.")
    for current_compute_type in fallback_types:
        try:
            if current_compute_type != compute_type:
                logger.warning(
                    f"compute_type '{compute_type}' 不可用，尝试回退到 '{current_compute_type}'"
                )
            return WhisperModel(
                model_name,
                device=device,
                compute_type=current_compute_type,
            )
        except ValueError as e:
            last_error = e
            continue

    raise last_error


def transcribe_video(
    input_path: str,
    model: Any,
    language: str = "ja",
    beam_size: int = 5,
    best_of: int = 5,
    patience: float = 1.0,
    temperature: float = 0.0,
    condition_on_previous_text: bool = True,
    initial_prompt: str = "",
    vad_filter: bool = True,
    vad_min_silence_duration_ms: int = 500,
    progress_log_interval_sec: int = 15,
) -> Dict[str, Any]:
    """
    对整段视频进行一次性转录，返回全局时间轴上的分段结果。
    """
    language_arg = None if language == "auto" else language
    transcribe_kwargs: Dict[str, Any] = {
        "language": language_arg,
        "beam_size": max(1, int(beam_size or 1)),
        "best_of": max(1, int(best_of or 1)),
        "patience": max(0.1, float(patience or 1.0)),
        "temperature": float(temperature if temperature is not None else 0.0),
        "condition_on_previous_text": bool(condition_on_previous_text),
        "vad_filter": vad_filter,
        "vad_parameters": {"min_silence_duration_ms": max(100, int(vad_min_silence_duration_ms or 500))},
    }
    if initial_prompt and initial_prompt.strip():
        transcribe_kwargs["initial_prompt"] = initial_prompt.strip()

    segments_iter, info = model.transcribe(input_path, **transcribe_kwargs)

    raw_segments: List[Dict[str, Any]] = []
    start_wall_time = time.time()
    next_log_time = start_wall_time + max(1, int(progress_log_interval_sec or 1))
    last_processed_end_sec = 0.0

    total_duration_sec = _get_media_duration_seconds(input_path)
    for seg in segments_iter:
        seg_text = (seg.text or "").strip()
        if not seg_text:
            continue
        last_processed_end_sec = float(seg.end)
        raw_segments.append(
            {
                "start": float(seg.start),
                "end": float(seg.end),
                "text": seg_text,
            }
        )

        now = time.time()
        if now >= next_log_time:
            processed_min = last_processed_end_sec / 60.0
            if total_duration_sec > 0:
                total_min = total_duration_sec / 60.0
                progress = min(100.0, (last_processed_end_sec / total_duration_sec) * 100.0)
                logger.info(
                    f"识别进度: 已处理到 {processed_min:.1f} 分钟 / {total_min:.1f} 分钟 ({progress:.1f}%)"
                )
            else:
                logger.info(f"识别进度: 已处理到 {processed_min:.1f} 分钟")
            next_log_time = now + max(1, int(progress_log_interval_sec or 1))

    # 后处理：检测并修复 Whisper 幻觉循环（同一短文本在短时间内大量重复）
    segments = _deduplicate_hallucination(raw_segments)
    if len(segments) < len(raw_segments):
        logger.warning(
            f"检测到 Whisper 幻觉循环: 原始 {len(raw_segments)} 个分段 → 去重后 {len(segments)} 个分段"
        )

    texts = [seg["text"] for seg in segments]

    return {
        "text": " ".join(texts).strip(),
        "detected_language": getattr(info, "language", language),
        "language_probability": getattr(info, "language_probability", None),
        "segments": segments,
    }


def _deduplicate_hallucination(
    segments: List[Dict[str, Any]],
    max_repeat_count: int = 5,
    window_sec: float = 15.0,
) -> List[Dict[str, Any]]:
    """
    检测 Whisper 幻觉循环：同一短文本（≤10字）在短时间内重复出现超过阈值。
    将循环区域合并为一个分段，保留第一次出现。

    Args:
        segments: 原始分段列表
        max_repeat_count: 窗口内同一文本最大允许出现次数
        window_sec: 检测窗口大小（秒）
    """
    if not segments:
        return []

    # 第一轮：标记可疑的循环文本（短文本+高频重复）
    text_counts: Dict[str, int] = {}
    for seg in segments:
        text = seg["text"]
        if len(text) <= 10:  # 短文本更容易是幻觉
            text_counts[text] = text_counts.get(text, 0) + 1

    # 找出高频重复的候选文本（出现次数 > 阈值）
    hallucination_candidates = {t for t, c in text_counts.items() if c > max_repeat_count}

    if not hallucination_candidates:
        return segments  # 无幻觉迹象，直接返回

    result: List[Dict[str, Any]] = []
    i = 0
    while i < len(segments):
        seg = segments[i]
        text = seg["text"]

        if text not in hallucination_candidates:
            result.append(seg)
            i += 1
            continue

        # 收集该候选文本的连续/近连续段
        window_start = seg["start"]
        window_end = seg["end"]
        j = i + 1
        while j < len(segments):
            next_seg = segments[j]
            # 判断是否为同一文本的延续（间隔不超过 2 秒或总窗口不超过阈值）
            if next_seg["text"] == text and next_seg["start"] - window_end <= 2.0:
                window_end = max(window_end, next_seg["end"])
                j += 1
            # 或者仍在时间窗口内且是同一文本
            elif next_seg["text"] == text and next_seg["end"] - window_start <= window_sec:
                window_end = max(window_end, next_seg["end"])
                j += 1
            else:
                break

        # 合并为一个分段（保留原始文本，时间取整个范围）
        result.append({
            "start": seg["start"],
            "end": window_end,
            "text": text,
        })
        i = j

    return result


def _get_media_duration_seconds(input_path: str) -> float:
    """读取媒体时长（秒），失败时返回0。"""
    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            input_path,
        ]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            return 0.0
        return float((result.stdout or "").strip() or 0.0)
    except Exception:
        return 0.0


def slice_segments_by_scene(
    segments: List[Dict[str, Any]],
    start: float,
    end: float,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    按场景时间范围裁剪全局segments，返回该场景的文本与分段。
    仅保留与场景有时间交集的语音段。
    """
    scene_segments: List[Dict[str, Any]] = []
    scene_texts: List[str] = []

    for seg in segments:
        seg_start = float(seg.get("start", 0.0))
        seg_end = float(seg.get("end", 0.0))
        seg_text = (seg.get("text") or "").strip()
        if not seg_text:
            continue
        if seg_end <= start or seg_start >= end:
            continue

        scene_segments.append(
            {
                "start": max(seg_start, start),
                "end": min(seg_end, end),
                "text": seg_text,
            }
        )
        scene_texts.append(seg_text)

    return " ".join(scene_texts).strip(), scene_segments


