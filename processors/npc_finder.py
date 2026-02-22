from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import pyautogui
from PIL import ImageGrab

from ocr import recognize_compare_two_templates
from automation import StopExecution


TEMPLATES_DIR = Path("templates")
TALK_TEMPLATE = "gifts/talk.png"
CALL_TEMPLATE = "gifts/call.png"


def find_npc_by_walking(
    confidence_threshold: float = 0.5,
    min_matches: int = 10,
    max_steps: int = 9,
    stop_check: Callable[[], bool] | None = None,
) -> dict:
    """
    Find NPC by walking along a fixed path with recognition at each step.
    
    Algorithm:
    1. For each step (max 9):
       a. Take screenshot and recognize both talk and call templates
       b. If talk_confidence >= threshold AND talk_confidence > call_confidence → Exit (found NPC)
       c. Otherwise, execute the next step in the path and continue
    
    Path sequence: dddwwwaaa (3 right + 3 forward + 3 left)
    Each step: key_press → sleep 0.05s → key_release
    
    Args:
        confidence_threshold: Minimum confidence (0-1) for talk detection (default 0.5 = 50%)
        min_matches: Minimum SIFT matches required
        max_steps: Maximum steps to walk (default 9)
        stop_check: Optional callback to check if operation should stop
    
    Returns:
        Dict with:
        {
            "success": bool (True if NPC found),
            "steps_taken": int,
            "final_talk_confidence": float,
            "final_call_confidence": float,
            "message": str
        }
    """
    # Path sequence: dddwwwaaa
    path = ['d', 'd', 'd', 'w', 'w', 'w', 'a', 'a', 'a']
    
    stats = {
        "success": False,
        "steps_taken": 0,
        "final_talk_confidence": 0.0,
        "final_call_confidence": 0.0,
        "message": "",
    }
    
    try:
        for step_idx in range(max_steps):
            if stop_check and stop_check():
                raise StopExecution("Stopped by user")
            
            print(f"Find NPC: Step {step_idx + 1}/{max_steps}")
            
            # Take screenshot and recognize both templates
            screenshot = ImageGrab.grab()
            result = recognize_compare_two_templates(
                screenshot,
                TALK_TEMPLATE,
                CALL_TEMPLATE,
                min_matches=min_matches,
            )
            
            if result is None:
                print(f"Find NPC [Step {step_idx + 1}]: Recognition failed")
                talk_conf = 0.0
                call_conf = 0.0
            else:
                talk_conf = result["confidence1"]
                call_conf = result["confidence2"]
                print(f"Find NPC [Step {step_idx + 1}]: talk={talk_conf:.2%}, call={call_conf:.2%}")
            
            # Check if NPC found
            if talk_conf >= confidence_threshold and talk_conf > call_conf:
                print(f"Find NPC: NPC found! talk_confidence={talk_conf:.2%}")
                stats["success"] = True
                stats["steps_taken"] = step_idx
                stats["final_talk_confidence"] = talk_conf
                stats["final_call_confidence"] = call_conf
                stats["message"] = f"NPC found after {step_idx} step(s): talk={talk_conf:.2%} > call={call_conf:.2%}"
                return stats
            
            # If not found and not the last step, execute next step
            if step_idx < max_steps - 1:
                key = path[step_idx]
                print(f"Find NPC: Executing step {step_idx + 1}: '{key}'")
                
                # Press key with 0.05s delay before release
                pyautogui.keyDown(key)
                time.sleep(0.05)
                pyautogui.keyUp(key)
            
            stats["steps_taken"] = step_idx + 1
            stats["final_talk_confidence"] = talk_conf
            stats["final_call_confidence"] = call_conf
        
        # If we reach here, NPC was not found after all steps
        stats["success"] = False
        stats["message"] = f"NPC not found after {max_steps} step(s)"
        print(f"Find NPC: {stats['message']}")
        return stats
    
    except StopExecution as e:
        stats["message"] = f"Stopped by user: {e}"
        print(f"Find NPC: {stats['message']}")
        return stats
    
    except Exception as e:
        stats["message"] = f"Error: {e}"
        print(f"Find NPC: {stats['message']}")
        return stats
