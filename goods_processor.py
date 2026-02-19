from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import cv2
import easyocr
import numpy as np
from PIL import Image, ImageGrab
from pynput import keyboard


SCREENSHOT_DIR = Path("templates")
SCREENSHOT_REGION = (129, 580, 2260, 1438)

_DEBUG_MODE = False
TEMPLATE_IMAGE_PATH = SCREENSHOT_DIR / "goods_template_gudi_7x2.png"

# GPU initialization
def _init_gpu() -> bool:
    """Initialize and check GPU availability."""
    try:
        cuda_enabled = cv2.cuda.getCudaEnabledDeviceCount() > 0
        if cuda_enabled:
            # Get GPU device info
            device_count = cv2.cuda.getCudaEnabledDeviceCount()
            print(f"GPU detected: {device_count} CUDA device(s) available")
            # Set active GPU (use first one)
            cv2.cuda.setDevice(0)
            cap = cv2.cuda.getCudaEnabledDeviceCount()
            print(f"Active GPU device: {cv2.cuda.getDevice()}")
            return True
        else:
            print("No CUDA-enabled GPU detected")
            return False
    except Exception as e:
        print(f"GPU initialization error: {e}")
        return False

GPU_AVAILABLE = _init_gpu()
_EASYOCR_GPU = GPU_AVAILABLE  # Use GPU for EasyOCR if available


def parse_grid_from_template(template_path: Path | str) -> tuple[int, int]:
    """
    Extract grid dimensions from template filename.
    Example: 'goods_template_gudi_7x2.png' -> (7, 2) (cols, rows)
    
    Args:
        template_path: Path to template image or filename
    
    Returns:
        (cols, rows) tuple, default (7, 2) if parsing fails
    """
    filename = Path(template_path).stem if isinstance(template_path, (Path, str)) else str(template_path)
    
    # Look for pattern like '7x2' in the filename
    match = re.search(r'(\d+)x(\d+)', filename)
    if match:
        cols = int(match.group(1))
        rows = int(match.group(2))
        return (cols, rows)
    
    # Default fallback
    return (7, 2)


def find_template_region(
    full_screen_image: Image.Image | None,
    template_path: Path = TEMPLATE_IMAGE_PATH,
    min_matches: int = 4,
    full_screen_cv: np.ndarray | None = None,
    screen_gray: np.ndarray | None = None,
) -> tuple[int, int, int, int] | None:
    """
    Find the goods region in the full screen image using SIFT feature matching.
    Robust to scaling, rotation, and perspective changes.
    GPU-accelerated when available.
    
    Args:
        full_screen_image: Full screen image as PIL Image
        template_path: Path to template image
        min_matches: Minimum number of good feature matches required
    
    Returns:
        Bounding box (x1, y1, x2, y2) if found, None otherwise
    """
    if not template_path.exists():
        return None
    
    if full_screen_cv is None or screen_gray is None:
        if full_screen_image is None:
            raise ValueError("full_screen_image is required when no precomputed screen is provided")
        # Convert PIL images to OpenCV format (BGR)
        full_screen_cv = cv2.cvtColor(np.array(full_screen_image), cv2.COLOR_RGB2BGR)
    template_img = cv2.imread(str(template_path))
    
    if template_img is None:
        return None
    
    # Convert to grayscale
    if screen_gray is None:
        screen_gray = cv2.cvtColor(full_screen_cv, cv2.COLOR_BGR2GRAY)
    template_gray = cv2.cvtColor(template_img, cv2.COLOR_BGR2GRAY)
    
    # Initialize SIFT detector
    sift = cv2.SIFT_create()
    
    # Detect keypoints and descriptors
    kp_screen, des_screen = sift.detectAndCompute(screen_gray, None)
    kp_template, des_template = sift.detectAndCompute(template_gray, None)
    
    if des_screen is None or des_template is None:
        print("SIFT: Not enough features found")
        return None
    
    # Use GPU-accelerated matcher if available
    matcher = None
    use_gpu = False
    
    try:
        if cv2.cuda.getCudaEnabledDeviceCount() > 0:
            # Try to use GPU-accelerated BFMatcher
            matcher = cv2.cuda.DescriptorMatcher_createBFMatcher(cv2.NORM_L2)
            use_gpu = True
            print("SIFT: Using GPU-accelerated BFMatcher (CUDA)")
        else:
            matcher = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
            print("SIFT: Using CPU BFMatcher")
    except Exception as e:
        print(f"SIFT: GPU BFMatcher failed ({e}), using CPU matcher")
        matcher = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
        use_gpu = False
    
    # KNN matching
    if use_gpu:
        # For GPU matcher, upload to GPU first
        try:
            des_template_gpu = cv2.cuda_GpuMat()
            des_screen_gpu = cv2.cuda_GpuMat()
            des_template_gpu.upload(des_template.astype(np.float32))
            des_screen_gpu.upload(des_screen.astype(np.float32))
            matches = matcher.knnMatch(des_template_gpu, des_screen_gpu, k=2)
        except Exception as e:
            print(f"SIFT: GPU matching error ({e}), falling back to CPU")
            matcher = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
            matches = matcher.knnMatch(des_template, des_screen, k=2)
    else:
        # CPU matcher
        matches = matcher.knnMatch(des_template, des_screen, k=2)
    
    # Apply Lowe's ratio test to filter good matches
    good_matches = []
    for match_pair in matches:
        if len(match_pair) == 2:
            m, n = match_pair
            # If first match is significantly better than second, it's a good match
            if m.distance < 0.7 * n.distance:
                good_matches.append(m)
    
    if len(good_matches) < min_matches:
        print(f"SIFT: Only {len(good_matches)} good matches found (need {min_matches})")
        return None
    
    # Extract location of good matches
    src_pts = np.float32([kp_template[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp_screen[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    
    # Find homography matrix using RANSAC
    H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
    
    if H is None:
        print("SIFT: Failed to compute homography")
        return None
    
    # Get template corners in template coordinate system
    template_h, template_w = template_img.shape[:2]
    corners = np.float32([
        [0, 0],
        [template_w, 0],
        [template_w, template_h],
        [0, template_h]
    ]).reshape(-1, 1, 2)
    
    # Transform corners to screen coordinate system
    transformed_corners = cv2.perspectiveTransform(corners, H)
    transformed_corners = transformed_corners.reshape(-1, 2)
    
    # Get bounding box from transformed corners
    x_coords = transformed_corners[:, 0]
    y_coords = transformed_corners[:, 1]
    x1 = int(np.floor(np.min(x_coords)))
    x2 = int(np.ceil(np.max(x_coords)))
    y1 = int(np.floor(np.min(y_coords)))
    y2 = int(np.ceil(np.max(y_coords)))
    
    # Clamp to image bounds
    x1 = max(0, x1)
    y1 = max(0, y1)
    x2 = min(full_screen_cv.shape[1], x2)
    y2 = min(full_screen_cv.shape[0], y2)
    
    # Calculate scale and confidence
    scale_factor = np.linalg.norm(transformed_corners[1] - transformed_corners[0]) / template_w
    confidence = np.sum(mask) / len(mask) if mask is not None else 1.0
    
    print(f"SIFT: Template matched! Scale: {scale_factor:.2f}x, Matches: {len(good_matches)}, Confidence: {confidence:.2%}")
    
    return (x1, y1, x2, y2)


def _resolve_goods_group(template_path: Path | str | None) -> str | None:
    if not template_path:
        return None
    name = Path(template_path).name.lower()
    if "gudi" in name:
        return "gudi"
    if "wuling" in name:
        return "wuling"
    return None


def _template_sort_key(path: Path) -> tuple[int, str]:
    match = re.search(r"(\d+)$", path.stem)
    if match:
        return (int(match.group(1)), path.stem)
    return (0, path.stem)


def _load_goods_item_templates(group: str) -> list[Path]:
    prefix = f"goods_{group}_"
    return sorted(SCREENSHOT_DIR.glob(f"{prefix}*.png"), key=_template_sort_key)


def split_tiles(image: Image.Image, rows: int = 2, cols: int = 7) -> list[tuple[int, int, Image.Image]]:
    width, height = image.size
    cell_width = width // cols
    cell_height = height // rows

    tiles: list[tuple[int, int, Image.Image]] = []
    for row in range(rows):
        for col in range(cols):
            left = col * cell_width
            upper = row * cell_height
            right = (col + 1) * cell_width if col < cols - 1 else width
            lower = (row + 1) * cell_height if row < rows - 1 else height
            tiles.append((row + 1, col + 1, image.crop((left, upper, right, lower))))
    return tiles


def _pick_percent_token(tokens: list[tuple[str, int, int, int, int]]) -> tuple[str | None, tuple[int, int, int, int] | None]:
    cleaned = []
    for index, token, x, y, w, h in tokens:
        if not token:
            continue
        value = token.strip()
        if not value:
            continue
        cleaned.append((index, value, x, y, w, h))

    percent_candidates = [t for t in cleaned if "%" in t[1]]
    digit_candidates = [t for t in cleaned if re.search(r"\d", t[1])]

    if percent_candidates:
        best = max(percent_candidates, key=lambda t: t[3] + t[5])
        if re.search(r"\d", best[1]):
            return best[1], (best[2], best[3], best[4], best[5])
        for d in digit_candidates:
            if abs(d[3] - best[3]) <= max(d[5], best[5]):
                left = min(d[2], best[2])
                top = min(d[3], best[3])
                right = max(d[2] + d[4], best[2] + best[4])
                bottom = max(d[3] + d[5], best[3] + best[5])
                return f"{d[1]}%", (left, top, right - left, bottom - top)

    fallback = []
    for d in digit_candidates:
        match = re.search(r"\d+(?:\.\d+)?", d[1])
        if match:
            value = float(match.group(0))
            if value <= 100:
                fallback.append((value, d))
    if fallback:
        _, d = min(fallback, key=lambda item: item[0])
        return d[1], (d[2], d[3], d[4], d[5])

    return None, None


def _extract_tokens(ocr_results: list) -> list[tuple[str, int, int, int, int]]:
    tokens: list[tuple[str, int, int, int, int]] = []
    for index, result in enumerate(ocr_results):
        if len(result) < 2:
            continue
        box = result[0]
        text = result[1]
        xs = [point[0] for point in box]
        ys = [point[1] for point in box]
        x_min = int(min(xs))
        y_min = int(min(ys))
        x_max = int(max(xs))
        y_max = int(max(ys))
        tokens.append((index, text, x_min, y_min, x_max - x_min, y_max - y_min))
    return tokens


def ocr_percent_and_bbox(
    tile_bgr: np.ndarray,
    reader: easyocr.Reader,
) -> tuple[str | None, tuple[int, int, int, int] | None]:
    gray = cv2.cvtColor(tile_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    rgb = cv2.cvtColor(thresh, cv2.COLOR_GRAY2RGB)
    ocr_results = reader.readtext(rgb, detail=1, allowlist="0123456789.%")
    tokens = _extract_tokens(ocr_results)
    return _pick_percent_token(tokens)


def detect_arrow_color(
    tile_bgr: np.ndarray,
    percent_bbox: tuple[int, int, int, int] | None,
) -> str:
    height, width = tile_bgr.shape[:2]
    if percent_bbox:
        x, y, w, h = percent_bbox
        x = int(x / 2)
        y = int(y / 2)
        w = int(w / 2)
        h = int(h / 2)
        left = max(0, x - int(1.5 * w))
        right = min(width, x + int(2.0 * w))
        top = max(0, y - int(0.6 * h))
        bottom = min(height, y + int(1.2 * h))
        roi = tile_bgr[top:bottom, left:right]
    else:
        roi = tile_bgr

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    red_mask1 = cv2.inRange(hsv, (0, 80, 80), (10, 255, 255))
    red_mask2 = cv2.inRange(hsv, (170, 80, 80), (180, 255, 255))
    red_mask = cv2.bitwise_or(red_mask1, red_mask2)
    green_mask = cv2.inRange(hsv, (35, 80, 80), (85, 255, 255))

    red_count = int(cv2.countNonZero(red_mask))
    green_count = int(cv2.countNonZero(green_mask))

    if red_count < 15 and green_count < 15:
        return "unknown"
    if red_count > green_count:
        return "red"
    if green_count > red_count:
        return "green"
    return "unknown"


def crop_percent_roi(tile_bgr: np.ndarray) -> np.ndarray:
    height, width = tile_bgr.shape[:2]
    left = int(width * 0.5)
    top = int(height * 0.58)
    right = int(width * 1.0)
    bottom = int(height * 0.68)
    left = max(0, min(left, width))
    right = max(0, min(right, width))
    top = max(0, min(top, height))
    bottom = max(0, min(bottom, height))
    if right <= left or bottom <= top:
        return tile_bgr
    return tile_bgr[top:bottom, left:right]


def process_goods_image(image_path: Path | None = None, save_screenshot: bool = True, template_path: Path | str | None = None) -> dict:
    """
    Process a goods screenshot or image file.
    Takes full screen screenshot if image_path is None, automatically detects goods region using template matching,
    otherwise processes the given image.
    Returns JSON data with recognition results.
    
    Args:
        image_path: Path to image file. If None, takes a full screen screenshot and auto-detects region.
        save_screenshot: Whether to save the screenshot to disk (only used when image_path is None).
        template_path: Path to template image for region detection. If None, uses default TEMPLATE_IMAGE_PATH.
    
    Returns:
        Dictionary with OCR results including "goods" list and "region" coordinates.
    """
    template_group = _resolve_goods_group(template_path)
    if template_group is None:
        raise ValueError("goods_ocr requires template group: gudi or wuling")

    if image_path is None:
        # Take full screen screenshot
        full_screen = ImageGrab.grab()
        image_path = "<screenshot>"
    else:
        full_screen = Image.open(image_path)

    if save_screenshot and image_path == "<screenshot>":
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        saved_path = SCREENSHOT_DIR / f"goods_{timestamp}.png"
        full_screen.save(saved_path)
        image_path = str(saved_path)
        print(f"Screenshot saved: {saved_path}")

    template_paths = _load_goods_item_templates(template_group)
    if not template_paths:
        raise FileNotFoundError(f"No templates found for group: {template_group}")

    full_screen_cv = cv2.cvtColor(np.array(full_screen), cv2.COLOR_RGB2BGR)
    screen_gray = cv2.cvtColor(full_screen_cv, cv2.COLOR_BGR2GRAY)
    reader = easyocr.Reader(["en"], gpu=_EASYOCR_GPU)
    results = []

    for template_img in template_paths:
        region = find_template_region(
            None,
            template_path=template_img,
            full_screen_cv=full_screen_cv,
            screen_gray=screen_gray,
        )
        if not region:
            continue
        x1, y1, x2, y2 = region
        tile = full_screen.crop((x1, y1, x2, y2))
        tile_bgr = cv2.cvtColor(np.array(tile), cv2.COLOR_RGB2BGR)
        roi_bgr = crop_percent_roi(tile_bgr)
        percent_text, percent_bbox = ocr_percent_and_bbox(roi_bgr, reader)
        arrow_color = detect_arrow_color(roi_bgr, percent_bbox)
        center_x = int((x1 + x2) / 2)
        center_y = int((y1 + y2) / 2)
        results.append(
            {
                "row": None,
                "col": None,
                "percent": percent_text,
                "arrow": arrow_color,
                "center_x": center_x,
                "center_y": center_y,
                "template": template_img.name,
                "bbox": [x1, y1, x2, y2],
            }
        )

    return {
        "timestamp": datetime.now().isoformat(),
        "screenshot": str(image_path),
        "debug_dir": None,
        "goods": results,
        "region": None,
        "cols": None,
        "rows": None,
        "template": template_group,
        "template_group": template_group,
    }


def analyze_goods_data(ocr_result: dict, cols: int = 7, rows: int = 2) -> dict | None:
    """
    Analyze OCR result to find the item with max percentage and green arrow.
    Returns the row, col, percent value, and the center position of the tile.
    
    Args:
        ocr_result: Output from process_goods_image()
        cols: Number of columns in grid (default 7)
        rows: Number of rows in grid (default 2)
    
    Returns:
        A dict with:
        {
            "row": int,
            "col": int,
            "percent": str (e.g., "5.2%"),
            "percent_value": float (e.g., 5.2),
            "center_x": int,
            "center_y": int
        }
        or None if no valid item found.
    """
    goods_list = ocr_result.get("goods", [])
    
    # Filter: percent is not null and arrow is green
    valid_items = [
        item for item in goods_list
        if item.get("percent") is not None and item.get("arrow") == "green"
    ]
    
    if not valid_items:
        return None
    
    # Extract percent value and find max
    def extract_percent_value(percent_str: str) -> float:
        """Extract numeric value from percent string like '5.2%'"""
        match = re.search(r"(\d+\.?\d*)", percent_str)
        if match:
            return float(match.group(1))
        return 0.0
    
    max_item = max(valid_items, key=lambda x: extract_percent_value(x.get("percent", "0%")))
    
    row = max_item.get("row")  # 1 or 2
    col = max_item.get("col")  # 1-7
    percent = max_item.get("percent")
    percent_value = extract_percent_value(percent)

    center_x = max_item.get("center_x")
    center_y = max_item.get("center_y")
    if center_x is None or center_y is None:
        # Get the region used (from ocr_result or use default)
        region = ocr_result.get("region", SCREENSHOT_REGION)
        x1, y1, x2, y2 = region
        width = x2 - x1
        height = y2 - y1

        tile_width = width / cols
        tile_height = height / rows

        # Center position of the tile in screen coordinates
        center_x = int(x1 + (col - 0.5) * tile_width)
        center_y = int(y1 + (row - 0.5) * tile_height)
    
    return {
        "row": row,
        "col": col,
        "percent": percent,
        "percent_value": percent_value,
        "center_x": center_x,
        "center_y": center_y,
    }


def format_goods_ocr_items(ocr_result: dict) -> list[str]:
    """Format OCR items for logging (direction + percent per tile)."""
    goods_list = ocr_result.get("goods", []) if ocr_result else []
    formatted: list[str] = []

    for item in goods_list:
        row = item.get("row")
        col = item.get("col")
        percent = item.get("percent")
        arrow = item.get("arrow")
        template_name = item.get("template")

        if arrow == "green":
            direction = "up"
        elif arrow == "red":
            direction = "down"
        else:
            direction = "unknown"

        percent_text = percent if percent is not None else "none"
        if template_name:
            formatted.append(
                f"row={row} col={col} template={template_name} direction={direction} percent={percent_text}"
            )
        else:
            formatted.append(
                f"row={row} col={col} direction={direction} percent={percent_text}"
            )

    return formatted


def on_capture() -> None:
    try:
        print("Processing...")
        data = process_goods_image()
        print(json.dumps(data, ensure_ascii=False, indent=2))
        
        # Analyze and print the result
        analysis = analyze_goods_data(data, cols=data.get("cols", 7), rows=data.get("rows", 2))
        if analysis:
            print("\n=== Analysis Result ===")
            print(f"Max green arrow item: Row {analysis['row']}, Col {analysis['col']}")
            print(f"Percent: {analysis['percent']} ({analysis['percent_value']:.2f}%)")
            print(f"Center position: ({analysis['center_x']}, {analysis['center_y']})")
        else:
            print("\nNo valid items found (percent not null and arrow is green)")
    except Exception as e:
        print(f"Error: {e}")


def on_exit() -> None:
    print("Exiting...")
    sys.exit(0)


def start_listener() -> None:
    print("Goods Processor started. Press S to capture & process, X to exit.")
    with keyboard.GlobalHotKeys({"s": on_capture, "x": on_exit}) as listener:
        listener.join()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Goods Processor - OCR recognition for game goods")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode to save all cropped screenshots")
    args = parser.parse_args()

    if args.debug:
        _DEBUG_MODE = True
        print("Debug mode enabled")

    start_listener()
