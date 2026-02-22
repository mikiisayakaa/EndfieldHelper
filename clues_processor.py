from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import pyautogui
from PIL import Image

from ocr import find_template_sift
from automation import load_steps, run_timeline


CLUES_TEMPLATE_DIR = Path("templates") / "clues"
PLACE_CLUE_CONFIG = Path("configs") / "帝江号收菜" / "放置线索.json"


def process_clues_placement(
    confidence_threshold: float = 0.5,
    min_matches: int = 10,
    stop_check: Callable[[], bool] | None = None,
) -> dict:
    """
    Process clues recognition and placement.
    
    1. Take full screen screenshot
    2. For each clue (clue1-clue8), detect in two steps:
       a. Detect clue{num}.png
       b. Detect clue{num}full.png
       c. Compare confidence: if clue{num}.png > clue{num}full.png:
          - Click at the clue position
          - Execute the place_clue config file
       d. Otherwise skip to next clue
    3. Continue until all clues are processed
    
    Args:
        confidence_threshold: Minimum confidence (0-1) to trigger click
        min_matches: Minimum number of SIFT matches required
        stop_check: Optional callback to check if operation should stop
    
    Returns:
        Dict with:
        {
            "success": bool,
            "processed_clues": list of clue names that were found and placed,
            "total_found": int,
            "message": str
        }
    """
    processed_clues = []
    
    # Verify place_clue config exists
    if not PLACE_CLUE_CONFIG.exists():
        return {
            "success": False,
            "processed_clues": [],
            "total_found": 0,
            "message": f"Config file not found: {PLACE_CLUE_CONFIG}"
        }
    
    # Load the place_clue config once
    try:
        place_clue_data = load_steps(PLACE_CLUE_CONFIG)
    except Exception as e:
        return {
            "success": False,
            "processed_clues": [],
            "total_found": 0,
            "message": f"Failed to load config: {e}"
        }
    
    # Process each clue from clue1 to clue7
    for clue_num in range(1, 8):
        clue_name = f"clue{clue_num}"
        clue_template = CLUES_TEMPLATE_DIR / f"{clue_name}.png"
        clue_full_template = CLUES_TEMPLATE_DIR / f"{clue_name}full.png"
        
        # Check if we should stop
        if stop_check and stop_check():
            return {
                "success": False,
                "processed_clues": processed_clues,
                "total_found": len(processed_clues),
                "message": "Operation stopped by user"
            }
        
        # Check if templates exist
        if not clue_template.exists():
            print(f"Warning: Template not found: {clue_template}")
            continue
        
        if not clue_full_template.exists():
            print(f"Warning: Template not found: {clue_full_template}")
            continue
        
        # Take screenshot for this clue
        screenshot = pyautogui.screenshot()
        
        # Step 1: Try to find the clue using SIFT (clue{num}.png)
        result = find_template_sift(
            screenshot,
            clue_template,
            min_matches=min_matches,
            ratio_threshold=0.7
        )
        
        if result is None:
            print(f"{clue_name}: Not found")
            continue
        
        confidence = result.get("confidence", 0.0)
        
        if confidence < confidence_threshold:
            print(f"{clue_name}: Found but confidence too low: {confidence:.2%}")
            continue
        
        # Step 2: Try to find the full clue (clue{num}full.png)
        result_full = find_template_sift(
            screenshot,
            clue_full_template,
            min_matches=min_matches,
            ratio_threshold=0.7
        )
        
        confidence_full = result_full.get("confidence", 0.0) if result_full else 0.0
        
        # Compare confidence
        if confidence <= confidence_full:
            print(f"{clue_name}: Skipped (confidence comparison failed: "
                  f"{confidence:.2%} <= {confidence_full:.2%})")
            continue
        
        # Clue found with confidence > full clue confidence
        center_x = result["center_x"]
        center_y = result["center_y"]
        matches = result.get("matches", 0)
        
        print(f"{clue_name}: Found at ({center_x}, {center_y}), "
              f"confidence={confidence:.2%} > {confidence_full:.2%}, matches={matches}")
        
        # Check stop again before clicking
        if stop_check and stop_check():
            return {
                "success": False,
                "processed_clues": processed_clues,
                "total_found": len(processed_clues),
                "message": "Operation stopped by user"
            }
        
        try:
            # Click the clue position
            pyautogui.click(center_x, center_y)
            time.sleep(0.5)  # Wait a bit after clicking
            
            # Execute the place_clue config
            run_timeline(
                place_clue_data,
                stop_check=stop_check,
                event_callback=None,
                wait_for_events=True,
            )
            
            processed_clues.append(clue_name)
            print(f"{clue_name}: Placed successfully")
            
            # Wait a bit before processing next clue
            time.sleep(0.5)
            
        except Exception as e:
            print(f"{clue_name}: Error during placement: {e}")
            # Continue to next clue even if this one failed
            continue
    
    # Return summary
    total_found = len(processed_clues)
    
    if total_found > 0:
        return {
            "success": True,
            "processed_clues": processed_clues,
            "total_found": total_found,
            "message": f"Successfully processed {total_found} clue(s): {', '.join(processed_clues)}"
        }
    else:
        return {
            "success": False,
            "processed_clues": [],
            "total_found": 0,
            "message": "No clues found"
        }
