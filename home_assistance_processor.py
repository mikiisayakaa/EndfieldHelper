from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import pyautogui
from PIL import Image

from ocr import recognize_template


TEMPLATE_DIR = Path("templates")
HOME_ASSISTANCE_TEMPLATE = TEMPLATE_DIR / "home_use_assistance.png"


def process_home_assistance(
    confidence_threshold: float = 90.0,
    click_interval: float = 0.5,
    stop_check: Callable[[], bool] | None = None,
) -> dict:
    """
    Process home assistance recognition and click operation.
    
    1. Take full screen screenshot
    2. Use SIFT to recognize home_use_assistance template
    3. If confidence > threshold, click twice with interval
    
    Args:
        confidence_threshold: Minimum confidence percentage (0-100) to trigger click
        click_interval: Time interval between two clicks in seconds
        stop_check: Optional callback to check if operation should stop
    
    Returns:
        Dict with:
        {
            "success": bool,
            "confidence": float,
            "center_x": int or None,
            "center_y": int or None,
            "message": str
        }
    """
    # Take full screenshot
    screenshot = pyautogui.screenshot()
    
    # Recognize template using SIFT (via recognize_template which uses find_template_sift)
    result = recognize_template(screenshot, HOME_ASSISTANCE_TEMPLATE.name)
    
    if result is None:
        return {
            "success": False,
            "confidence": 0.0,
            "center_x": None,
            "center_y": None,
            "message": "Template not found"
        }
    
    confidence = result.get("confidence", 0.0)
    
    if confidence < confidence_threshold:
        return {
            "success": False,
            "confidence": confidence,
            "center_x": result.get("x"),
            "center_y": result.get("y"),
            "message": f"Confidence too low: {confidence:.1f}%"
        }
    
    # Check if we should stop before clicking
    if stop_check and stop_check():
        return {
            "success": False,
            "confidence": confidence,
            "center_x": result["x"],
            "center_y": result["y"],
            "message": "Operation stopped by user"
        }
    
    # Confidence meets threshold, perform double click
    x = result["x"]
    y = result["y"]
    
    pyautogui.click(x, y)
    time.sleep(click_interval)
    pyautogui.click(x, y)
    
    return {
        "success": True,
        "confidence": confidence,
        "center_x": x,
        "center_y": y,
        "message": f"Clicked at ({x}, {y}) with confidence {confidence:.1f}%"
    }
