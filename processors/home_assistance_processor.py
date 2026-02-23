from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import pyautogui

from ocr import recognize_template


TEMPLATE_DIR = Path("templates")
HOME_ASSISTANCE_TEMPLATE = TEMPLATE_DIR / "home_use_assistance.png"


def process_home_assistance(
    confidence_threshold: float = 90.0,
    click_interval: float = 0.5,
    max_iterations: int = 3,
    stop_check: Callable[[], bool] | None = None,
) -> dict:
    """
    Process home assistance recognition and click operation in a loop.
    
    Loop logic (max 3 iterations):
    1. Take full screen screenshot and recognize template
    2. If recognized with confidence > threshold:
       - Perform double click with interval
       - Sleep 0.5s
       - Continue to next iteration
    3. If not recognized or confidence too low:
       - Break out of loop
    
    Args:
        confidence_threshold: Minimum confidence percentage (0-100) to trigger click
        click_interval: Time interval between two clicks in seconds
        max_iterations: Maximum number of loop iterations (default: 3)
        stop_check: Optional callback to check if operation should stop
    
    Returns:
        Dict with:
        {
            "success": bool,
            "total_iterations": int,
            "total_clicks": int,
            "message": str
        }
    """
    total_clicks = 0
    iteration = 0
    
    for iteration in range(1, max_iterations + 1):
        # Check if we should stop
        if stop_check and stop_check():
            return {
                "success": False,
                "total_iterations": iteration - 1,
                "total_clicks": total_clicks,
                "message": "Operation stopped by user"
            }
        
        print(f"Home assistance loop: Iteration {iteration}/{max_iterations}")
        
        # Take full screenshot
        screenshot = pyautogui.screenshot()
        
        # Recognize template using SIFT
        result = recognize_template(screenshot, HOME_ASSISTANCE_TEMPLATE.name)
        
        if result is None:
            print(f"Home assistance loop [#{iteration}]: Template not found, exiting loop")
            break
        
        confidence = result.get("confidence", 0.0)
        
        if confidence < confidence_threshold:
            print(f"Home assistance loop [#{iteration}]: Confidence too low: {confidence:.1f}%, exiting loop")
            break
        
        # Confidence meets threshold, perform double click
        x = result["x"]
        y = result["y"]
        
        print(f"Home assistance loop [#{iteration}]: Clicking at ({x}, {y}), confidence={confidence:.1f}%")
        pyautogui.click(x, y)
        time.sleep(click_interval)
        pyautogui.click(x, y)
        total_clicks += 1
        
        # Sleep at the end of each iteration
        time.sleep(0.5)
    
    if total_clicks > 0:
        return {
            "success": True,
            "total_iterations": iteration,
            "total_clicks": total_clicks,
            "message": f"Loop completed: {total_clicks} assistance(s) clicked in {iteration} iteration(s)"
        }
    else:
        return {
            "success": False,
            "total_iterations": iteration,
            "total_clicks": 0,
            "message": f"No assistance found in {iteration} iteration(s)"
        }
