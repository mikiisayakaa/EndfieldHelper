"""
Plants harvest loop processor - OCR-based plant harvesting automation.

Workflow:
1. Detect empty plants using SIFT
2. Click on empty plant if found
3. Enter loop:
   a. Check for harvestable plants (plants_confirm)
   b. If found, click and continue loop
   c. If not found, check for extractable cores (plants_extract)
   d. If found, click, execute extract config, and continue loop
   e. If neither found, exit loop
"""

import logging
import time
from pathlib import Path
from typing import Callable

import pyautogui
from PIL import ImageGrab

from automation import load_steps, run_timeline, StopExecution
from ocr import recognize_template

logger = logging.getLogger("app")


def run_plants_harvest_loop(
    stop_check: Callable[[], bool] | None = None,
    max_iterations: int = 100,
) -> dict:
    """
    Run the plants harvest loop using SIFT-based template recognition.
    
    Args:
        stop_check: Optional callback to check if execution should stop
        max_iterations: Maximum number of loop iterations to prevent infinite loops
    
    Returns:
        Dict with loop statistics:
        {
            "success": bool,
            "message": str,
            "total_iterations": int,
            "confirm_clicks": int,
            "extract_clicks": int,
            "error": str (if any)
        }
    """
    
    stats = {
        "success": False,
        "message": "",
        "total_iterations": 0,
        "confirm_clicks": 0,
        "extract_clicks": 0,
        "error": None,
    }
    
    try:
        # Step 1: Check for empty plants
        logger.info("Plants harvest loop: Checking for empty plants...")
        screen = ImageGrab.grab()
        
        result_empty = recognize_template(screen, "plants/plants_empty.png", min_matches=4)
        
        if result_empty is None:
            logger.info("Plants harvest loop: No empty plants found, exit")
            stats["message"] = "No empty plants found"
            stats["success"] = True
            return stats
        
        # Click on empty plant
        click_x = result_empty["x"]
        click_y = result_empty["y"]
        logger.info(f"Plants harvest loop: Clicking empty plant at ({click_x}, {click_y})")
        pyautogui.click(click_x, click_y)
        time.sleep(0.5)
        
        # Step 2: Enter harvest loop
        iteration = 0
        while iteration < max_iterations:
            if stop_check and stop_check():
                raise StopExecution("Stopped by user")
            
            iteration += 1
            logger.info(f"Plants harvest loop: Iteration {iteration}")
            
            # Take a fresh screenshot for each iteration
            screen = ImageGrab.grab()
            
            # Check for harvestable plants (plants_confirm)
            result_confirm = recognize_template(screen, "plants/plants_confirm.png", min_matches=4)
            
            if result_confirm is not None:
                # Harvestable plant found, click it
                click_x = result_confirm["x"]
                click_y = result_confirm["y"]
                logger.info(
                    f"Plants harvest loop [#{iteration}]: "
                    f"Clicked confirm at ({click_x}, {click_y}), "
                    f"confidence={result_confirm['confidence']:.1f}%"
                )
                pyautogui.click(click_x, click_y)
                stats["confirm_clicks"] += 1
                time.sleep(0.3)
                continue
            
            # plants_confirm not found, check for extractable cores (plants_extract)
            result_extract = recognize_template(screen, "plants/plants_extract.png", min_matches=4)
            
            if result_extract is not None:
                # Extractable core found, click it
                click_x = result_extract["x"]
                click_y = result_extract["y"]
                logger.info(
                    f"Plants harvest loop [#{iteration}]: "
                    f"Clicked extract at ({click_x}, {click_y}), "
                    f"confidence={result_extract['confidence']:.1f}%"
                )
                pyautogui.click(click_x, click_y)
                stats["extract_clicks"] += 1
                time.sleep(0.3)
                
                # Execute extract core config
                logger.info(f"Plants harvest loop [#{iteration}]: Executing extract core config...")
                config_path = Path("configs/帝江号收菜/提取基核.json")
                
                if not config_path.exists():
                    raise FileNotFoundError(f"Config not found: {config_path}")
                
                steps = load_steps(config_path)
                
                # Execute config timeline
                if isinstance(steps, dict) and "timeline" in steps:
                    run_timeline(
                        steps,
                        stop_check=stop_check,
                        event_callback=None,
                        wait_for_events=True,
                    )
                else:
                    # Legacy format - list of steps
                    run_timeline(
                        steps,
                        stop_check=stop_check,
                        event_callback=None,
                        wait_for_events=True,
                    )
                
                logger.info(f"Plants harvest loop [#{iteration}]: Extract core config completed")
                time.sleep(0.5)
                continue
            
            # Both confirm and extract not found, exit loop
            logger.info(f"Plants harvest loop: No confirm or extract templates found, exiting loop")
            break
        
        stats["total_iterations"] = iteration
        stats["message"] = (
            f"Loop completed: {stats['confirm_clicks']} confirm clicks, "
            f"{stats['extract_clicks']} extract clicks, "
            f"{iteration} total iterations"
        )
        stats["success"] = True
        
        logger.info(f"Plants harvest loop: {stats['message']}")
        
        return stats
    
    except StopExecution as e:
        stats["error"] = str(e)
        stats["message"] = f"Stopped by user: {e}"
        logger.warning(f"Plants harvest loop: {stats['message']}")
        return stats
    
    except FileNotFoundError as e:
        stats["error"] = str(e)
        stats["message"] = f"File not found: {e}"
        logger.error(f"Plants harvest loop: {stats['message']}")
        return stats
    
    except Exception as e:
        stats["error"] = str(e)
        stats["message"] = f"Error: {e}"
        logger.error(f"Plants harvest loop: {stats['message']}", exc_info=True)
        return stats
