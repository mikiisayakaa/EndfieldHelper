"""
Plants harvest loop processor - OCR-based plant harvesting automation.

Workflow (all within main loop):
1. Detect empty plants using SIFT
2. If not found, exit loop
3. If found, click on empty plant
4. Check for extractable cores (plants_extract)
   - If found, click and execute extract config
5. Check for harvestable plants (plants_confirm) - always required
   - If found, click and continue to next iteration
   - If not found, exit loop
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


def get_bottom_right_region(screen_image):
    """
    Get the bottom-right quarter of the screen (from 1/2, 1/2 to 1.0, 1.0).
    
    Returns:
        tuple: (cropped_image, x_offset, y_offset)
        - cropped_image: PIL Image of the bottom-right region
        - x_offset: x coordinate offset to convert back to full screen
        - y_offset: y coordinate offset to convert back to full screen
    """
    width, height = screen_image.size
    x_offset = width // 2
    y_offset = height // 2
    
    # Crop to bottom-right quarter
    cropped = screen_image.crop((x_offset, y_offset, width, height))
    
    return cropped, x_offset, y_offset


def recognize_in_bottom_right(screen_image, template_name, min_matches=4):
    """
    Recognize a template in the bottom-right quarter of the screen.
    
    Returns dict with coordinates adjusted to full screen, or None if not found.
    """
    cropped, x_offset, y_offset = get_bottom_right_region(screen_image)
    
    result = recognize_template(cropped, template_name, min_matches)
    
    if result is None:
        return None
    
    # Adjust coordinates to full screen
    result["x"] += x_offset
    result["y"] += y_offset
    result["x1"] += x_offset
    result["y1"] += y_offset
    result["x2"] += x_offset
    result["y2"] += y_offset
    
    return result


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
        # Main harvest loop with integrated initialization
        iteration = 0
        sort_executed = False  # Flag to track if sort config has been executed once
        
        while iteration < max_iterations:
            if stop_check and stop_check():
                raise StopExecution("Stopped by user")
            
            iteration += 1
            logger.info(f"Plants harvest loop: Iteration {iteration}")
            
            # Take a fresh screenshot for each iteration
            screen = ImageGrab.grab()
            
            # Step 1: Check for empty plants
            result_empty = recognize_template(screen, "plants/plants_empty1.png", min_matches=4)
            
            if result_empty is None:
                logger.info(f"Plants harvest loop [#{iteration}]: No empty plants found, exiting loop")
                break
            
            # Click on empty plant
            click_x = result_empty["x"]
            click_y = result_empty["y"]
            logger.info(f"Plants harvest loop [#{iteration}]: Clicking empty plant at ({click_x}, {click_y})")
            pyautogui.click(click_x, click_y)
            time.sleep(0.3)
            
            # Step 1.5: Execute sort config once (only on first empty plant detected)
            if not sort_executed:
                logger.info(f"Plants harvest loop [#{iteration}]: Executing sort config (first time)...")
                sort_config_path = Path("configs/帝江号收菜/切换拥有数量升序.json")
                
                if not sort_config_path.exists():
                    logger.warning(f"Sort config not found: {sort_config_path}, skipping")
                else:
                    try:
                        sort_steps = load_steps(sort_config_path)
                        
                        # Execute config timeline
                        run_timeline(
                            sort_steps,
                            stop_check=stop_check,
                            event_callback=None,
                            wait_for_events=True,
                        )
                        
                        logger.info(f"Plants harvest loop [#{iteration}]: Sort config executed successfully")
                        sort_executed = True
                        time.sleep(0.5)
                    except Exception as e:
                        logger.error(f"Plants harvest loop [#{iteration}]: Error executing sort config: {e}")
                        # Continue even if sort config fails
            
            # Step 2: Check for extractable cores (plants_extract) - optional, in bottom-right corner
            screen = ImageGrab.grab()
            result_extract = recognize_in_bottom_right(screen, "plants/plants_extract.png", min_matches=4)
            
            # Apply confidence threshold
            if result_extract is not None and result_extract["confidence"] < 90.0:
                logger.info(f"Plants harvest loop [#{iteration}]: Extract detection confidence {result_extract['confidence']:.1f}% below threshold 90%, rejecting")
                result_extract = None
            
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
                run_timeline(
                    steps,
                    stop_check=stop_check,
                    event_callback=None,
                    wait_for_events=True,
                )
                
                logger.info(f"Plants harvest loop [#{iteration}]: Extract core config completed")
                time.sleep(1.0)
            
            # Step 3: Check for harvestable plants (plants_confirm) - always required, in bottom-right corner
            screen = ImageGrab.grab()
            result_confirm = recognize_in_bottom_right(screen, "plants/plants_confirm.png", min_matches=4)
            
            # Apply confidence threshold
            if result_confirm is not None and result_confirm["confidence"] < 90.0:
                logger.info(f"Plants harvest loop [#{iteration}]: Confirm detection confidence {result_confirm['confidence']:.1f}% below threshold 90%, rejecting")
                result_confirm = None
            
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
                time.sleep(0.5)
                continue
            
            # Step 4: confirm not found, exit loop
            logger.info(f"Plants harvest loop [#{iteration}]: No confirm template found, exiting loop")
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
