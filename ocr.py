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


def recognize_template(
    full_screen_image: Image.Image,
    template_name: str,
    min_matches: int = 4,
) -> dict | None:
    """
    Recognize a template in the full screen image and return position with confidence.
    """
    template_path = TEMPLATE_DIR / template_name

    if not template_path.exists():
        print(f"Template not found: {template_path}")
        return None

    full_screen_cv = pil_to_bgr(full_screen_image)
    template_img = cv2.imread(str(template_path))

    if template_img is None:
        print(f"Failed to load template: {template_path}")
        return None

    screen_gray = cv2.cvtColor(full_screen_cv, cv2.COLOR_BGR2GRAY)
    template_gray = cv2.cvtColor(template_img, cv2.COLOR_BGR2GRAY)

    sift = cv2.SIFT_create()

    kp_screen, des_screen = sift.detectAndCompute(screen_gray, None)
    kp_template, des_template = sift.detectAndCompute(template_gray, None)

    if des_screen is None or des_template is None:
        print("SIFT: Not enough features found")
        return None

    matcher = None
    use_gpu = False

    try:
        if cv2.cuda.getCudaEnabledDeviceCount() > 0:
            matcher = cv2.cuda.DescriptorMatcher_createBFMatcher(cv2.NORM_L2)
            use_gpu = True
        else:
            matcher = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
    except Exception as exc:
        print(f"SIFT: GPU BFMatcher failed ({exc}), using CPU matcher")
        matcher = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
        use_gpu = False

    if use_gpu:
        try:
            des_template_gpu = cv2.cuda_GpuMat()
            des_screen_gpu = cv2.cuda_GpuMat()
            des_template_gpu.upload(des_template.astype(np.float32))
            des_screen_gpu.upload(des_screen.astype(np.float32))
            matches = matcher.knnMatch(des_template_gpu, des_screen_gpu, k=2)
        except Exception as exc:
            print(f"SIFT: GPU matching error ({exc}), falling back to CPU")
            matcher = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
            matches = matcher.knnMatch(des_template, des_screen, k=2)
    else:
        matches = matcher.knnMatch(des_template, des_screen, k=2)

    good_matches = []
    for match_pair in matches:
        if len(match_pair) == 2:
            m, n = match_pair
            if m.distance < 0.7 * n.distance:
                good_matches.append(m)

    if len(good_matches) < min_matches:
        print(f"SIFT: Only {len(good_matches)} good matches found (need {min_matches})")
        return None

    src_pts = np.float32([kp_template[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp_screen[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

    h_matrix, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)

    if h_matrix is None:
        print("SIFT: Failed to compute homography")
        return None

    template_h, template_w = template_img.shape[:2]
    corners = np.float32(
        [[0, 0], [template_w, 0], [template_w, template_h], [0, template_h]]
    ).reshape(-1, 1, 2)

    transformed_corners = cv2.perspectiveTransform(corners, h_matrix)
    transformed_corners = transformed_corners.reshape(-1, 2)

    x_coords = transformed_corners[:, 0]
    y_coords = transformed_corners[:, 1]
    x1 = int(np.floor(np.min(x_coords)))
    x2 = int(np.ceil(np.max(x_coords)))
    y1 = int(np.floor(np.min(y_coords)))
    y2 = int(np.ceil(np.max(y_coords)))

    x1 = max(0, x1)
    y1 = max(0, y1)
    x2 = min(full_screen_cv.shape[1], x2)
    y2 = min(full_screen_cv.shape[0], y2)

    confidence = np.sum(mask) / len(mask) if mask is not None else 1.0
    confidence_percent = confidence * 100

    center_x = (x1 + x2) // 2
    center_y = (y1 + y2) // 2

    print(
        f"Template recognized: {template_name}, Confidence: {confidence_percent:.1f}%, Center: ({center_x}, {center_y})"
    )

    return {
        "confidence": confidence_percent,
        "x": center_x,
        "y": center_y,
        "x1": x1,
        "y1": y1,
        "x2": x2,
        "y2": y2,
    }
