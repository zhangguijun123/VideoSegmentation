import argparse
import json
import os
from typing import Dict, Any, List, Tuple

import yaml
from tqdm import tqdm

from modules.scene_detector import detect_scenes
from modules.speech_recognizer import load_whisper_model, transcribe_scene
from modules.japanese_analyzer import extract_keywords
from modules.video_processor import export_scene_with_keywords
from utils.logger import get_logger
from utils.video_utils import ensure_ffmpeg, normalize_input_video



logger = get_logger()


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def ensure_dirs(*paths: str) -> None:
    for p in paths:
        os.makedirs(p, exist_ok=True)


def save_text(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(text or "")


def save_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def run_pipeline(cfg: Dict[str, Any], input_path: str) -> None:
    ensure_ffmpeg()

    video_cfg = cfg["video"]
    scene_cfg = cfg["scene_detection"]
    sr_cfg = cfg["speech_recognition"]
    kw_cfg = cfg["keywords"]
    sub_cfg = cfg["subtitle"]

    output_dir = video_cfg["output_dir"]
    temp_dir = video_cfg["temp_dir"]

    scenes_dir = os.path.join(output_dir, "scenes")
    transcripts_dir = os.path.join(output_dir, "transcripts")
    keywords_dir = os.path.join(output_dir, "keywords")

    ensure_dirs(output_dir, scenes_dir, transcripts_dir, keywords_dir, temp_dir)

    input_path = normalize_input_video(
        input_path=input_path,
        temp_dir=temp_dir,
        enabled=video_cfg.get("transcode_input", True),
        target_format=video_cfg.get("transcode_format", "mp4"),
    )

    scenes = detect_scenes(
        input_path=input_path,
        method=scene_cfg["method"],
        threshold=scene_cfg["threshold"],
        min_scene_length=scene_cfg["min_scene_length"],
        merge_min_length=scene_cfg.get("merge_min_length", 0.0),
    )



    if not scenes:
        logger.warning("未检测到场景，尝试调低阈值或增加视频时长。")
        return

    logger.info(f"检测到 {len(scenes)} 个场景，开始处理……")

    model = load_whisper_model(sr_cfg["model"])

    for idx, (start, end) in enumerate(tqdm(scenes, desc="Processing scenes"), start=1):
        scene_id = f"scene_{idx:04d}"

        transcript = transcribe_scene(
            input_path=input_path,
            start=start,
            end=end,
            model=model,
            language=sr_cfg["language"],
            temp_dir=temp_dir,
            scene_id=scene_id,
        )

        keywords = extract_keywords(
            text=transcript,
            max_keywords=kw_cfg["max_keywords_per_scene"],
            parts_of_speech=kw_cfg["parts_of_speech"],
            min_frequency=kw_cfg["min_frequency"],
            stopwords_path=kw_cfg["stopwords_path"],
        )

        transcript_path = os.path.join(transcripts_dir, f"{scene_id}.txt")
        keywords_path = os.path.join(keywords_dir, f"{scene_id}.json")
        save_text(transcript_path, transcript)
        save_json(keywords_path, {"scene": scene_id, "start": start, "end": end, "keywords": keywords})

        export_scene_with_keywords(
            input_path=input_path,
            start=start,
            end=end,
            output_path=os.path.join(scenes_dir, f"{scene_id}.{video_cfg['output_format']}"),
            keywords=keywords,
            subtitle_cfg=sub_cfg,
            dialogue_text=transcript,
        )


    logger.info("处理完成。")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="日文电影场景切分与关键词提取")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    parser.add_argument("--input", default="", help="输入视频路径")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)

    input_path = args.input or cfg["video"]["input_path"]
    if not input_path:
        logger.error("请通过 --input 或 config.yaml 提供输入视频路径。")
        return

    run_pipeline(cfg, input_path)


if __name__ == "__main__":
    main()
