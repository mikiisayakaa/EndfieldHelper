from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

import pyautogui
from PIL import Image, ImageGrab

from ocr import compare_similarity, crop_right_fraction, load_template_bgr, match_template, pil_to_bgr

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
    roi_image, offset_x, offset_y = crop_right_fraction(screenshot, 0.2)
    roi_bgr = pil_to_bgr(roi_image)

    template_bgr = load_template_bgr(QINGBAO_TEMPLATE)
    invalid_bgr = load_template_bgr(QINGBAO_INVALID_TEMPLATE)
    if template_bgr is None or invalid_bgr is None:
        return None

    max_val, max_loc = match_template(roi_bgr, template_bgr)
    if max_val < match_threshold:
        return None

    t_height, t_width = template_bgr.shape[:2]
    x, y = max_loc
    if y + t_height > roi_bgr.shape[0] or x + t_width > roi_bgr.shape[1]:
        return None

    candidate = roi_bgr[y : y + t_height, x : x + t_width]
    valid_score = compare_similarity(candidate, template_bgr)
    invalid_score = compare_similarity(candidate, invalid_bgr)

    if valid_score < invalid_score:
        return None

    center_x = offset_x + x + t_width // 2
    center_y = offset_y + y + t_height // 2

    return {
        "center_x": center_x,
        "center_y": center_y,
        "score": max_val,
        "valid_score": valid_score,
        "invalid_score": invalid_score,
    }


def _run_config(config_path: Path | str, stop_check: Callable[[], bool] | None) -> None:
    from automation import load_steps, run_step, run_timeline

    resolved_path = _resolve_config_path(config_path)
    if not resolved_path.exists():
        raise FileNotFoundError(f"Config not found: {resolved_path}")

    data = load_steps(resolved_path)
    if isinstance(data, dict) and "timeline" in data:
        run_timeline(
            data,
            stop_check=stop_check,
            event_callback=None,
            wait_for_events=True,
        )
        return

    for step in data:
        if stop_check and stop_check():
            from automation import StopExecution

            raise StopExecution("Stopped")
        run_step(step, stop_check=stop_check)


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
