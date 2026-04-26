import argparse
import hashlib
import json
import os
from typing import Dict, Any, List, Tuple, Optional

import yaml
from tqdm import tqdm

from modules.scene_detector import detect_scenes
from modules.speech_recognizer import (
    load_whisper_model,
    transcribe_video,
    slice_segments_by_scene,
)
from modules.keyword_extractor import extract_keywords as extract_keywords_multilingual
from modules.translator import translate_segments
from modules.video_processor import export_scene_with_keywords
from utils.logger import get_logger
from utils.video_utils import ensure_ffmpeg, normalize_input_video



logger = get_logger()


def normalize_language_code(language: str) -> str:
    if not language:
        return ""
    return language.lower().split("-")[0]


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


def load_json(path: str) -> Optional[Any]:
    """加载JSON文件，如果不存在或出错返回None"""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"加载缓存文件失败 {path}: {e}")
        return None


def _get_file_hash(path: str, block_size: int = 65536) -> str:
    """计算文件的 MD5 hash（前 1MB + 最后 1MB），用于缓存校验。"""
    hasher = hashlib.md5()
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        if size <= block_size * 2:
            hasher.update(f.read())
        else:
            hasher.update(f.read(block_size))
            f.seek(max(0, size - block_size))
            hasher.update(f.read(block_size))
    return hasher.hexdigest()


def get_cache_paths(output_dir: str, input_path: str) -> Dict[str, str]:
    """获取所有缓存文件路径"""
    input_name = os.path.splitext(os.path.basename(input_path))[0]
    cache_dir = os.path.join(output_dir, ".cache")
    return {
        "cache_dir": cache_dir,
        "scenes": os.path.join(cache_dir, f"{input_name}_scenes.json"),
        "transcript": os.path.join(cache_dir, f"{input_name}_transcript.json"),
        "progress": os.path.join(cache_dir, f"{input_name}_progress.json"),
    }


def _is_cache_valid(data: Optional[Dict[str, Any]], input_path: str) -> bool:
    """校验缓存是否与当前输入文件匹配。"""
    if not data or "input_hash" not in data:
        return False
    try:
        current_hash = _get_file_hash(input_path)
        return data["input_hash"] == current_hash
    except OSError:
        return False


def load_scenes_cache(cache_path: str, input_path: str) -> Optional[List[Tuple[float, float]]]:
    """从缓存加载场景检测结果（带输入文件校验）。"""
    data = load_json(cache_path)
    if not _is_cache_valid(data, input_path):
        logger.info("场景缓存与当前输入文件不匹配，将重新检测。")
        return None
    if data and "scenes" in data:
        scenes = [(float(s[0]), float(s[1])) for s in data["scenes"]]
        logger.info(f"从缓存加载场景检测结果: {len(scenes)} 个场景")
        return scenes
    return None


def save_scenes_cache(cache_path: str, scenes: List[Tuple[float, float]], input_path: str) -> None:
    """保存场景检测结果到缓存（附加输入文件 hash 用于校验）。"""
    try:
        cache_data = {
            "scenes": scenes,
            "version": 2,
            "input_hash": _get_file_hash(input_path),
        }
        save_json(cache_path, cache_data)
        logger.info(f"场景检测结果已缓存: {cache_path}")
    except Exception as e:
        logger.warning(f"保存场景缓存失败: {e}")


def load_transcript_cache(cache_path: str, input_path: str) -> Optional[Tuple[List[Dict[str, Any]], str, Optional[float]]]:
    """从缓存加载语音识别结果（带输入文件校验）。"""
    data = load_json(cache_path)
    if not _is_cache_valid(data, input_path):
        logger.info("语音识别缓存与当前输入文件不匹配，将重新识别。")
        return None
    if data and "segments" in data:
        segments = data["segments"]
        language = data.get("language", "ja")
        probability = data.get("language_probability")
        logger.info(f"从缓存加载语音识别结果: {len(segments)} 个分段")
        return segments, language, probability
    return None


def save_transcript_cache(
    cache_path: str,
    segments: List[Dict[str, Any]],
    language: str,
    probability: Optional[float],
    input_path: str,
) -> None:
    """保存语音识别结果到缓存（附加输入文件 hash 用于校验）。"""
    try:
        cache_data = {
            "segments": segments,
            "language": language,
            "language_probability": probability,
            "version": 2,
            "input_hash": _get_file_hash(input_path),
        }
        save_json(cache_path, cache_data)
        logger.info(f"语音识别结果已缓存: {cache_path}")
    except Exception as e:
        logger.warning(f"保存语音识别缓存失败: {e}")


def get_completed_scenes(progress_path: str) -> set:
    """获取已完成的场景索引集合"""
    data = load_json(progress_path)
    if data and "completed" in data:
        return set(data["completed"])
    return set()


def update_progress(progress_path: str, scene_idx: int) -> None:
    """更新进度文件，标记场景为已完成"""
    data = load_json(progress_path) or {"completed": [], "version": 1}
    if "completed" not in data:
        data["completed"] = []
    if scene_idx not in data["completed"]:
        data["completed"].append(scene_idx)
        data["completed"].sort()
    try:
        save_json(progress_path, data)
    except Exception as e:
        logger.warning(f"更新进度文件失败: {e}")


def run_pipeline(cfg: Dict[str, Any], input_path: str, resume: bool = False) -> None:
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

    # 获取缓存路径
    cache_paths = get_cache_paths(output_dir, input_path)
    ensure_dirs(cache_paths["cache_dir"])

    input_path = normalize_input_video(
        input_path=input_path,
        temp_dir=temp_dir,
        enabled=video_cfg.get("transcode_input", True),
        target_format=video_cfg.get("transcode_format", "mp4"),
    )

    # ==================== 步骤1: 场景检测（支持缓存）====================
    scenes = None
    if resume:
        scenes = load_scenes_cache(cache_paths["scenes"], input_path)

    if scenes is None:
        scenes = detect_scenes(
            input_path=input_path,
            method=scene_cfg["method"],
            threshold=scene_cfg["threshold"],
            min_scene_length=scene_cfg["min_scene_length"],
            merge_min_length=scene_cfg.get("merge_min_length", 0.0),
        )
        save_scenes_cache(cache_paths["scenes"], scenes, input_path)

    if not scenes:
        logger.warning("未检测到场景，尝试调低阈值或增加视频时长。")
        return

    logger.info(f"检测到 {len(scenes)} 个场景，开始处理……")

    # ==================== 步骤2: 语音识别（支持缓存）====================
    full_segments = None
    full_detected_language = sr_cfg.get("language", "ja")
    full_language_prob = None

    if resume:
        cached = load_transcript_cache(cache_paths["transcript"], input_path)
        if cached:
            full_segments, full_detected_language, full_language_prob = cached

    if full_segments is None:
        model = load_whisper_model(
            model_name=sr_cfg.get("model", "large-v3"),
            device=sr_cfg.get("device", "auto"),
            compute_type=sr_cfg.get("compute_type", "int8_float16"),
        )
        configured_language = sr_cfg.get("language", "ja")
        full_transcript_result = transcribe_video(
            input_path=input_path,
            model=model,
            language=configured_language,
            beam_size=sr_cfg.get("beam_size", 5),
            best_of=sr_cfg.get("best_of", 5),
            patience=sr_cfg.get("patience", 1.0),
            temperature=sr_cfg.get("temperature", 0.0),
            condition_on_previous_text=sr_cfg.get("condition_on_previous_text", True),
            initial_prompt=sr_cfg.get("initial_prompt", ""),
            vad_filter=sr_cfg.get("vad_filter", True),
            vad_min_silence_duration_ms=sr_cfg.get("vad_min_silence_duration_ms", 500),
            progress_log_interval_sec=sr_cfg.get("progress_log_interval_sec", 15),
        )
        full_segments = full_transcript_result.get("segments", [])
        full_detected_language = full_transcript_result.get("detected_language", configured_language)
        full_language_prob = full_transcript_result.get("language_probability")
        save_transcript_cache(
            cache_paths["transcript"],
            full_segments,
            full_detected_language,
            full_language_prob,
            input_path,
        )

    logger.info(
        f"全片识别完成，分段数量: {len(full_segments)}，检测语言: "
        f"{full_detected_language} (概率: {full_language_prob})"
    )
    
    # ==================== 步骤3: 获取已完成场景（支持续传）====================
    completed_scenes = get_completed_scenes(cache_paths["progress"]) if resume else set()
    if completed_scenes:
        logger.info(f"检测到已完成的场景: {len(completed_scenes)}/{len(scenes)}")

    for idx, (start, end) in enumerate(tqdm(scenes, desc="Processing scenes"), start=1):
        scene_id = f"scene_{idx:04d}"
        
        # ==================== 步骤4: 检查是否已导出（支持续传）====================
        output_scene_path = os.path.join(scenes_dir, f"{scene_id}.{video_cfg['output_format']}")
        if resume and idx in completed_scenes and os.path.exists(output_scene_path):
            logger.info(f"场景 {scene_id}: 已存在，跳过")
            continue
        
        # 同时检查中间文件是否存在（转录和关键词）
        transcript_path = os.path.join(transcripts_dir, f"{scene_id}.txt")
        keywords_path = os.path.join(keywords_dir, f"{scene_id}.json")
        
        # 如果中间文件存在但视频不存在，复用中间结果
        reuse_existing = resume and os.path.exists(transcript_path) and os.path.exists(keywords_path)
        
        if not reuse_existing:
            original_text, original_segments = slice_segments_by_scene(
                segments=full_segments,
                start=start,
                end=end,
            )
            detected_language = full_detected_language
            language_prob = full_language_prob

            logger.debug(
                f"场景 {scene_id}: 检测到语言 {detected_language} (概率: {language_prob})"
            )
            logger.debug(f"场景 {scene_id}: 原文分段数量: {len(original_segments)}")

            # 翻译处理
            display_text = original_text  # 默认显示原文（向后兼容）
            translation_used = False
            translated_text = None  # 译文，可能为空
            translated_segments = None  # 译文分段信息，默认为None
            
            if trans_cfg.get("enabled", False) and original_text.strip():
                target_lang = trans_cfg.get("target_language", "zh-CN")
                show_original = trans_cfg.get("show_original", True)

                source_code = normalize_language_code(detected_language or "")
                target_code = normalize_language_code(target_lang)

                # 如果检测到的语言不是目标语言，则进行翻译
                if source_code and source_code != target_code:
                    translated_segments, detected_src = translate_segments(
                        segments=original_segments,
                        target_lang=target_lang,
                        src_lang=detected_language,
                        max_retries=3,
                        batch_size=trans_cfg.get("batch_size", 16),
                        use_cache=trans_cfg.get("use_cache", True),
                    )

                    translated_text = " ".join(
                        [(seg.get("text") or "").strip() for seg in translated_segments]
                    ).strip()

                    if translated_text and translated_text != original_text:
                        translation_used = True
                        # 保持向后兼容：如果show_original为True，则display_text包含原文和译文
                        if show_original:
                            display_text = f"{original_text}\n{translated_text}"
                        else:
                            display_text = translated_text

                        logger.debug(
                            f"分段翻译完成: {detected_src or detected_language} -> {target_lang}, "
                            f"segments={len(translated_segments)}"
                        )
                    else:
                        logger.warning(f"翻译失败，使用原文")
                        translated_text = None
                        translated_segments = None
                else:
                    logger.debug(f"检测语言与目标语言相同，跳过翻译")
                    translated_text = None
                    translated_segments = None
            
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
            
            # 保存文本文件（仅原始文本，便于阅读）
            save_text(transcript_path, original_text)
            # 保存JSON文件包含完整信息
            save_json(keywords_path, {**transcript_info, "keywords": keywords})
        else:
            # 复用已有中间结果
            logger.info(f"场景 {scene_id}: 复用已有转录和关键词结果")
            keywords_data = load_json(keywords_path) or {}
            original_text = keywords_data.get("original_text", "")
            translated_text = keywords_data.get("translated_text")
            translated_segments = None  # 简化处理，不复用分段
            keywords = keywords_data.get("keywords", [])
            original_segments = slice_segments_by_scene(
                segments=full_segments,
                start=start,
                end=end,
            )[1]  # 重新切分获取分段

        export_scene_with_keywords(
            input_path=input_path,
            start=start,
            end=end,
            output_path=output_scene_path,
            keywords=keywords,
            subtitle_cfg=sub_cfg,
            dialogue_text=original_text,
            translated_text=translated_text,
            segments=original_segments,
            translated_segments=translated_segments,
        )
        
        # 更新进度
        update_progress(cache_paths["progress"], idx)


    logger.info("处理完成。")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="日文电影场景切分与关键词提取")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    parser.add_argument("--input", default="", help="输入视频路径")
    parser.add_argument("--resume", action="store_true", help="启用断点续传模式，跳过已完成的场景")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)

    input_path = args.input or cfg["video"]["input_path"]
    if not input_path:
        logger.error("请通过 --input 或 config.yaml 提供输入视频路径。")
        return

    run_pipeline(cfg, input_path, resume=args.resume)


if __name__ == "__main__":
    main()
