import argparse
import json
import os
from typing import Dict, Any, List, Tuple

import yaml
from tqdm import tqdm

from modules.scene_detector import detect_scenes
from modules.speech_recognizer import load_whisper_model, transcribe_scene
from modules.keyword_extractor import extract_keywords as extract_keywords_multilingual
from modules.translator import translate_text
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
    trans_cfg = cfg.get("translation", {"enabled": False, "target_language": "zh-CN", "show_original": True})

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

        # 确定识别语言：如果启用自动检测则传递"auto"，否则使用配置语言
        language = "auto" if sr_cfg.get("auto_detect", False) else sr_cfg["language"]
        
        # 转录场景，返回字典包含文本、检测语言和置信度
        transcript_result = transcribe_scene(
            input_path=input_path,
            start=start,
            end=end,
            model=model,
            language=language,
            temp_dir=temp_dir,
            scene_id=scene_id,
        )
        
        original_text = transcript_result["text"]
        detected_language = transcript_result["detected_language"]
        language_prob = transcript_result.get("language_probability")
        
        logger.debug(f"场景 {scene_id}: 检测到语言 {detected_language} (概率: {language_prob})")

        # 翻译处理
        display_text = original_text  # 默认显示原文（向后兼容）
        translation_used = False
        translated_text = None  # 译文，可能为空
        
        if trans_cfg.get("enabled", False) and original_text.strip():
            target_lang = trans_cfg.get("target_language", "zh-CN")
            show_original = trans_cfg.get("show_original", True)
            
            # 如果检测到的语言不是目标语言，则进行翻译
            if detected_language and detected_language != target_lang:
                translated_result, detected_src = translate_text(
                    original_text, 
                    target_lang=target_lang,
                    src_lang=detected_language,
                    max_retries=3
                )
                
                if translated_result and translated_result != original_text:
                    translation_used = True
                    translated_text = translated_result
                    # 保持向后兼容：如果show_original为True，则display_text包含原文和译文
                    if show_original:
                        display_text = f"{original_text}\n{translated_text}"
                    else:
                        display_text = translated_text
                    
                    logger.debug(f"翻译完成: {detected_language} -> {target_lang}")
                else:
                    logger.warning(f"翻译失败，使用原文")
                    translated_text = None
            else:
                logger.debug(f"检测语言与目标语言相同，跳过翻译")
                translated_text = None
        
        # 关键词提取：多语言支持
        if detected_language in ["ja", "en"]:
            keywords = extract_keywords_multilingual(
                text=original_text,
                language=detected_language,
                max_keywords=kw_cfg["max_keywords_per_scene"],
                parts_of_speech=kw_cfg["parts_of_speech"],
                min_frequency=kw_cfg["min_frequency"],
                stopwords_path=kw_cfg["stopwords_path"],
            )
        else:
            # 其他语言，暂时返回空列表
            keywords = []
            logger.debug(f"语言 {detected_language} 不支持关键词提取，跳过")
        
        # 保存原始转录文本和检测到的语言信息
        transcript_info = {
            "scene": scene_id,
            "start": start,
            "end": end,
            "original_text": original_text,
            "detected_language": detected_language,
            "language_probability": language_prob,
            "translation_used": translation_used,
            "translated_text": translated_text,
            "display_text": display_text,
        }
        
        transcript_path = os.path.join(transcripts_dir, f"{scene_id}.txt")
        keywords_path = os.path.join(keywords_dir, f"{scene_id}.json")
        
        # 保存文本文件（仅原始文本，便于阅读）
        save_text(transcript_path, original_text)
        # 保存JSON文件包含完整信息
        save_json(keywords_path, {**transcript_info, "keywords": keywords})

        export_scene_with_keywords(
            input_path=input_path,
            start=start,
            end=end,
            output_path=os.path.join(scenes_dir, f"{scene_id}.{video_cfg['output_format']}"),
            keywords=keywords,
            subtitle_cfg=sub_cfg,
            dialogue_text=original_text,
            translated_text=translated_text,
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
