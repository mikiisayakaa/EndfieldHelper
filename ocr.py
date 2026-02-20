from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

TEMPLATE_DIR = Path("templates")


def pil_to_bgr(image: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def load_template_bgr(template_path: Path | str) -> np.ndarray | None:
    path = Path(template_path)
    if not path.exists():
        return None
    return cv2.imread(str(path))


def crop_right_fraction(image: Image.Image, fraction: float = 0.2) -> tuple[Image.Image, int, int]:
    width, height = image.size
    crop_width = int(width * fraction)
    left = width - crop_width
    return image.crop((left, 0, width, height)), left, 0


def match_template(
    roi_bgr: np.ndarray,
    template_bgr: np.ndarray,
    method: int = cv2.TM_CCOEFF_NORMED,
) -> tuple[float, tuple[int, int]]:
    if roi_bgr.shape[0] < template_bgr.shape[0] or roi_bgr.shape[1] < template_bgr.shape[1]:
        return 0.0, (0, 0)
    result = cv2.matchTemplate(roi_bgr, template_bgr, method)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    return float(max_val), (int(max_loc[0]), int(max_loc[1]))


def _ssim_gray(image_a: np.ndarray, image_b: np.ndarray) -> float:
    image_a = image_a.astype(np.float64)
    image_b = image_b.astype(np.float64)

    c1 = (0.01 * 255) ** 2
    c2 = (0.03 * 255) ** 2

    mu_a = image_a.mean()
    mu_b = image_b.mean()
    sigma_a = image_a.var()
    sigma_b = image_b.var()
    covariance = ((image_a - mu_a) * (image_b - mu_b)).mean()

    numerator = (2 * mu_a * mu_b + c1) * (2 * covariance + c2)
    denominator = (mu_a ** 2 + mu_b ** 2 + c1) * (sigma_a + sigma_b + c2)
    if denominator == 0:
        return 0.0
    return float(numerator / denominator)


def ssim_color(image_a_bgr: np.ndarray, image_b_bgr: np.ndarray) -> float:
    hsv_a = cv2.cvtColor(image_a_bgr, cv2.COLOR_BGR2HSV)
    hsv_b = cv2.cvtColor(image_b_bgr, cv2.COLOR_BGR2HSV)

    scores = []
    for channel in range(3):
        scores.append(_ssim_gray(hsv_a[:, :, channel], hsv_b[:, :, channel]))
    return float(sum(scores) / len(scores))


def compare_similarity(candidate_bgr: np.ndarray, template_bgr: np.ndarray) -> float:
    if candidate_bgr.shape[:2] != template_bgr.shape[:2]:
        candidate_bgr = cv2.resize(candidate_bgr, (template_bgr.shape[1], template_bgr.shape[0]))
    return ssim_color(candidate_bgr, template_bgr)


def find_template_sift(
    screen_image: Image.Image | np.ndarray,
    template_path: Path | str,
    min_matches: int = 4,
    screen_gray: np.ndarray | None = None,
    ratio_threshold: float = 0.7,
) -> dict | None:
    """
    Find a template in the screen image using SIFT feature matching.
    
    Args:
        screen_image: Screen image (PIL Image or numpy array in BGR format)
        template_path: Path to template image
        min_matches: Minimum number of good feature matches required
        screen_gray: Optional pre-computed grayscale screen image
        ratio_threshold: Lowe's ratio test threshold (default 0.7, higher = more lenient)
    
    Returns:
        Dict with:
        {
            "center_x": int,
            "center_y": int,
            "confidence": float (0.0 to 1.0),
            "bbox": [x1, y1, x2, y2],
            "matches": int (number of good matches)
        }
        or None if not found
    """
    template_path = Path(template_path)
    if not template_path.exists():
        print(f"Template not found: {template_path}")
        return None
    
    # Convert screen image to BGR numpy array if needed
    if isinstance(screen_image, Image.Image):
        screen_cv = pil_to_bgr(screen_image)
    else:
        screen_cv = screen_image
    
    # Load template
    template_bgr = load_template_bgr(template_path)
    if template_bgr is None:
        print(f"Failed to load template: {template_path}")
        return None
    
    # Convert to grayscale
    if screen_gray is None:
        screen_gray = cv2.cvtColor(screen_cv, cv2.COLOR_BGR2GRAY)
    template_gray = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2GRAY)
    
    # Initialize SIFT detector
    sift = cv2.SIFT_create()
    
    # Detect keypoints and descriptors
    kp_screen, des_screen = sift.detectAndCompute(screen_gray, None)
    kp_template, des_template = sift.detectAndCompute(template_gray, None)
    
    if des_screen is None or des_template is None:
        print("SIFT: Not enough features found")
        return None
    
    # Create matcher and perform KNN matching
    matcher = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
    matches = matcher.knnMatch(des_template, des_screen, k=2)
    
    # Apply Lowe's ratio test to filter good matches
    good_matches = []
    for match_pair in matches:
        if len(match_pair) == 2:
            m, n = match_pair
            if m.distance < ratio_threshold * n.distance:
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
    
    # Get template corners and transform to screen coordinates
    template_h, template_w = template_bgr.shape[:2]
    corners = np.float32([
        [0, 0],
        [template_w, 0],
        [template_w, template_h],
        [0, template_h]
    ]).reshape(-1, 1, 2)
    
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
    x2 = min(screen_cv.shape[1], x2)
    y2 = min(screen_cv.shape[0], y2)
    
    # Calculate center and confidence
    center_x = int((x1 + x2) / 2)
    center_y = int((y1 + y2) / 2)
    confidence = np.sum(mask) / len(mask) if mask is not None else 1.0
    
    print(f"SIFT: Template matched! Matches: {len(good_matches)}, Confidence: {confidence:.2%}")
    
    return {
        "center_x": center_x,
        "center_y": center_y,
        "confidence": float(confidence),
        "bbox": [x1, y1, x2, y2],
        "matches": len(good_matches),
    }


def recognize_template(
    full_screen_image: Image.Image,
    template_name: str,
    min_matches: int = 4,
) -> dict | None:
    """
    Recognize a template in the full screen image and return position with confidence.
    
    Returns dict with confidence (percentage), x, y (center), and bbox (x1, y1, x2, y2).
    """
    template_path = TEMPLATE_DIR / template_name
    
    result = find_template_sift(full_screen_image, template_path, min_matches)
    
    if result is None:
        return None
    
    # Convert to legacy format for compatibility
    confidence_percent = result["confidence"] * 100
    
    print(
        f"Template recognized: {template_name}, Confidence: {confidence_percent:.1f}%, Center: ({result['center_x']}, {result['center_y']})"
    )
    
    return {
        "confidence": confidence_percent,
        "x": result["center_x"],
        "y": result["center_y"],
        "x1": result["bbox"][0],
        "y1": result["bbox"][1],
        "x2": result["bbox"][2],
        "y2": result["bbox"][3],
    }
