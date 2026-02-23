import ctypes
import json
import logging
import threading
import time
from pathlib import Path
from typing import Callable

from ctypes import wintypes

import pyautogui
from pynput import keyboard, mouse


_SCREEN_SIZE: tuple[int, int] = (2560, 1600)
_SCREEN_OFFSET: tuple[int, int] = (0, 0)


def set_screen_transform(width: int, height: int, offset_x: int = 0, offset_y: int = 0) -> None:
    global _SCREEN_SIZE, _SCREEN_OFFSET
    width = max(1, int(width))
    height = max(1, int(height))
    _SCREEN_SIZE = (width, height)
    _SCREEN_OFFSET = (int(offset_x), int(offset_y))


def get_screen_size() -> tuple[int, int]:
    return _SCREEN_SIZE


def get_screen_offset() -> tuple[int, int]:
    return _SCREEN_OFFSET


def _relative_to_absolute(value: float, max_value: int) -> int:
    return int(round(float(value) * max_value))


def _coords_relative_to_absolute(x_rel: float, y_rel: float) -> tuple[int, int]:
    width, height = get_screen_size()
    offset_x, offset_y = get_screen_offset()
    return (
        _relative_to_absolute(x_rel, width) + offset_x,
        _relative_to_absolute(y_rel, height) + offset_y,
    )


def load_steps(config_path: Path) -> dict:
    """Load steps from config (timeline format)."""
    with config_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data


def save_steps(config_path: Path, steps: dict) -> None:
    """Save steps to config (timeline format)"""
    cleaned = {
        "timeline": [
            {k: v for k, v in event.items() if not k.startswith("_")}
            for event in steps.get("timeline", [])
        ],
    }
    
    with config_path.open("w", encoding="utf-8") as handle:
        json.dump(cleaned, handle, ensure_ascii=False, indent=2)


class StopExecution(Exception):
    pass


COMPOSITE_BREAK_EVENT = threading.Event()


def request_composite_break() -> None:
    COMPOSITE_BREAK_EVENT.set()


def consume_composite_break() -> bool:
    if COMPOSITE_BREAK_EVENT.is_set():
        COMPOSITE_BREAK_EVENT.clear()
        return True
    return False


def clear_composite_break() -> None:
    COMPOSITE_BREAK_EVENT.clear()


class Recorder:
    """Records keyboard and mouse operations (clicks, drags, holds, key presses/releases)."""
    
    def __init__(
        self,
        click_filter: Callable[[int, int], bool] | None = None,
        drag_threshold: int = 5,
        hold_threshold: float = 0.3,
    ) -> None:
        self.timeline: list[dict] = []
        self.recording = False
        self.start_time: float | None = None
        self.mouse_listener: mouse.Listener | None = None
        self.key_listener: keyboard.Listener | None = None
        self.click_filter = click_filter
        self.drag_threshold = drag_threshold
        self.hold_threshold = hold_threshold
        
        # Track mouse drag state
        self.mouse_down: dict | None = None
        self.pressed_keys: dict = {}
        self._skip_recording = False  # Flag to skip recording all operations (for internal sequences like goods_ocr)

    def _to_relative(self, x: int, y: int) -> tuple[float, float]:
        width, height = get_screen_size()
        offset_x, offset_y = get_screen_offset()
        return round((x - offset_x) / width, 6), round((y - offset_y) / height, 6)
    
    def _elapsed_time(self) -> float:
        """Get elapsed time since recording started."""
        if self.start_time is None:
            return 0.0
        return time.monotonic() - self.start_time
    
    def _add_event(self, event_type: str, **kwargs) -> None:
        """Add timestamped event to timeline."""
        event = {
            "time": round(self._elapsed_time(), 3),
            "type": event_type,
            **kwargs
        }
        self.timeline.append(event)
    
    def _normalize_key(self, key: keyboard.Key | keyboard.KeyCode) -> str:
        """Convert key to string representation."""
        if isinstance(key, keyboard.KeyCode) and key.char:
            return key.char
        if isinstance(key, keyboard.Key):
            return key.name or str(key)
        return str(key)
    
    def on_click(self, x: int, y: int, button: mouse.Button, pressed: bool) -> None:
        """Handle mouse click events."""
        if not self.recording or self._skip_recording:
            return
        
        if pressed:
            if self.click_filter and self.click_filter(x, y):
                return
            self.mouse_down = {
                "x": x,
                "y": y,
                "button": button.name,
                "time": self._elapsed_time(),
            }
        else:
            if self.mouse_down is None:
                return
            
            # Calculate movement and duration
            dx = abs(x - self.mouse_down["x"])
            dy = abs(y - self.mouse_down["y"])
            duration = self._elapsed_time() - self.mouse_down["time"]
            
            if dx > self.drag_threshold or dy > self.drag_threshold:
                # It's a drag (moved significantly)
                start_x_rel, start_y_rel = self._to_relative(
                    self.mouse_down["x"], self.mouse_down["y"]
                )
                end_x_rel, end_y_rel = self._to_relative(x, y)
                self._add_event(
                    "drag",
                    start_x=start_x_rel,
                    start_y=start_y_rel,
                    end_x=end_x_rel,
                    end_y=end_y_rel,
                    button=self.mouse_down["button"],
                    duration=duration,
                )
            elif duration >= self.hold_threshold:
                # It's a hold (stayed in place for a while)
                x_rel, y_rel = self._to_relative(self.mouse_down["x"], self.mouse_down["y"])
                self._add_event(
                    "hold",
                    x=x_rel,
                    y=y_rel,
                    button=self.mouse_down["button"],
                    duration=duration,
                )
            else:
                # It's a quick click
                x_rel, y_rel = self._to_relative(self.mouse_down["x"], self.mouse_down["y"])
                self._add_event(
                    "click",
                    x=x_rel,
                    y=y_rel,
                    button=self.mouse_down["button"],
                )
            
            self.mouse_down = None
    
    def on_press(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        """Handle key press events."""
        if not self.recording or self._skip_recording:
            return
        
        key_name = self._normalize_key(key)
        
        # Check if key is already pressed
        if key_name not in self.pressed_keys or not self.pressed_keys[key_name]:
            if key_name not in self.pressed_keys:
                self.pressed_keys[key_name] = []
            self.pressed_keys[key_name].append(self._elapsed_time())
            self._add_event("key_press", key=key_name)
    
    def on_release(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        """Handle key release events."""
        if not self.recording or self._skip_recording:
            return
        
        key_name = self._normalize_key(key)
        
        if key_name in self.pressed_keys and self.pressed_keys[key_name]:
            self.pressed_keys[key_name].pop()
            self._add_event("key_release", key=key_name)
    
    def record_arrow_key_press(self, key_name: str) -> None:
        """Record an arrow key press event (called from low-level keyboard hook)."""
        if not self.recording or self._skip_recording:
            return
        
        # key_name should be 'up', 'down', 'left', 'right'
        if key_name not in self.pressed_keys:
            self.pressed_keys[key_name] = []
        self.pressed_keys[key_name].append(self._elapsed_time())
        self._add_event("key_press", key=key_name)
    
    def record_arrow_key_release(self, key_name: str) -> None:
        """Record an arrow key release event (called from low-level keyboard hook)."""
        if not self.recording or self._skip_recording:
            return
        
        # key_name should be 'up', 'down', 'left', 'right'
        if key_name in self.pressed_keys and self.pressed_keys[key_name]:
            self.pressed_keys[key_name].pop()
            self._add_event("key_release", key=key_name)
    
    def start(self) -> None:
        """Start recording operations."""
        if self.recording:
            return
        
        self.timeline = []
        self.pressed_keys = {}
        self.mouse_down = None
        self.start_time = time.monotonic()
        self.recording = True
        
        # Start listeners
        self.mouse_listener = mouse.Listener(on_click=self.on_click)
        self.key_listener = keyboard.Listener(on_press=self.on_press, on_release=self.on_release)
        
        self.mouse_listener.start()
        self.key_listener.start()
    
    def stop(self) -> dict:
        """Stop recording and return recorded data."""
        if not self.recording:
            return {"timeline": self.timeline}
        
        self.recording = False
        
        if self.mouse_listener:
            self.mouse_listener.stop()
        if self.key_listener:
            self.key_listener.stop()
        
        # Clean up internal hotkeys
        # self._cleanup_internal_hotkeys()
        
        return {"timeline": self.timeline}
    
    def _cleanup_internal_hotkeys(self) -> None:
        """Remove internal hotkeys from timeline (Ctrl+X and OCR hotkeys)."""
        if not self.timeline:
            return
        
        # Step 1: Remove the last 2 operations (Ctrl+X stop hotkey)
        if len(self.timeline) >= 2:
            self.timeline = self.timeline[:-2]
        
        # Step 2: Find and remove hotkeys before OCR operations
        # We need to iterate backwards and track which indices to remove
        indices_to_remove = set()
        
        for i in range(len(self.timeline)):
            event = self.timeline[i]
            event_type = event.get("type", "")
            
            # Check if this is an OCR operation
            if event_type.endswith("ocr"):
                # Mark the 3 operations before this OCR for removal
                # (These are the hotkey operations: Ctrl press, Shift press, key press)
                for j in range(max(0, i - 3), i):
                    indices_to_remove.add(j)
        
        # Remove marked operations (iterate backwards to preserve indices)
        for i in sorted(indices_to_remove, reverse=True):
            self.timeline.pop(i)


def _sleep_with_stop(seconds: float, stop_check: Callable[[], bool] | None) -> None:
    if seconds <= 0:
        return
    if stop_check is None:
        time.sleep(seconds)
        return
    end_time = time.monotonic() + seconds
    while time.monotonic() < end_time:
        if stop_check():
            raise StopExecution("Stopped")
        time.sleep(0.05)


def _hold_key_for_duration(
    controller, key: str, duration: float, stop_check: Callable[[], bool] | None
) -> None:
    """Hold a key for the specified duration."""
    from pynput.keyboard import Key as PynputKey
    
    # Map key string to pynput Key object if needed
    key_map = {
        'shift': PynputKey.shift,
        'ctrl': PynputKey.ctrl,
        'alt': PynputKey.alt,
        'space': ' ',
        'enter': PynputKey.enter,
        'tab': PynputKey.tab,
        'backspace': PynputKey.backspace,
        'delete': PynputKey.delete,
        'up': PynputKey.up,
        'down': PynputKey.down,
        'left': PynputKey.left,
        'right': PynputKey.right,
        'home': PynputKey.home,
        'end': PynputKey.end,
        'pageup': PynputKey.page_up,
        'pagedown': PynputKey.page_down,
    }
    
    key_obj = key_map.get(key.lower(), key)
    
    start_time = time.monotonic()
    controller.press(key_obj)
    try:
        end_time = start_time + duration
        while time.monotonic() < end_time:
            if stop_check and stop_check():
                raise StopExecution("Stopped")
            time.sleep(0.01)  # Check every 10ms
    finally:
        controller.release(key_obj)


def _get_pynput_key(key: str):
    """Convert key string to pynput Key object."""
    from pynput.keyboard import Key as PynputKey, KeyCode
    
    key_map = {
        'shift': PynputKey.shift,
        'shift_l': PynputKey.shift,
        'shift_r': PynputKey.shift,
        'ctrl': PynputKey.ctrl,
        'ctrl_l': PynputKey.ctrl_l,
        'ctrl_r': PynputKey.ctrl_r,
        'alt': PynputKey.alt,
        'alt_l': PynputKey.alt_l,
        'alt_r': PynputKey.alt_r,
        'space': ' ',
        'enter': PynputKey.enter,
        'return': PynputKey.enter,
        'tab': PynputKey.tab,
        'backspace': PynputKey.backspace,
        'delete': PynputKey.delete,
        'esc': PynputKey.esc,
        'escape': PynputKey.esc,
        'up': PynputKey.up,
        'down': PynputKey.down,
        'left': PynputKey.left,
        'right': PynputKey.right,
        'home': PynputKey.home,
        'end': PynputKey.end,
        'pageup': PynputKey.page_up,
        'pagedown': PynputKey.page_down,
        'page_up': PynputKey.page_up,
        'page_down': PynputKey.page_down,
        'insert': PynputKey.insert,
        'pause': PynputKey.pause,
        'print_screen': PynputKey.print_screen,
        'scroll_lock': PynputKey.scroll_lock,
        'caps_lock': PynputKey.caps_lock,
        'num_lock': PynputKey.num_lock,
        'f1': PynputKey.f1,
        'f2': PynputKey.f2,
        'f3': PynputKey.f3,
        'f4': PynputKey.f4,
        'f5': PynputKey.f5,
        'f6': PynputKey.f6,
        'f7': PynputKey.f7,
        'f8': PynputKey.f8,
        'f9': PynputKey.f9,
        'f10': PynputKey.f10,
        'f11': PynputKey.f11,
        'f12': PynputKey.f12,
    }
    
    return key_map.get(key.lower(), key)


ARROW_KEY_MOVE_DISTANCE = 50

INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001

ULONG_PTR = getattr(wintypes, "ULONG_PTR", ctypes.c_size_t)

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]

class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("mi", MOUSEINPUT)]

def _mouse_move_relative(dx: int, dy: int) -> None:
    """Move mouse by relative amount (dx, dy)."""
    try:
        mouse_input = MOUSEINPUT(
            dx=dx,
            dy=dy,
            mouseData=0,
            dwFlags=MOUSEEVENTF_MOVE,
            time=0,
            dwExtraInfo=0,
        )
        input_struct = INPUT(type=INPUT_MOUSE, mi=mouse_input)
        sent = ctypes.windll.user32.SendInput(1, ctypes.byref(input_struct), ctypes.sizeof(INPUT))
        if sent == 0:
            raise OSError("SendInput failed")
    except Exception:
        current_x, current_y = pyautogui.position()
        pyautogui.moveTo(current_x + dx, current_y + dy)


def _normalize_arrow_key_name(key_name: str | None) -> str | None:
    if not key_name:
        return None
    name = str(key_name).lower()
    if name.startswith("key."):
        name = name[4:]
    return name


def _move_for_arrow_key(key_name: str | None) -> None:
    name = _normalize_arrow_key_name(key_name)
    if name == "right":
        _mouse_move_relative(ARROW_KEY_MOVE_DISTANCE, 0)
    elif name == "left":
        _mouse_move_relative(-ARROW_KEY_MOVE_DISTANCE, 0)
    elif name == "down":
        _mouse_move_relative(0, ARROW_KEY_MOVE_DISTANCE)
    elif name == "up":
        _mouse_move_relative(0, -ARROW_KEY_MOVE_DISTANCE)


def _mouse_down(button: str = "left") -> None:
    """Press mouse button."""
    pyautogui.mouseDown(button=button)


def _mouse_up(button: str = "left") -> None:
    """Release mouse button."""
    pyautogui.mouseUp(button=button)


def _mouse_click(x: int, y: int, clicks: int = 1, interval: float = 0, button: str = "left") -> None:
    """Click at position."""
    pyautogui.click(x=x, y=y, clicks=clicks, interval=interval, button=button)


def _mouse_drag(start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 0, button: str = "left") -> None:
    """Drag from start to end position."""
    pyautogui.moveTo(start_x, start_y)
    pyautogui.dragTo(end_x, end_y, duration=duration, button=button)


def _mouse_hold(x: int, y: int, duration: float, button: str = "left") -> None:
    """Hold mouse button at position for specified duration."""
    pyautogui.moveTo(x, y)
    _mouse_down(button)
    time.sleep(duration)
    _mouse_up(button)


def run_timeline(
    data: dict,
    stop_check: Callable[[], bool] | None = None,
    event_callback: Callable[[dict], None] | None = None,
    wait_for_events: bool = False,
) -> None:
    """Execute timeline using main thread scheduling + spawned worker threads for each event."""
    timeline = data.get("timeline", [])
    goods_template = data.get("goods_template")  # Get template from config
    
    if not timeline:
        raise ValueError("Timeline is empty")
    
    events: list[dict] = list(timeline)
    events.sort(key=lambda e: float(e.get("time", 0)))
    
    start_time = time.monotonic()
    
    # Track all pressed keys to clean up afterwards
    pressed_keys: dict[str, int] = {}  # key_name -> press_count
    pressed_keys_lock = threading.Lock()
    event_threads: list[threading.Thread] = []
    
    def run_event(event: dict) -> None:
        """Execute a single event in a worker thread."""
        event_type = event.get("type")
        
        if event_callback:
            event_callback(event)
        
        if event_type == "key_press":
            key_name = event.get("key")
            key_obj = _get_pynput_key(key_name)
            keyboard.Controller().press(key_obj)
            with pressed_keys_lock:
                pressed_keys[key_name] = pressed_keys.get(key_name, 0) + 1
            
            # For arrow keys, also execute mouse movement (direct execution during playback)
            _move_for_arrow_key(key_name)
        elif event_type == "key_release":
            key_name = event.get("key")
            key_obj = _get_pynput_key(key_name)
            keyboard.Controller().release(key_obj)
            with pressed_keys_lock:
                if key_name in pressed_keys and pressed_keys[key_name] > 0:
                    pressed_keys[key_name] -= 1
        elif event_type == "click":
            x_rel = event.get("x")
            y_rel = event.get("y")
            clicks = event.get("clicks", 1)
            button = event.get("button", "left")
            x, y = _coords_relative_to_absolute(float(x_rel), float(y_rel))
            _mouse_click(x, y, clicks=clicks, button=button)
        elif event_type == "hold":
            x_rel = event.get("x")
            y_rel = event.get("y")
            duration = event.get("duration", 0.3)
            button = event.get("button", "left")
            x, y = _coords_relative_to_absolute(float(x_rel), float(y_rel))
            _mouse_hold(x, y, duration=duration, button=button)
        elif event_type == "drag":
            start_x_rel = event.get("start_x")
            start_y_rel = event.get("start_y")
            end_x_rel = event.get("end_x")
            end_y_rel = event.get("end_y")
            duration = event.get("duration", 0)
            button = event.get("button", "left")
            start_x, start_y = _coords_relative_to_absolute(float(start_x_rel), float(start_y_rel))
            end_x, end_y = _coords_relative_to_absolute(float(end_x_rel), float(end_y_rel))
            _mouse_drag(start_x, start_y, end_x, end_y, duration=duration, button=button)
            _mouse_up(button)
        elif event_type == "config_action":
            # Execute a complete config file as atomic operation
            config_path_str = event.get("config")
            if config_path_str:
                try:
                    config_path = Path(config_path_str)
                    if not config_path.exists():
                        config_path = Path(__file__).parent / config_path_str
                    
                    if config_path.exists():
                        data = load_steps(config_path)
                        # Execute the entire config file
                        run_timeline(
                            data,
                            stop_check=stop_check,
                            event_callback=None,
                            wait_for_events=True,
                        )
                except Exception as e:
                    print(f"Error executing config_action: {e}")
        elif event_type == "goods_ocr":
            # Process goods image and auto-click the cheapest item
            from processors.goods_processor import (
                process_goods_image,
                analyze_goods_data,
                format_goods_ocr_items,
            )
            
            try:
                # Prioritize event-level template over global template
                template_path = None
                event_template = event.get("template")
                template_key = event_template or goods_template
                if template_key:
                    if template_key in {"gudi", "wuling"}:
                        template_path = template_key
                    else:
                        template_path = Path("templates") / template_key
                result = process_goods_image(template_path=template_path)
                logger = logging.getLogger("app")
                logger.info(
                    "goods_ocr result: template=%s",
                    result.get("template"),
                )
                for item_line in format_goods_ocr_items(result):
                    logger.info("goods_ocr item: %s", item_line)
                analysis = analyze_goods_data(result)
                if analysis:
                    time.sleep(0.3)
                    # Auto-click the cheapest item
                    pyautogui.click(analysis["center_x"], analysis["center_y"])
            except Exception as e:
                print(f"Error executing goods_ocr: {e}")
        elif event_type == "home_assist_ocr":
            # Home Assistant OCR - recognize template and click if confidence > 90%
            from processors.home_assistance_processor import process_home_assistance
            
            try:
                result = process_home_assistance()
                
                if result["success"]:
                    print(f"home_assist_ocr: {result['message']}")
                else:
                    print(f"home_assist_ocr: {result['message']}")
            except Exception as e:
                print(f"Error executing home_assist_ocr: {e}")
        elif event_type == "item_drag":
            try:
                from processors.backpack_processor import process_item_drag
                
                item_id = event.get("item_id")
                if not item_id:
                    print("item_drag: Missing item_id")
                else:
                    result = process_item_drag(item_id)
                    
                    if result.get("success"):
                        start = result["start"]
                        end = result["end"]
                        confidence = result.get("confidence", 0)
                        print(f"item_drag: {item_id} dragged from {start} to {end}, confidence={confidence:.2%}")
                    else:
                        error = result.get("error", "Unknown error")
                        print(f"item_drag: Failed - {error}")
            except Exception as e:
                print(f"Error executing item_drag: {e}")
        elif event_type == "qingbao_loop":
            from processors.qingbao_processor import run_qingbao_loop

            try:
                config_found = event.get("config_found")
                config_not_found = event.get("config_not_found")
                max_clicks = int(event.get("max_clicks", 5))
                max_recognitions = int(event.get("max_recognitions", 20))
                match_threshold = float(event.get("match_threshold", 0.7))

                if not config_found or not config_not_found:
                    raise ValueError("qingbao_loop requires config_found and config_not_found")

                run_qingbao_loop(
                    config_found=config_found,
                    config_not_found=config_not_found,
                    max_clicks=max_clicks,
                    max_recognitions=max_recognitions,
                    match_threshold=match_threshold,
                    stop_check=stop_check,
                )
            except Exception as e:
                print(f"Error executing qingbao_loop: {e}")
        elif event_type == "plants_loop":
            from processors.plants_processor import run_plants_harvest_loop

            try:
                max_iterations = int(event.get("max_iterations", 8))
                result = run_plants_harvest_loop(
                    stop_check=stop_check,
                    max_iterations=max_iterations,
                )
                print(f"plants_loop result: {result['message']}")
            except Exception as e:
                print(f"Error executing plants_loop: {e}")
        elif event_type == "clues_ocr":
            from processors.clues_processor import process_clues_placement

            try:
                confidence_threshold = float(event.get("confidence_threshold", 0.5))
                min_matches = int(event.get("min_matches", 10))
                
                result = process_clues_placement(
                    confidence_threshold=confidence_threshold,
                    min_matches=min_matches,
                    stop_check=stop_check,
                )
                
                print(f"clues_ocr result: {result['message']}")
            except Exception as e:
                print(f"Error executing clues_ocr: {e}")
        elif event_type == "receive_clue_ocr":
            from ocr import recognize_compare_two_templates

            try:
                template1 = event.get("template1", "clues/receive_all.png")
                template2 = event.get("template2", "clues/invite.png")
                min_matches = int(event.get("min_matches", 10))
                
                screenshot = pyautogui.screenshot()
                result = recognize_compare_two_templates(
                    screenshot,
                    template1,
                    template2,
                    min_matches=min_matches,
                )
                
                if result and result["success"] and result["winner"] == "template1":
                    # Click at the recognized position
                    center_x = result["center_x"]
                    center_y = result["center_y"]
                    print(f"receive_clue_ocr: Clicking at ({center_x}, {center_y})")
                    pyautogui.click(center_x, center_y)
                else:
                    print(f"receive_clue_ocr: {result['message'] if result else 'No match found'}")
            except Exception as e:
                print(f"Error executing receive_clue_ocr: {e}")
        elif event_type == "gift_choice_ocr":
            from ocr import recognize_compare_two_templates

            try:
                template1 = event.get("template1", "gifts/receive_gift.png")
                template2 = event.get("template2", "gifts/send_gift.png")
                min_matches = int(event.get("min_matches", 10))
                config_if_template1 = event.get("config_if_template1")
                config_if_template2 = event.get("config_if_template2")
                
                screenshot = pyautogui.screenshot()
                result = recognize_compare_two_templates(
                    screenshot,
                    template1,
                    template2,
                    min_matches=min_matches,
                )
                
                if result and result["winner"] == "template1":
                    # Template1 (receive_gift) wins, execute config_if_template1
                    print(f"gift_choice_ocr: {result['message']}, executing {config_if_template1}")
                    if config_if_template1:
                        config_path = Path(config_if_template1)
                        if config_path.exists():
                            steps = load_steps(config_path)
                            run_timeline(
                                steps,
                                stop_check=stop_check,
                                event_callback=event_callback,
                                wait_for_events=wait_for_events,
                            )
                        else:
                            print(f"gift_choice_ocr: Config not found: {config_path}")
                elif result and result["winner"] == "template2":
                    # Template2 (send_gift) wins, execute config_if_template2
                    print(f"gift_choice_ocr: {result['message']}, executing {config_if_template2}")
                    if config_if_template2:
                        config_path = Path(config_if_template2)
                        if config_path.exists():
                            steps = load_steps(config_path)
                            run_timeline(
                                steps,
                                stop_check=stop_check,
                                event_callback=event_callback,
                                wait_for_events=wait_for_events,
                            )
                        else:
                            print(f"gift_choice_ocr: Config not found: {config_path}")
                else:
                    print(f"gift_choice_ocr: No match found or comparison failed")
            except Exception as e:
                print(f"Error executing gift_choice_ocr: {e}")
        elif event_type == "collection_max_ocr":
            from ocr import recognize_compare_two_templates

            try:
                template_full = event.get("template_full", "collection_max.png")
                template_not_full = event.get("template_not_full", "collection_notmax.png")
                min_matches = int(event.get("min_matches", 10))

                screenshot = pyautogui.screenshot()
                result = recognize_compare_two_templates(
                    screenshot,
                    template_full,
                    template_not_full,
                    min_matches=min_matches,
                )

                is_full = False
                if result is not None:
                    full_conf = float(result.get("confidence1", 0.0))
                    not_full_conf = float(result.get("confidence2", 0.0))
                    is_full = full_conf > not_full_conf
                    print(
                        f"collection_max_ocr: full={full_conf:.1f}%, "
                        f"not_full={not_full_conf:.1f}%"
                    )
                else:
                    print("collection_max_ocr: Comparison failed")

                pyautogui.keyDown("esc")
                time.sleep(0.05)
                pyautogui.keyUp("esc")

                if not is_full:
                    pyautogui.keyDown("esc")
                    time.sleep(0.05)
                    pyautogui.keyUp("esc")
                    request_composite_break()
                    print("collection_max_ocr: Not full, requested composite stop")
                else:
                    print("collection_max_ocr: Full, continuing")
            except Exception as e:
                print(f"Error executing collection_max_ocr: {e}")
        elif event_type == "find_npc_ocr":
            from processors.npc_finder import find_npc_by_walking

            try:
                confidence_threshold = float(event.get("confidence_threshold", 0.5))
                min_matches = int(event.get("min_matches", 10))
                
                result = find_npc_by_walking(
                    confidence_threshold=confidence_threshold,
                    min_matches=min_matches,
                    max_steps=9,
                    stop_check=stop_check,
                )
                
                print(f"find_npc_ocr result: {result['message']}")
            except Exception as e:
                print(f"Error executing find_npc_ocr: {e}")

    
    # Main thread scheduling loop
    try:
        for event in events:
            if stop_check and stop_check():                raise StopExecution("Stopped")
            
            event_time = float(event.get("time", 0))
            target_time = start_time + event_time
            
            # Wait until the event's scheduled time
            while True:
                if stop_check and stop_check():
                    raise StopExecution("Stopped")
                now = time.monotonic()
                remaining = target_time - now
                if remaining <= 0:
                    break
                time.sleep(min(0.01, remaining))
            
            # Spawn worker thread to execute this event (non-blocking)
            event_thread = threading.Thread(target=run_event, args=(event,), daemon=True)
            event_thread.start()
            event_threads.append(event_thread)
    finally:
        if wait_for_events:
            # Wait for all event threads to finish before returning
            for event_thread in event_threads:
                event_thread.join()
        # Release all pressed keys to ensure no keys are stuck
        with pressed_keys_lock:
            for key_name, count in pressed_keys.items():
                if count > 0:
                    try:
                        key_obj = _get_pynput_key(key_name)
                        kb_ctrl = keyboard.Controller()
                        for _ in range(count):
                            kb_ctrl.release(key_obj)
                    except Exception:
                        pass
