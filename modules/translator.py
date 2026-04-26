import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from googletrans import Translator as GoogleTranslator

logger = logging.getLogger(__name__)

_translator_instance = None
_translation_cache = {}


def get_translator() -> GoogleTranslator:
    """获取Google翻译器单例实例"""
    global _translator_instance
    if _translator_instance is None:
        _translator_instance = GoogleTranslator()
    return _translator_instance


def reset_translator() -> None:
    """重置翻译器实例，避免连接异常在重试中持续复用。"""
    global _translator_instance
    _translator_instance = None


def clear_translation_cache() -> None:
    """清空翻译缓存。"""
    _translation_cache.clear()


def translate_text(
    text: str,
    target_lang: str = "zh-CN",
    src_lang: Optional[str] = None,
    max_retries: int = 3,
) -> Tuple[str, Optional[str]]:
    """
    翻译文本
    
    Args:
        text: 要翻译的文本
        target_lang: 目标语言代码，默认为中文（zh-CN）
        src_lang: 源语言代码，如果为None则自动检测
        max_retries: 最大重试次数
    
    Returns:
        元组 (翻译后的文本, 检测到的源语言代码)
        如果翻译失败，返回原文本和None
    """
    if not text or not text.strip():
        return text, src_lang
    
    for attempt in range(max_retries):
        try:
            translator = get_translator()
            if src_lang:
                # 指定源语言
                translation = translator.translate(
                    text, 
                    dest=target_lang, 
                    src=src_lang
                )
            else:
                # 自动检测源语言
                translation = translator.translate(text, dest=target_lang)

            if translation is None:
                raise ValueError("翻译服务返回空响应")

            translated_text = getattr(translation, "text", None)
            detected_src_lang = getattr(translation, "src", None)
            if translated_text is None:
                raise ValueError("翻译结果缺少 text 字段")
            
            logger.debug(
                f"翻译成功: {src_lang or 'auto'} -> {target_lang}, "
                f"检测到源语言: {detected_src_lang}"
            )
            
            return translated_text, detected_src_lang
            
        except Exception as e:
            logger.warning(f"翻译尝试 {attempt + 1}/{max_retries} 失败: {e}")
            reset_translator()
            if attempt < max_retries - 1:
                time.sleep(0.5 * (attempt + 1))
            if attempt == max_retries - 1:
                logger.error(f"翻译失败，返回原文: {text[:50]}...")
                return text, src_lang
    
    return text, src_lang


def translate_batch(
    texts: list,
    target_lang: str = "zh-CN",
    src_lang: Optional[str] = None,
    max_retries: int = 3,
) -> Tuple[list, Optional[str]]:
    """
    批量翻译文本列表
    
    Args:
        texts: 文本列表
        target_lang: 目标语言代码
        src_lang: 源语言代码
        max_retries: 最大重试次数
    
    Returns:
        元组 (翻译后的文本列表, 检测到的源语言代码)
        如果所有文本都翻译失败，返回原文本列表和None
    """
    if not texts:
        return [], src_lang
    
    # 简单实现：逐一翻译
    results = []
    detected_lang = None
    
    for text in texts:
        translated, detected = translate_text(
            text, target_lang, src_lang, max_retries
        )
        results.append(translated)
        if detected and detected_lang is None:
            detected_lang = detected
    
    return results, detected_lang


def translate_segments(
    segments: List[Dict[str, Any]],
    target_lang: str = "zh-CN",
    src_lang: Optional[str] = None,
    max_retries: int = 3,
    batch_size: int = 16,
    use_cache: bool = True,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    翻译分段文本，并保持与原始分段时间戳对齐。

    Args:
        segments: 原文分段，元素包含 start/end/text
        target_lang: 目标语言
        src_lang: 源语言（可选）
        max_retries: 单条翻译最大重试次数
        batch_size: 批处理大小
        use_cache: 是否启用句子级缓存

    Returns:
        (translated_segments, detected_src_lang)
    """
    if not segments:
        return [], src_lang

    translated_segments: List[Dict[str, Any]] = []
    detected_lang: Optional[str] = None
    normalized_batch_size = max(1, int(batch_size or 1))

    segment_items: List[Dict[str, Any]] = []
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        segment_items.append(
            {
                "start": seg.get("start"),
                "end": seg.get("end"),
                "text": text,
            }
        )

    unique_texts: List[str] = []
    seen_texts = set()
    for item in segment_items:
        text = item["text"]
        if text not in seen_texts:
            seen_texts.add(text)
            unique_texts.append(text)

    to_translate: List[str] = []
    for text in unique_texts:
        cache_key = (src_lang or "auto", target_lang, text)
        if use_cache and cache_key in _translation_cache:
            continue
        to_translate.append(text)

    for i in range(0, len(to_translate), normalized_batch_size):
        batch_texts = to_translate[i : i + normalized_batch_size]
        if not batch_texts:
            continue

        translated_batch: Optional[List[str]] = None
        batch_detected_lang: Optional[str] = None

        for attempt in range(max_retries):
            try:
                translator = get_translator()
                if src_lang:
                    raw_results = translator.translate(
                        batch_texts,
                        dest=target_lang,
                        src=src_lang,
                    )
                else:
                    raw_results = translator.translate(batch_texts, dest=target_lang)

                if raw_results is None:
                    raise ValueError("批量翻译服务返回空响应")

                if not isinstance(raw_results, list):
                    raw_results = [raw_results]

                if len(raw_results) != len(batch_texts):
                    raise ValueError(
                        f"批量翻译返回数量异常: expected={len(batch_texts)}, "
                        f"actual={len(raw_results)}"
                    )

                translated_batch = []
                for item in raw_results:
                    if item is None:
                        raise ValueError("批量翻译包含空条目")
                    item_text = getattr(item, "text", None)
                    if item_text is None:
                        raise ValueError("批量翻译条目缺少 text 字段")
                    translated_batch.append(item_text or "")
                    item_src = getattr(item, "src", None)
                    if item_src and batch_detected_lang is None:
                        batch_detected_lang = item_src
                break
            except Exception as e:
                logger.warning(
                    f"分段批量翻译尝试 {attempt + 1}/{max_retries} 失败: {e}"
                )
                reset_translator()
                if attempt < max_retries - 1:
                    time.sleep(0.5 * (attempt + 1))

        if batch_detected_lang and detected_lang is None:
            detected_lang = batch_detected_lang

        if translated_batch and len(translated_batch) == len(batch_texts):
            for src_text, dst_text in zip(batch_texts, translated_batch):
                cache_key = (src_lang or "auto", target_lang, src_text)
                _translation_cache[cache_key] = dst_text if dst_text else src_text
        else:
            # 批量失败则回退到单条翻译，保证可用性
            for text in batch_texts:
                translated_text, detected = translate_text(
                    text=text,
                    target_lang=target_lang,
                    src_lang=src_lang,
                    max_retries=max_retries,
                )
                if detected and detected_lang is None:
                    detected_lang = detected
                cache_key = (src_lang or "auto", target_lang, text)
                _translation_cache[cache_key] = translated_text if translated_text else text

    for item in segment_items:
        text = item["text"]
        cache_key = (src_lang or "auto", target_lang, text)
        translated_text = _translation_cache.get(cache_key, text) if use_cache else text
        if not use_cache:
            translated_text, detected = translate_text(
                text=text,
                target_lang=target_lang,
                src_lang=src_lang,
                max_retries=max_retries,
            )
            if detected and detected_lang is None:
                detected_lang = detected
            translated_text = translated_text if translated_text else text

        translated_segments.append(
            {
                "start": item["start"],
                "end": item["end"],
                "text": translated_text,
            }
        )

    return translated_segments, detected_lang