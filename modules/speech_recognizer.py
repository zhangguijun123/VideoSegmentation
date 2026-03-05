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
) -> str:
    audio_path = extract_audio_segment(
        input_path=input_path,
        start=start,
        end=end,
        output_dir=temp_dir,
        name=f"{scene_id}.wav",
    )

    result = model.transcribe(audio_path, language=language, fp16=False)
    text = (result.get("text") or "").strip()
    return text
