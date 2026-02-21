from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
import pyautogui
from PIL import Image, ImageGrab

from ocr import compare_similarity, crop_right_fraction, load_template_bgr, pil_to_bgr, match_template

TEMPLATE_DIR = Path("templates")
QINGBAO_TEMPLATE = TEMPLATE_DIR / "qingbao.png"
QINGBAO_INVALID_TEMPLATE = TEMPLATE_DIR / "qingbao_invalid.png"


def _resolve_config_path(config_path: Path | str) -> Path:
    path = Path(config_path)
    if path.exists():
        return path
    return Path(__file__).parent / path


def find_qingbao_target(
    screenshot: Image.Image,
    match_threshold: float = 0.7,
) -> dict | None:
    """
    Find qingbao target in screenshot using template matching.
    
    Args:
        screenshot: Full screen PIL Image
        match_threshold: Minimum confidence threshold for template matching
    
    Returns:
        Dict with center_x, center_y, and scores, or None if not found
    """
    # Use ROI (right 20% of screen) for efficiency
    roi_image, offset_x, offset_y = crop_right_fraction(screenshot, 0.2)
    roi_bgr = pil_to_bgr(roi_image)

    invalid_bgr = load_template_bgr(QINGBAO_INVALID_TEMPLATE)
    if invalid_bgr is None:
        return None

    valid_bgr = load_template_bgr(QINGBAO_TEMPLATE)
    if valid_bgr is None:
        return None

    confidence, (x, y) = match_template(roi_bgr, valid_bgr)

    if confidence < match_threshold:
        return None

    h, w = valid_bgr.shape[:2]
    result = {
        "center_x": x + w // 2,
        "center_y": y + h // 2,
        "confidence": confidence,
        "bbox": [x, y, x + w, y + h],
    }
    print(f"Template matching: confidence={confidence:.2%}")

    # Extract candidate region and compare with valid/invalid templates
    x1, y1, x2, y2 = result["bbox"]
    candidate = roi_bgr[y1:y2, x1:x2]
    if candidate.size == 0:
        return None

    # Load valid template for comparison
    valid_bgr = load_template_bgr(QINGBAO_TEMPLATE)
    if valid_bgr is None:
        return None
    
    valid_score = compare_similarity(candidate, valid_bgr)
    invalid_score = compare_similarity(candidate, invalid_bgr)

    if valid_score < invalid_score:
        return None

    # Calculate center in full screen coordinates
    center_x = offset_x + result["center_x"]
    center_y = offset_y + result["center_y"]

    confidence = result["confidence"]

    return {
        "center_x": center_x,
        "center_y": center_y,
        "score": float(confidence),
        "valid_score": valid_score,
        "invalid_score": invalid_score,
    }


def _run_config(config_path: Path | str, stop_check: Callable[[], bool] | None) -> None:
    from automation import load_steps, run_timeline

    resolved_path = _resolve_config_path(config_path)
    if not resolved_path.exists():
        raise FileNotFoundError(f"Config not found: {resolved_path}")

    data = load_steps(resolved_path)
    run_timeline(
        data,
        stop_check=stop_check,
        event_callback=None,
        wait_for_events=True,
    )


def run_qingbao_loop(
    config_found: Path | str,
    config_not_found: Path | str,
    max_clicks: int = 5,
    max_recognitions: int = 20,
    match_threshold: float = 0.7,
    stop_check: Callable[[], bool] | None = None,
) -> dict:
    logger = logging.getLogger("app")
    click_count = 0
    recognition_count = 0

    while recognition_count < max_recognitions:
        if stop_check and stop_check():
            from automation import StopExecution

            raise StopExecution("Stopped")

        screenshot = ImageGrab.grab()
        target = find_qingbao_target(screenshot, match_threshold=match_threshold)
        recognition_count += 1

        if target:
            logger.info(
                "qingbao: target found (match=%.3f, valid=%.3f, invalid=%.3f)",
                target["score"],
                target["valid_score"],
                target["invalid_score"],
            )
            pyautogui.click(target["center_x"], target["center_y"])
            click_count += 1
            _run_config(config_found, stop_check)

            if click_count >= max_clicks:
                break
        else:
            logger.info("qingbao: no valid target found")
            _run_config(config_not_found, stop_check)

    return {
        "click_count": click_count,
        "recognition_count": recognition_count,
        "stopped": click_count >= max_clicks or recognition_count >= max_recognitions,
    }
