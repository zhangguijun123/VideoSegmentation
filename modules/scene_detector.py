from typing import List, Tuple

from scenedetect import open_video, SceneManager
from scenedetect.detectors import ContentDetector, ThresholdDetector, AdaptiveDetector


def detect_scenes(
    input_path: str,
    method: str = "content",
    threshold: float = 27.0,
    min_scene_length: float = 2.0,
    merge_min_length: float = 0.0,
) -> List[Tuple[float, float]]:
    video = open_video(input_path)
    scene_manager = SceneManager()

    detector = None
    if method == "threshold":
        detector = ThresholdDetector(threshold=threshold, min_scene_len=int(min_scene_length * video.frame_rate))
    elif method == "adaptive":
        detector = AdaptiveDetector(adaptive_threshold=threshold, min_scene_len=int(min_scene_length * video.frame_rate))
    else:
        detector = ContentDetector(threshold=threshold, min_scene_len=int(min_scene_length * video.frame_rate))

    scene_manager.add_detector(detector)
    scene_manager.detect_scenes(video)
    scene_list = scene_manager.get_scene_list()

    results: List[Tuple[float, float]] = []
    for start_time, end_time in scene_list:
        start_sec = start_time.get_seconds()
        end_sec = end_time.get_seconds()
        if end_sec - start_sec >= min_scene_length:
            results.append((start_sec, end_sec))

    if not results or merge_min_length <= 0:
        return results

    merged: List[Tuple[float, float]] = []
    current_start, current_end = results[0]
    for start_sec, end_sec in results[1:]:
        if current_end - current_start < merge_min_length:
            current_end = end_sec
        else:
            merged.append((current_start, current_end))
            current_start, current_end = start_sec, end_sec

    merged.append((current_start, current_end))
    return merged

