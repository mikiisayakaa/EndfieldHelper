from __future__ import annotations

import time
from pathlib import Path

import pyautogui
from PIL import Image, ImageGrab

from ocr import pil_to_bgr, find_template_sift


ITEMS_DIR = Path("templates") / "items"


def get_item_templates() -> list[tuple[str, Path]]:
    """
    Get all item templates from templates/items directory.
    
    Returns:
        List of (item_id, template_path) tuples
        Example: [("healing_item", Path("templates/items/healing_item.png")), ...]
    """
    if not ITEMS_DIR.exists():
        return []
    
    templates = []
    for template_path in sorted(ITEMS_DIR.glob("*.png")):
        item_id = template_path.stem  # filename without extension
        templates.append((item_id, template_path))
    
    return templates


def find_item_with_sift(
    full_screen_image: Image.Image,
    template_path: Path,
    min_matches: int = 4,
) -> dict | None:
    """
    Find an item in the full screen image using SIFT feature matching.
    
    Args:
        full_screen_image: Full screen PIL Image
        template_path: Path to item template image
        min_matches: Minimum number of good feature matches required
    
    Returns:
        Dict with:
        {
            "center_x": int,
            "center_y": int,
            "confidence": float,
            "bbox": [x1, y1, x2, y2]
        }
        or None if not found
    """
    if not template_path.exists():
        print(f"Template not found: {template_path}")
        return None
    
    # Convert to OpenCV format
    full_screen_cv = pil_to_bgr(full_screen_image)
    
    # Use unified SIFT function
    result = find_template_sift(full_screen_cv, template_path, min_matches)
    
    return result


def process_item_drag(item_id: str) -> dict:
    """
    Process item drag operation:
    1. Take screenshot
    2. Find item using SIFT
    3. Drag from item center to screen position (3/4 width, 1/2 height)
    
    Args:
        item_id: Item identifier (e.g., "healing_item")
    
    Returns:
        Dictionary with operation result
    """
    # Find template path
    template_path = ITEMS_DIR / f"{item_id}.png"
    if not template_path.exists():
        return {
            "success": False,
            "error": f"Template not found: {template_path}",
        }
    
    # Take screenshot
    full_screen = ImageGrab.grab()
    screen_width, screen_height = full_screen.size
    
    # Find item
    result = find_item_with_sift(full_screen, template_path)
    
    if result is None:
        return {
            "success": False,
            "error": f"Item '{item_id}' not found in screenshot",
        }
    
    # Calculate drag endpoints
    start_x = result["center_x"]
    start_y = result["center_y"]
    end_x = int(screen_width * 0.75)  # 3/4 of screen width
    end_y = int(screen_height * 0.5)   # 1/2 of screen height
    
    print(f"Dragging {item_id} from ({start_x}, {start_y}) to ({end_x}, {end_y})")
    
    # Perform drag
    pyautogui.moveTo(start_x, start_y)
    time.sleep(0.1)
    pyautogui.drag(end_x - start_x, end_y - start_y, duration=0.5, button='left')
    
    return {
        "success": True,
        "item_id": item_id,
        "start": (start_x, start_y),
        "end": (end_x, end_y),
        "confidence": result["confidence"],
    }
