import logging
from typing import Optional, Tuple
from googletrans import Translator as GoogleTranslator

logger = logging.getLogger(__name__)

_translator_instance = None


def get_translator() -> GoogleTranslator:
    """获取Google翻译器单例实例"""
    global _translator_instance
    if _translator_instance is None:
        _translator_instance = GoogleTranslator()
    return _translator_instance


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
    
    translator = get_translator()
    
    for attempt in range(max_retries):
        try:
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
            
            translated_text = translation.text
            detected_src_lang = translation.src
            
            logger.debug(
                f"翻译成功: {src_lang or 'auto'} -> {target_lang}, "
                f"检测到源语言: {detected_src_lang}"
            )
            
            return translated_text, detected_src_lang
            
        except Exception as e:
            logger.warning(f"翻译尝试 {attempt + 1}/{max_retries} 失败: {e}")
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