import logging
import re
from collections import Counter
from typing import List, Optional
from modules.japanese_analyzer import extract_keywords as extract_japanese_keywords

logger = logging.getLogger(__name__)

# 英语停用词列表（基础）
ENGLISH_STOPWORDS = {
    "i", "me", "my", "myself", "we", "our", "ours", "ourselves", "you", "your", "yours",
    "yourself", "yourselves", "he", "him", "his", "himself", "she", "her", "hers",
    "herself", "it", "its", "itself", "they", "them", "their", "theirs", "themselves",
    "what", "which", "who", "whom", "this", "that", "these", "those", "am", "is", "are",
    "was", "were", "be", "been", "being", "have", "has", "had", "having", "do", "does",
    "did", "doing", "a", "an", "the", "and", "but", "if", "or", "because", "as", "until",
    "while", "of", "at", "by", "for", "with", "about", "against", "between", "into",
    "through", "during", "before", "after", "above", "below", "to", "from", "up", "down",
    "in", "out", "on", "off", "over", "under", "again", "further", "then", "once", "here",
    "there", "when", "where", "why", "how", "all", "any", "both", "each", "few", "more",
    "most", "other", "some", "such", "no", "nor", "not", "only", "own", "same", "so",
    "than", "too", "very", "s", "t", "can", "will", "just", "don", "should", "now"
}

def load_stopwords(path: str) -> set:
    """加载停用词文件"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return {line.strip().lower() for line in f if line.strip()}
    except FileNotFoundError:
        return set()

def extract_english_keywords_basic(
    text: str,
    max_keywords: int,
    parts_of_speech: List[str],
    min_frequency: int,
    stopwords_path: str,
) -> List[str]:
    """
    基础英语关键词提取（不使用nltk）
    通过简单规则提取名词和动词
    """
    if not text:
        return []
    
    # 加载停用词
    stopwords = ENGLISH_STOPWORDS.copy()
    file_stopwords = load_stopwords(stopwords_path)
    stopwords.update(file_stopwords)
    
    # 简单分词（按非字母字符分割）
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    
    # 过滤停用词
    filtered_words = [w for w in words if w not in stopwords]
    
    # 统计频率
    counts = Counter(filtered_words)
    filtered = [word for word, cnt in counts.items() if cnt >= min_frequency]
    filtered.sort(key=lambda w: counts[w], reverse=True)
    
    return filtered[:max_keywords]

def extract_english_keywords_nltk(
    text: str,
    max_keywords: int,
    parts_of_speech: List[str],
    min_frequency: int,
    stopwords_path: str,
) -> List[str]:
    """
    使用nltk进行英语关键词提取（如果可用）
    """
    try:
        import nltk
        from nltk.tokenize import word_tokenize
        from nltk.tag import pos_tag
        from nltk.corpus import stopwords as nltk_stopwords
        
        # 确保nltk数据已下载
        try:
            nltk.data.find('tokenizers/punkt')
        except LookupError:
            nltk.download('punkt', quiet=True)
        try:
            nltk.data.find('taggers/averaged_perceptron_tagger')
        except LookupError:
            nltk.download('averaged_perceptron_tagger', quiet=True)
        try:
            nltk.data.find('corpora/stopwords')
        except LookupError:
            nltk.download('stopwords', quiet=True)
        
        if not text:
            return []
        
        # 加载停用词
        stopwords = set(nltk_stopwords.words('english'))
        file_stopwords = load_stopwords(stopwords_path)
        stopwords.update(file_stopwords)
        
        # 分词和词性标注
        tokens = word_tokenize(text.lower())
        tagged = pos_tag(tokens)
        
        # 映射词性标签到通用类别
        pos_mapping = {
            'NN': 'noun', 'NNS': 'noun', 'NNP': 'noun', 'NNPS': 'noun',
            'VB': 'verb', 'VBD': 'verb', 'VBG': 'verb', 'VBN': 'verb', 
            'VBP': 'verb', 'VBZ': 'verb',
            'JJ': 'adjective', 'JJR': 'adjective', 'JJS': 'adjective',
            'RB': 'adverb', 'RBR': 'adverb', 'RBS': 'adverb'
        }
        
        keywords = []
        for word, tag in tagged:
            # 只保留字母单词，长度至少3
            if not re.match(r'^[a-zA-Z]{3,}$', word):
                continue
            
            if word in stopwords:
                continue
            
            pos_category = pos_mapping.get(tag[:2])
            if pos_category in parts_of_speech or not parts_of_speech:
                keywords.append(word)
        
        # 统计频率
        counts = Counter(keywords)
        filtered = [word for word, cnt in counts.items() if cnt >= min_frequency]
        filtered.sort(key=lambda w: counts[w], reverse=True)
        
        return filtered[:max_keywords]
        
    except ImportError:
        logger.warning("nltk not available, falling back to basic keyword extraction")
        return extract_english_keywords_basic(
            text, max_keywords, parts_of_speech, min_frequency, stopwords_path
        )
    except Exception as e:
        logger.error(f"nltk keyword extraction failed: {e}")
        return extract_english_keywords_basic(
            text, max_keywords, parts_of_speech, min_frequency, stopwords_path
        )

def extract_keywords(
    text: str,
    language: str,
    max_keywords: int,
    parts_of_speech: List[str],
    min_frequency: int,
    stopwords_path: str,
) -> List[str]:
    """
    根据语言提取关键词的多语言接口
    
    Args:
        text: 输入文本
        language: 语言代码 ('ja', 'en', 'zh', etc.)
        max_keywords: 最大关键词数量
        parts_of_speech: 词性列表（语言相关）
        min_frequency: 最小出现频率
        stopwords_path: 停用词文件路径
    
    Returns:
        关键词列表
    """
    if not text or not text.strip():
        return []
    
    # 日语：使用现有分析器
    if language == "ja":
        # 日语分析器期望特定的词性格式（如“動詞”）
        return extract_japanese_keywords(
            text=text,
            max_keywords=max_keywords,
            parts_of_speech=parts_of_speech,
            min_frequency=min_frequency,
            stopwords_path=stopwords_path,
        )
    
    # 英语：使用nltk或基础提取器
    elif language == "en":
        # 将日语词性映射到英语词性
        pos_mapping = {
            "動詞": "verb",
            "名詞": "noun",
            "形容詞": "adjective",
            "副詞": "adverb",
        }
        
        english_pos = []
        for pos in parts_of_speech:
            english_pos.append(pos_mapping.get(pos, pos))
        
        # 如果没有有效的词性，使用默认值
        if not english_pos:
            english_pos = ["noun", "verb"]
        
        # 尝试使用nltk，失败则回退到基础提取
        try:
            return extract_english_keywords_nltk(
                text=text,
                max_keywords=max_keywords,
                parts_of_speech=english_pos,
                min_frequency=min_frequency,
                stopwords_path=stopwords_path,
            )
        except Exception as e:
            logger.warning(f"English keyword extraction failed: {e}")
            return extract_english_keywords_basic(
                text=text,
                max_keywords=max_keywords,
                parts_of_speech=english_pos,
                min_frequency=min_frequency,
                stopwords_path=stopwords_path,
            )
    
    # 其他语言：暂时返回空列表
    else:
        logger.debug(f"Keyword extraction not supported for language: {language}")
        return []

def filter_keywords_by_kanji_priority(keywords: List[str], max_display: int = 10) -> List[str]:
    """
    根据汉字优先级筛选关键词
    优先选择包含汉字的词，按汉字数量排序，最多返回max_display个
    
    Args:
        keywords: 原始关键词列表
        max_display: 最大显示数量（默认10）
        
    Returns:
        筛选后的关键词列表
    """
    if not keywords:
        return []
    
    # 统计每个关键词的汉字数量
    kanji_counts = []
    for keyword in keywords:
        # 汉字 Unicode 范围：\u4e00-\u9fff (基本汉字)，\u3400-\u4dbf (扩展A)
        kanji_count = sum(1 for char in keyword if '\u4e00' <= char <= '\u9fff' or '\u3400' <= char <= '\u4dbf')
        kanji_counts.append((keyword, kanji_count))
    
    # 按汉字数量降序排序（汉字多的优先）
    kanji_counts.sort(key=lambda x: x[1], reverse=True)
    
    # 提取排序后的关键词
    sorted_keywords = [kw for kw, _ in kanji_counts]
    
    # 限制显示数量
    return sorted_keywords[:max_display]