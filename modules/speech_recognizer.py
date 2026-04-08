from typing import Any

import whisper

from utils.video_utils import extract_audio_segment


def load_whisper_model(model_name: str = "base") -> Any:
    return whisper.load_model(model_name)


def transcribe_scene(
    input_path: str,
    start: float,
    end: float,
    model: Any,
    language: str,
    temp_dir: str,
    scene_id: str,
) -> dict:
    """
    转录视频场景的音频，支持自动语言检测。
    返回字典，包含以下字段：
    - text: 转录文本
    - detected_language: 检测到的语言代码（如 'ja', 'en'）
    - language_probability: 语言检测置信度（如果有）
    """
    audio_path = extract_audio_segment(
        input_path=input_path,
        start=start,
        end=end,
        output_dir=temp_dir,
        name=f"{scene_id}.wav",
    )

    # 如果 language 为 "auto" 或 None，则让 Whisper 自动检测
    if language == "auto" or language is None:
        result = model.transcribe(audio_path, fp16=False)
    else:
        result = model.transcribe(audio_path, language=language, fp16=False)

    text = (result.get("text") or "").strip()
    detected_language = result.get("language", language if language != "auto" else None)
    # 语言概率可能存在于 segments 中，取平均值
    language_probability = None
    segments = result.get("segments", [])
    if segments and "language_probability" in segments[0]:
        probs = [seg.get("language_probability", 0) for seg in segments if seg.get("language_probability")]
        if probs:
            language_probability = sum(probs) / len(probs)
    
    return {
        "text": text,
        "detected_language": detected_language,
        "language_probability": language_probability,
    }
