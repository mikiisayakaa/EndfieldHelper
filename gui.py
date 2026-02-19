import json
import logging
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import sys
import os
import ctypes
from ctypes import wintypes

import pyautogui
from pynput import keyboard, mouse
from PIL import Image, ImageTk

from automation import Recorder, StopExecution, load_steps, run_step, save_steps
from goods_processor import process_goods_image, analyze_goods_data, format_goods_ocr_items
from i18n import I18n

# ===== Directional Mouse Control via Arrow Keys =====
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Fallbacks for older ctypes.wintypes
ULONG_PTR = getattr(wintypes, "ULONG_PTR", ctypes.c_size_t)
WPARAM = getattr(wintypes, "WPARAM", ctypes.c_size_t)
LPARAM = getattr(wintypes, "LPARAM", ctypes.c_ssize_t)
LRESULT = getattr(wintypes, "LRESULT", ctypes.c_ssize_t)
LPCWSTR = getattr(wintypes, "LPCWSTR", ctypes.c_wchar_p)
HMODULE = getattr(wintypes, "HMODULE", ctypes.c_void_p)

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
VK_LEFT = 0x25
VK_RIGHT = 0x27
VK_UP = 0x26
VK_DOWN = 0x28
VK_CONTROL = 0x11
MOD_NOREPEAT = 0x4000

HOTKEY_ID_UP = 10
HOTKEY_ID_DOWN = 11
HOTKEY_ID_LEFT = 12
HOTKEY_ID_RIGHT = 13

# Mouse input constants
INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001

MOUSE_MOVE_DISTANCE = 50  # Pixel distance per arrow key press

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

class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]

HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, WPARAM, LPARAM)

# WinAPI signatures
kernel32.GetModuleHandleW.argtypes = [LPCWSTR]
kernel32.GetModuleHandleW.restype = HMODULE
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, HMODULE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = HMODULE
user32.CallNextHookEx.argtypes = [HMODULE, ctypes.c_int, WPARAM, LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [HMODULE]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p, ctypes.c_int]
user32.SendInput.restype = wintypes.UINT
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short

_kbd_hook_handle_arrow = None
_kbd_hook_ref_arrow = None

def get_resource_path(relative_path: str) -> Path:
    """
    Get the path to a resource file.
    In development, returns the path relative to the script.
    In PyInstaller exe, returns the path in the _MEIPASS directory.
    """
    if hasattr(sys, '_MEIPASS'):
        # Running as compiled exe
        base_path = Path(sys._MEIPASS)
    else:
        # Running as script
        base_path = Path(__file__).parent
    return base_path / relative_path

# Configure logging for all application operations
logging.basicConfig(
    filename='endfield_helper.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)
app_logger = logging.getLogger('app')


def start_gui() -> int:
    app_logger.info("=" * 50)
    app_logger.info("Endfield Helper application started")
    app_logger.info("=" * 50)
    
    # Initialize internationalization (i18n) with default language English
    i18n = I18n(language="zh")
    
    root = tk.Tk()
    root.title(i18n.t("app_title"))
    root.resizable(False, False)
    root.attributes("-topmost", True)

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("Modern.TButton", padding=(10, 6), font=("Segoe UI", 9))

    # Set window icon from icon.png
    try:
        icon_path = get_resource_path("imgs/icon.png")
        if icon_path.exists():
            # Load image with PIL
            icon_image = Image.open(icon_path)
            # Convert to PhotoImage for tkinter
            photo_image = ImageTk.PhotoImage(icon_image)
            # Set the window icon
            root.tk.call('wm', 'iconphoto', root._w, photo_image)
    except Exception as e:
        app_logger.warning(f"Failed to load icon: {e}")

    def on_unmap(event: tk.Event) -> None:
        if root.state() == "iconic":
            root.attributes("-topmost", False)

    def on_map(event: tk.Event) -> None:
        if root.state() != "iconic":
            root.attributes("-topmost", True)

    root.bind("<Unmap>", on_unmap)
    root.bind("<Map>", on_map)

    def is_click_in_gui(x: int, y: int) -> bool:
        if not root.winfo_viewable():
            return False
        root.update_idletasks()
        left = root.winfo_rootx()
        top = root.winfo_rooty()
        right = left + root.winfo_width()
        bottom = top + root.winfo_height()
        return left <= x <= right and top <= y <= bottom

    recorder = Recorder(click_filter=is_click_in_gui)

    config_var = tk.StringVar(value="config.json")
    status_var = tk.StringVar(value=i18n.t("idle"))
    position_var = tk.StringVar(value="(0, 0)")
    click_hint_var = tk.StringVar(value="")
    goods_template_var = tk.StringVar(value="gudi")
    config_comment_var = tk.StringVar(value="")  # Config comments
    config_folder = None  # Store the selected config folder
    config_files = []  # Store the list of config files
    composite_configs = []  # Store the list of configs in composite mode
    running = False
    stop_event = threading.Event()
    idle_listener = None
    hotkey_listener = None
    goods_listener = None
    should_close = False

    config_menu = None
    
    # Store all UI elements that have text for language switching
    ui_elements = {}

    def update_mouse_position() -> None:
        try:
            x, y = pyautogui.position()
            position_var.set(f"({x}, {y})")
        except Exception:
            pass
        root.after(50, update_mouse_position)

    update_mouse_position()

    def on_idle_click(x: int, y: int, button: mouse.Button, pressed: bool) -> None:
        if pressed and not recorder.recording and not running:
            if not is_click_in_gui(x, y):
                click_hint_var.set("click")
                root.after(500, lambda: click_hint_var.set(""))

    def start_idle_listener() -> None:
        nonlocal idle_listener
        if idle_listener is None:
            idle_listener = mouse.Listener(on_click=on_idle_click)
            idle_listener.start()

    start_idle_listener()

    def update_ui_language() -> None:
        """Update all UI text to the current language"""
        for widget_id, (widget, key, is_button) in ui_elements.items():
            text = i18n.t(key)
            if is_button:
                widget.config(text=text)
            else:
                widget.config(text=text)
        if config_menu is not None:
            config_menu.entryconfig(0, label=i18n.t("open_in_editor"))
    
    def toggle_language() -> None:
        """Toggle between English and Chinese"""
        current_lang = i18n.get_language()
        new_lang = "zh" if current_lang == "en" else "en"
        i18n.set_language(new_lang)
        update_ui_language()
        root.title(i18n.t("app_title"))
        app_logger.info(f"Language switched to: {new_lang}")

    # ===== Arrow Key Mouse Movement Functions =====
    def _get_hinstance():
        handle = kernel32.GetModuleHandleW(None)
        if not handle:
            handle = kernel32.GetModuleHandleW(sys.executable)
        return handle

    def _send_mouse_move(dx: int, dy: int) -> None:
        """Send relative mouse movement using SendInput."""
        try:
            mouse_input = MOUSEINPUT(
                dx=dx,
                dy=dy,
                mouseData=0,
                dwFlags=MOUSEEVENTF_MOVE,
                time=0,
                dwExtraInfo=0
            )
            input_struct = INPUT(type=INPUT_MOUSE, mi=mouse_input)
            user32.SendInput(1, ctypes.byref(input_struct), ctypes.sizeof(INPUT))
        except Exception as e:
            app_logger.error(f"Failed to send mouse move: {e}")

    def _keyboard_proc_arrow(n_code, w_param, l_param):
        """Low-level keyboard hook for arrow keys."""
        if n_code == 0:
            try:
                info = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                is_key_down = w_param in (WM_KEYDOWN, WM_SYSKEYDOWN)
                is_key_up = w_param in (WM_KEYUP, WM_SYSKEYUP)
                
                # Determine which arrow key was pressed/released
                key_name = None
                dx, dy = 0, 0
                
                if info.vkCode == VK_RIGHT:
                    key_name = "right"
                    dx = MOUSE_MOVE_DISTANCE
                elif info.vkCode == VK_LEFT:
                    key_name = "left"
                    dx = -MOUSE_MOVE_DISTANCE
                elif info.vkCode == VK_DOWN:
                    key_name = "down"
                    dy = MOUSE_MOVE_DISTANCE
                elif info.vkCode == VK_UP:
                    key_name = "up"
                    dy = -MOUSE_MOVE_DISTANCE
                
                # Record key press/release events during recording
                if key_name:
                    if is_key_down:
                        # Check break code bit (bit 31 of flags) - if set, it's a key release
                        is_release = (info.flags & 0x80) != 0
                        if not is_release:
                            # Record key press during recording
                            try:
                                if recorder.recording:
                                    recorder.record_arrow_key_press(key_name)
                            except Exception as e:
                                app_logger.error(f"Failed to record arrow key press: {e}")
                            # Execute mouse move on key down
                            _send_mouse_move(dx, dy)
                    elif is_key_up:
                        # Record key release during recording
                        try:
                            if recorder.recording:
                                recorder.record_arrow_key_release(key_name)
                        except Exception as e:
                            app_logger.error(f"Failed to record arrow key release: {e}")
            except Exception as e:
                app_logger.error(f"Error in keyboard hook: {e}")
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    def _start_arrow_key_hook() -> None:
        """Start the low-level keyboard hook for arrow keys."""
        global _kbd_hook_handle_arrow, _kbd_hook_ref_arrow
        if _kbd_hook_handle_arrow is not None:
            return
        try:
            _kbd_hook_ref_arrow = HOOKPROC(_keyboard_proc_arrow)
            h_module = _get_hinstance()
            _kbd_hook_handle_arrow = user32.SetWindowsHookExW(WH_KEYBOARD_LL, _kbd_hook_ref_arrow, h_module, 0)
            if _kbd_hook_handle_arrow:
                app_logger.info("Arrow key hook installed successfully")
            else:
                app_logger.error("Failed to install arrow key hook")
        except Exception as e:
            app_logger.error(f"Failed to start arrow key hook: {e}")

    def _stop_arrow_key_hook() -> None:
        """Stop the low-level keyboard hook for arrow keys."""
        global _kbd_hook_handle_arrow, _kbd_hook_ref_arrow
        if _kbd_hook_handle_arrow is not None:
            try:
                user32.UnhookWindowsHookEx(_kbd_hook_handle_arrow)
                _kbd_hook_handle_arrow = None
                _kbd_hook_ref_arrow = None
                app_logger.info("Arrow key hook uninstalled")
            except Exception as e:
                app_logger.error(f"Failed to stop arrow key hook: {e}")

    def minimize_gui() -> None:
        root.attributes("-topmost", False)
        root.iconify()

    def show_gui() -> None:
        root.deiconify()
        root.attributes("-topmost", True)
        root.lift()

    def ui_call(func, *args) -> None:
        root.after(0, lambda: func(*args))

    def add_comment_field_to_config(config_path: Path) -> None:
        """Add comment field to a config file if it doesn't have one."""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Add comment field if it doesn't exist
            if "comment" not in data:
                data["comment"] = ""
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                app_logger.info(f"Added comment field to {config_path}")
        except Exception as e:
            app_logger.error(f"Failed to add comment field to {config_path}: {e}")

    def trim_stop_hotkey(steps: list[dict] | dict) -> list[dict] | dict:
        """Remove stop hotkey (Ctrl+X) from recorded steps."""
        if isinstance(steps, dict):
            # Timeline format - remove trailing key_release and key_press for Ctrl+X
            timeline = steps.get("timeline", [])
            if len(timeline) < 4:
                return steps
            
            # Check if last events are ctrl release, x release (reverse of ctrl press, x press)
            last = timeline[-1]
            
            # Find the Ctrl+X press events at the end and remove them
            idx = len(timeline) - 1
            while idx >= 0:
                event = timeline[idx]
                if event.get("type") == "key_release" and event.get("key") in ("ctrl", "ctrl_l", "ctrl_r", "x"):
                    idx -= 1
                elif event.get("type") == "key_press" and event.get("key") in ("ctrl", "ctrl_l", "ctrl_r", "x"):
                    idx -= 1
                else:
                    break
            
            # Only trim if we found at least 4 ctrl+x events (2 presses + 2 releases)
            if len(timeline) - idx - 1 >= 4:
                steps["timeline"] = timeline[:idx + 1]
            
            return steps
        else:
            # Legacy list format
            if len(steps) < 2:
                return steps
            last = steps[-1]
            prev = steps[-2]
            if (
                last.get("action") == "key"
                and last.get("key") == "x"
                and prev.get("action") == "key"
                and str(prev.get("key", "")).startswith("ctrl")
            ):
                return steps[:-2]
            return steps

    def add_to_composite(config_path: str) -> None:
        """Add a config to the composite list."""
        nonlocal composite_configs
        composite_configs.append(config_path)
        composite_listbox.insert(tk.END, Path(config_path).name)
        app_logger.info(f"Added to composite: {config_path}")

    def clear_composite_list() -> None:
        """Clear the composite config list."""
        nonlocal composite_configs
        composite_configs = []
        composite_listbox.delete(0, tk.END)
        app_logger.info("Cleared composite config list")

    def save_composite_config() -> None:
        """Save the composite config to a file."""
        config_path = Path(config_var.get().strip())
        if not config_path.name:
            messagebox.showerror("Error", "Please specify a config file name.")
            return
        
        if not composite_configs:
            messagebox.showerror("Error", "Composite list is empty.")
            return
        
        # Check if file exists and ask for overwrite confirmation
        if config_path.exists():
            overwrite = messagebox.askyesno(
                "Overwrite?",
                "Config already exists. Overwrite?",
            )
            if not overwrite:
                return
        
        composite_data = {
            "type": "composite",
            "configs": [{"config": str(cfg)} for cfg in composite_configs],
            "comment": comment_text.get("1.0", tk.END).rstrip()
        }
        
        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(composite_data, f, indent=2, ensure_ascii=False)
            status_var.set(f"Saved composite config with {len(composite_configs)} items")
            app_logger.info(f"Saved composite config to {config_path} with {len(composite_configs)} items")
            messagebox.showinfo("Success", f"Saved composite config with {len(composite_configs)} configs")
        except OSError as e:
            messagebox.showerror("Error", f"Failed to save composite config: {e}")
            app_logger.error(f"Failed to save composite config: {e}")

    def load_composite_config(config_path: Path) -> bool:
        """Load a composite config and populate the list."""
        nonlocal composite_configs
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if isinstance(data, dict) and data.get("type") == "composite":
                composite_configs = [item["config"] for item in data.get("configs", [])]
                # Load and display comment
                comment = data.get("comment", "")
                update_comment_text_from_var(comment)
                config_comment_var.set(comment)
                composite_listbox.delete(0, tk.END)
                for cfg in composite_configs:
                    composite_listbox.insert(tk.END, Path(cfg).name)
                app_logger.info(f"Loaded composite config from {config_path} with {len(composite_configs)} items")
                return True
            return False
        except Exception as e:
            app_logger.error(f"Failed to load composite config: {e}")
            return False

    def run_unified_config() -> None:
        """
        Unified config runner that auto-detects and executes:
        - Config files specified in config_var (handles any format: timeline, composite, or legacy)
        - composite_configs is only for list editing and saving, not for execution
        """
        nonlocal running
        if recorder.recording or running:
            return

        config_path = Path(config_var.get().strip())
        if not config_path.name:
            messagebox.showerror(i18n.t("error"), i18n.t("error_choose_config"))
            return
        if not config_path.exists():
            messagebox.showerror(i18n.t("error"), i18n.t("config_not_found"))
            return
        
        # Define recursive config executor (shared by both modes)
        def execute_config_recursive(
            config_path: Path | str,
            depth: int = 0,
            wait_for_timeline: bool = False,
        ) -> None:
            """Recursively execute a config that may contain nested composites."""
            indent = "  " * depth
            data = load_steps(config_path)
            
            if isinstance(data, dict) and "timeline" in data:
                # Timeline format
                from automation import run_timeline
                timeline = data.get("timeline", [])
                ui_call(append_log_line, f"{indent}Running timeline with {len(timeline)} events")
                
                def log_event(event: dict) -> None:
                    event_time = float(event.get("time", 0))
                    event_type = event.get("type")
                    if event_type == "key_press":
                        key_name = event.get("key", "?")
                        line = f"T{event_time:.3f}: key_press {key_name}"
                    elif event_type == "key_release":
                        key_name = event.get("key", "?")
                        line = f"T{event_time:.3f}: key_release {key_name}"
                    elif event_type == "click":
                        x = event.get("x")
                        y = event.get("y")
                        button = event.get("button", "left")
                        line = f"T{event_time:.3f}: click {button} ({x}, {y})"
                    elif event_type == "hold":
                        x = event.get("x")
                        y = event.get("y")
                        button = event.get("button", "left")
                        duration = event.get("duration", 0)
                        line = f"T{event_time:.3f}: hold {button} ({x}, {y}) {duration:.3f}s"
                    elif event_type == "drag":
                        start_x = event.get("start_x")
                        start_y = event.get("start_y")
                        end_x = event.get("end_x")
                        end_y = event.get("end_y")
                        duration = event.get("duration", 0)
                        button = event.get("button", "left")
                        line = f"T{event_time:.3f}: drag {button} ({start_x}, {start_y}) -> ({end_x}, {end_y}) {duration:.3f}s"
                    elif event_type == "goods_ocr":
                        line = f"T{event_time:.3f}: goods_ocr (capture, recognize, click cheapest)"
                    else:
                        line = f"T{event_time:.3f}: {event_type}"
                    ui_call(append_log_line, line)
                
                run_timeline(
                    data,
                    stop_check=stop_event.is_set,
                    event_callback=log_event,
                    wait_for_events=wait_for_timeline,
                )
            elif isinstance(data, dict) and data.get("type") == "composite":
                # Nested composite format
                composite_list = data.get("configs", [])
                ui_call(append_log_line, f"{indent}Running composite format with {len(composite_list)} nested configs")
                
                for sub_idx, item in enumerate(composite_list, 1):
                    if stop_event.is_set():
                        raise StopExecution()
                    
                    sub_config_path = item.get("config") if isinstance(item, dict) else item
                    if not sub_config_path:
                        continue
                    
                    ui_call(append_log_line, f"{indent}  [{sub_idx}/{len(composite_list)}] {Path(sub_config_path).name}")
                    execute_config_recursive(
                        Path(sub_config_path),
                        depth + 1,
                        wait_for_timeline=True,
                    )
            else:
                # Legacy format
                ui_call(append_log_line, f"{indent}Running legacy format with {len(data)} steps")
                for step in data:
                    if stop_event.is_set():
                        raise StopExecution()
                    run_step(step)

        log_text.config(state=tk.NORMAL)
        log_text.delete("1.0", tk.END)
        log_text.config(state=tk.DISABLED)

        stop_event.clear()
        running = True
        set_controls(recorder.recording, running)
        status_var.set("Loading config...")
        app_logger.info(f"Starting to run config: {config_path}")
        minimize_gui()

        def append_log_line(line: str) -> None:
            log_text.config(state=tk.NORMAL)
            log_text.insert(tk.END, f"{line}\n")
            log_text.see(tk.END)
            log_text.config(state=tk.DISABLED)
            app_logger.info(line)

        def finalize_run() -> None:
            nonlocal running
            running = False
            stop_event.clear()
            set_controls(recorder.recording, running)
            show_gui()

        def execute() -> None:
            try:
                pyautogui.FAILSAFE = True
                ui_call(status_var.set, "Running config...")
                execute_config_recursive(config_path)
                ui_call(status_var.set, "Run complete.")
                app_logger.info("Config execution completed successfully")
            except StopExecution:
                ui_call(status_var.set, "Run stopped.")
                app_logger.info("Config execution stopped by user")
            except (OSError, ValueError) as exc:
                ui_call(messagebox.showerror, "Error", f"Failed to run config: {exc}")
                ui_call(status_var.set, "Idle")
                app_logger.error(f"Failed to run config: {exc}", exc_info=True)
            finally:
                ui_call(finalize_run)

        threading.Thread(target=execute, daemon=True).start()

    def browse_config() -> None:
        path = filedialog.askopenfilename(
            title="Select config",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if path:
            # Save current comment before switching
            save_current_comment()
            
            config_path = Path(path)
            config_var.set(path)
            app_logger.info(f"Config file selected: {path}")
            
            # Ensure comment field exists
            add_comment_field_to_config(config_path)
            
            # Load and display config comment
            comment = load_config_comment(config_path)
            update_comment_text_from_var(comment)
            config_comment_var.set(comment)
            
            # Try to load as composite config
            if load_composite_config(config_path):
                # Switch to composite tab if it's a composite config
                notebook.select(1)  # Select composite tab (index 1)
                status_var.set(f"Loaded composite config with {len(composite_configs)} items")
    
    def load_config_folder_by_path(folder_path: Path) -> None:
        """Load config files from a specified folder path."""
        nonlocal config_folder, config_files
        if not folder_path.exists() or not folder_path.is_dir():
            return
        
        config_folder = folder_path
        # Load all .json files from the folder
        config_files = sorted([f.name for f in config_folder.glob("*.json")])
        # Add comment field to all configs
        for config_file in config_files:
            add_comment_field_to_config(config_folder / config_file)
        # Update the listbox
        config_listbox.delete(0, tk.END)
        for config_file in config_files:
            config_listbox.insert(tk.END, config_file)
        status_var.set(f"Loaded {len(config_files)} config(s) from folder")
        app_logger.info(f"Loaded {len(config_files)} config files from folder: {folder_path}")
    
    def browse_folder() -> None:
        """Browse and select a folder containing config files."""
        folder = filedialog.askdirectory(title="Select Config Folder")
        if folder:
            load_config_folder_by_path(Path(folder))
    
    def load_config_comment(config_path: Path) -> str:
        """Load comment from config file."""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get("comment", "")
        except Exception:
            return ""

    def on_config_select(event) -> None:
        """Handle config selection from listbox."""
        selection = config_listbox.curselection()
        if selection and config_folder:
            # Save current comment before switching
            save_current_comment()
            
            selected_file = config_listbox.get(selection[0])
            config_path = config_folder / selected_file
            config_var.set(str(config_path))
            # Load and display config comment
            comment = load_config_comment(config_path)
            update_comment_text_from_var(comment)
            config_comment_var.set(comment)
            app_logger.info(f"Config selected from list: {config_path}")
    
    def on_config_double_click(event) -> None:
        """Handle double-click on config list to add to composite."""
        selection = config_listbox.curselection()
        if selection and config_folder:
            selected_file = config_listbox.get(selection[0])
            config_path = config_folder / selected_file
            add_to_composite(str(config_path))
            status_var.set(f"Added {selected_file} to composite list")

    def open_selected_config_in_editor() -> None:
        """Open the selected config in the system default editor."""
        selection = config_listbox.curselection()
        if not selection or not config_folder:
            messagebox.showinfo(i18n.t("error"), i18n.t("config_not_chosen"))
            return
        selected_file = config_listbox.get(selection[0])
        config_path = config_folder / selected_file
        if not config_path.exists():
            messagebox.showerror(i18n.t("error"), i18n.t("config_not_found"))
            return
        try:
            os.startfile(str(config_path))
        except OSError as exc:
            messagebox.showerror(i18n.t("error"), i18n.t("error_open_editor", error=str(exc)))

    def on_config_right_click(event) -> None:
        """Show context menu for config list."""
        if config_listbox.size() == 0:
            return
        index = config_listbox.nearest(event.y)
        if index >= 0:
            config_listbox.selection_clear(0, tk.END)
            config_listbox.selection_set(index)
            config_listbox.activate(index)
        if config_menu is not None:
            config_menu.tk_popup(event.x_root, event.y_root)
            config_menu.grab_release()

    def on_composite_double_click(event) -> None:
        """Handle double-click on composite list to remove item."""
        selection = composite_listbox.curselection()
        if selection:
            idx = selection[0]
            removed = composite_configs.pop(idx)
            composite_listbox.delete(idx)
            app_logger.info(f"Removed from composite: {removed}")
            status_var.set(f"Removed {Path(removed).name} from composite list")
    
    def on_composite_delete_key(event) -> None:
        """Handle Delete key on composite list to remove item."""
        selection = composite_listbox.curselection()
        if selection:
            idx = selection[0]
            removed = composite_configs.pop(idx)
            composite_listbox.delete(idx)
            app_logger.info(f"Removed from composite: {removed}")
            status_var.set(f"Removed {Path(removed).name} from composite list")
    
    def move_composite_up() -> None:
        """Move selected composite item up."""
        selection = composite_listbox.curselection()
        if selection and selection[0] > 0:
            idx = selection[0]
            # Swap in list
            composite_configs[idx], composite_configs[idx-1] = composite_configs[idx-1], composite_configs[idx]
            # Update listbox
            composite_listbox.delete(idx)
            composite_listbox.insert(idx-1, Path(composite_configs[idx-1]).name)
            composite_listbox.selection_set(idx-1)
            app_logger.info(f"Moved up: {composite_configs[idx-1]}")
    
    def move_composite_down() -> None:
        """Move selected composite item down."""
        selection = composite_listbox.curselection()
        if selection and selection[0] < len(composite_configs) - 1:
            idx = selection[0]
            # Swap in list
            composite_configs[idx], composite_configs[idx+1] = composite_configs[idx+1], composite_configs[idx]
            # Update listbox
            composite_listbox.delete(idx)
            composite_listbox.insert(idx+1, Path(composite_configs[idx+1]).name)
            composite_listbox.selection_set(idx+1)
            app_logger.info(f"Moved down: {composite_configs[idx+1]}")

    def show_help() -> None:
        messagebox.showinfo(i18n.t("help_title"), i18n.t("help_content"))

    def set_controls(recording: bool, is_running: bool) -> None:
        start_button.config(
            state=tk.DISABLED if (recording or is_running) else tk.NORMAL
        )
        stop_button.config(state=tk.NORMAL if (recording or is_running) else tk.DISABLED)
        run_unified_button.config(state=tk.DISABLED if (recording or is_running) else tk.NORMAL)
        browse_config_button.config(
            state=tk.DISABLED if (recording or is_running) else tk.NORMAL
        )

    def start_recording() -> None:
        config_path = Path(config_var.get().strip())
        if not config_path.name:
            messagebox.showerror(i18n.t("error"), i18n.t("error_choose_config"))
            return
        app_logger.info(f"Starting recording to: {config_path}")
        if config_path.exists():
            overwrite = messagebox.askyesno(
                i18n.t("overwrite"),
                i18n.t("config_exists"),
            )
            if not overwrite:
                return
            try:
                save_steps(config_path, [])
            except OSError as exc:
                messagebox.showerror(i18n.t("error"), i18n.t("error_clear_config", error=str(exc)))
                return

        set_controls(True, running)
        status_var.set(i18n.t("starting_recording"))

        def begin() -> None:
            minimize_gui()
            recorder.start()
            app_logger.info("Recording started")
            status_var.set(i18n.t("recording_status"))

        root.after(1000, begin)

    def stop_recording() -> None:
        data = recorder.stop()
        config_path = Path(config_var.get().strip())
        if not config_path.name:
            messagebox.showerror(i18n.t("error"), i18n.t("error_choose_config"))
            set_controls(False, running)
            status_var.set(i18n.t("idle"))
            return
        data = trim_stop_hotkey(data)
        
        # Add comment to data (from text box, not var)
        if isinstance(data, dict):
            data["comment"] = comment_text.get("1.0", tk.END).rstrip()
        
        try:
            save_steps(config_path, data)
        except OSError as exc:
            messagebox.showerror(i18n.t("error"), i18n.t("error_save", error=str(exc)))
            app_logger.error(f"Failed to save recording: {exc}")
        else:
            # Count items for status message
            if isinstance(data, dict):
                step_count = len(data.get("timeline", []))
            else:
                step_count = len(data)
            status_var.set(i18n.t("recording_saved", count=step_count, path=config_path))
            app_logger.info(f"Recording stopped. Saved {step_count} steps to {config_path}")
        set_controls(False, running)
        show_gui()

    def stop_action() -> None:
        if running:
            stop_event.set()
            status_var.set("Stopping...")
            return
        if recorder.recording:
            stop_recording()

    padding = {"padx": 8, "pady": 6}

    # ===== LEFT COLUMN: Template Selection =====
    template_dir = get_resource_path("templates")
    group_templates = []
    if list(template_dir.glob("goods_gudi_*.png")):
        group_templates.append("gudi")
    if list(template_dir.glob("goods_wuling_*.png")):
        group_templates.append("wuling")
    available_templates = group_templates
    if not available_templates:
        available_templates = sorted([f.name for f in template_dir.glob("goods_template_*.png")])
    if available_templates:
        goods_template_var.set(available_templates[0])
    
    template_frame = tk.LabelFrame(root, text=i18n.t("goods_template"), padx=8, pady=4)
    ui_elements['template_frame'] = (template_frame, 'goods_template', False)
    template_frame.grid(row=0, column=0, rowspan=6, sticky="nsew", **padding)
    for template_name in available_templates:
        if template_name.startswith("goods_template_"):
            label = template_name.replace("goods_template_", "").replace(".png", "")
        else:
            label = template_name
        tk.Radiobutton(
            template_frame,
            text=label,
            variable=goods_template_var,
            value=template_name,
        ).pack(anchor=tk.W)

    # ===== MIDDLE COLUMN: Controls and Log =====
    config_frame = tk.Frame(root)
    config_frame.grid(row=0, column=1, sticky="we", **padding)
    config_label = tk.Label(config_frame, text=i18n.t("config"))
    ui_elements['config_label'] = (config_label, 'config', False)
    config_label.pack(side=tk.LEFT, padx=(0, 5))
    tk.Entry(config_frame, textvariable=config_var, width=35).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
    browse_config_button = ttk.Button(
        config_frame,
        text=i18n.t("open"),
        command=browse_config,
        width=8,
        style="Modern.TButton",
    )
    ui_elements['browse_config_button'] = (browse_config_button, 'open', True)
    browse_config_button.pack(side=tk.LEFT, padx=(0, 4))
    # Add unified Run Config button at row 0 level
    run_unified_button = ttk.Button(
        config_frame,
        text=i18n.t("run_config"),
        command=run_unified_config,
        width=10,
        style="Modern.TButton",
    )
    ui_elements['run_unified_button'] = (run_unified_button, 'run_config', True)
    run_unified_button.pack(side=tk.LEFT, padx=4)
    # Add Help button at row 0 level
    help_unified_button = ttk.Button(
        config_frame,
        text=i18n.t("help"),
        command=show_help,
        width=8,
        style="Modern.TButton",
    )
    ui_elements['help_unified_button'] = (help_unified_button, 'help', True)
    help_unified_button.pack(side=tk.LEFT, padx=(4, 0))

    # Comment text frame
    comment_label = tk.Label(root, text=i18n.t("comment"), font=("Arial", 9))
    ui_elements['comment_label'] = (comment_label, 'comment', False)
    comment_label.grid(row=1, column=1, sticky="w", **padding)
    
    comment_frame = tk.Frame(root)
    comment_frame.grid(row=2, column=1, sticky="nsew", **padding)
    comment_scrollbar = tk.Scrollbar(comment_frame, orient=tk.VERTICAL)
    comment_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    comment_text = tk.Text(
        comment_frame,
        height=3,
        yscrollcommand=comment_scrollbar.set,
    )
    comment_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    comment_scrollbar.config(command=comment_text.yview)
    def sync_comment_to_var(event=None) -> None:
        """Sync comment text to StringVar (strips whitespace on focus out)."""
        if event is None or event.type == '9':  # FocusOut event
            config_comment_var.set(comment_text.get("1.0", tk.END).rstrip())
    
    def update_comment_text_from_var(comment: str) -> None:
        """Update comment text box from StringVar (for config load)."""
        comment_text.config(state=tk.NORMAL)
        comment_text.delete("1.0", tk.END)
        comment_text.insert("1.0", comment)
        comment_text.config(state=tk.NORMAL)
    
    # Only sync on focus out to avoid interrupting input
    comment_text.bind("<FocusOut>", sync_comment_to_var)
    # Remove the trace binding to prevent auto-updates that interrupt typing
    # config_comment_var.trace("w", update_comment_text)

    # Notebook for two modes: Recording and Composite
    notebook = ttk.Notebook(root)
    notebook.grid(row=3, column=1, sticky="nsew", **padding)

    # ===== TAB 1: Recording Mode =====
    recording_tab = tk.Frame(notebook)
    notebook.add(recording_tab, text=i18n.t("recording"))

    # Button row - Start and Stop buttons only (Run Config moved to row 0)
    button_frame = tk.Frame(recording_tab)
    button_frame.pack(fill=tk.X, padx=8, pady=6)
    start_button = ttk.Button(
        button_frame,
        text=i18n.t("start_recording"),
        command=start_recording,
        width=12,
        style="Modern.TButton",
    )
    ui_elements['start_button'] = (start_button, 'start_recording', True)
    start_button.pack(side=tk.LEFT, padx=(0, 4))
    stop_button = ttk.Button(
        button_frame,
        text=i18n.t("stop"),
        command=stop_action,
        state=tk.DISABLED,
        width=8,
        style="Modern.TButton",
    )
    ui_elements['stop_button'] = (stop_button, 'stop', True)
    stop_button.pack(side=tk.LEFT, padx=4)

    # ===== TAB 2: Composite Mode =====
    composite_tab = tk.Frame(notebook)
    notebook.add(composite_tab, text=i18n.t("composite"))

    # Instructions
    instruction_label = tk.Label(
        composite_tab, 
        text=i18n.t("composite_instructions"),
        font=("Arial", 9),
        fg="gray"
    )
    ui_elements['instruction_label'] = (instruction_label, 'composite_instructions', False)
    instruction_label.pack(padx=8, pady=(6, 0))

    composite_button_frame = tk.Frame(composite_tab)
    composite_button_frame.pack(fill=tk.X, padx=8, pady=6)
    save_composite_button = ttk.Button(
        composite_button_frame,
        text=i18n.t("save_composite"),
        command=lambda: save_composite_config(),
        width=14,
        style="Modern.TButton",
    )
    ui_elements['save_composite_button'] = (save_composite_button, 'save_composite', True)
    save_composite_button.pack(side=tk.LEFT, padx=(0, 4))
    clear_composite_button = ttk.Button(
        composite_button_frame,
        text=i18n.t("clear"),
        command=lambda: clear_composite_list(),
        width=8,
        style="Modern.TButton",
    )
    ui_elements['clear_composite_button'] = (clear_composite_button, 'clear', True)
    clear_composite_button.pack(side=tk.LEFT, padx=(4, 0))

    composite_list_frame = tk.LabelFrame(composite_tab, text=i18n.t("composite_config_list"), padx=4, pady=4)
    ui_elements['composite_list_frame'] = (composite_list_frame, 'composite_config_list', False)
    composite_list_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 6))
    
    composite_list_scrollbar = tk.Scrollbar(composite_list_frame, orient=tk.VERTICAL)
    composite_list_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    # Add up/down buttons frame
    composite_buttons_side = tk.Frame(composite_list_frame)
    composite_buttons_side.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 2))
    up_button = ttk.Button(
        composite_buttons_side,
        text=i18n.t("up"),
        command=move_composite_up,
        width=2,
        style="Modern.TButton",
    )
    ui_elements['up_button'] = (up_button, 'up', True)
    up_button.pack(pady=(0, 2))
    down_button = ttk.Button(
        composite_buttons_side,
        text=i18n.t("down"),
        command=move_composite_down,
        width=2,
        style="Modern.TButton",
    )
    ui_elements['down_button'] = (down_button, 'down', True)
    down_button.pack()
    
    composite_listbox = tk.Listbox(
        composite_list_frame,
        height=8,
        yscrollcommand=composite_list_scrollbar.set,
    )
    composite_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    composite_list_scrollbar.config(command=composite_listbox.yview)

    log_frame = tk.Frame(root)
    log_frame.grid(row=4, column=1, sticky="nsew", **padding)
    log_scrollbar = tk.Scrollbar(log_frame, orient=tk.VERTICAL)
    log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    log_text = tk.Text(
        log_frame,
        width=55,
        height=12,
        state=tk.DISABLED,
        yscrollcommand=log_scrollbar.set,
    )
    log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    log_scrollbar.config(command=log_text.yview)

    status_frame = tk.Frame(root)
    status_frame.grid(row=5, column=1, sticky="we", **padding)
    tk.Label(status_frame, textvariable=status_var).pack(side=tk.LEFT)
    tk.Label(status_frame, textvariable=position_var).pack(side=tk.RIGHT)
    tk.Label(status_frame, textvariable=click_hint_var, fg="red", width=6).pack(side=tk.RIGHT)

    # ===== RIGHT COLUMN: Config List =====
    top_right_frame = tk.Frame(root)
    top_right_frame.grid(row=0, column=2, sticky="we", **padding)
    top_right_frame.grid_columnconfigure(0, weight=1)

    browse_folder_button = ttk.Button(
        top_right_frame,
        text=i18n.t("open_folder"),
        command=browse_folder,
        style="Modern.TButton",
    )
    ui_elements['browse_folder_button'] = (browse_folder_button, 'open_folder', True)
    browse_folder_button.pack(side=tk.LEFT, fill=tk.X, expand=True)

    # Language toggle button
    language_button = ttk.Button(
        top_right_frame,
        text=i18n.t("toggle_language"),
        command=toggle_language,
        width=8,
        style="Modern.TButton",
    )
    ui_elements['language_button'] = (language_button, 'toggle_language', True)
    language_button.pack(side=tk.RIGHT, padx=(6, 0))

    config_list_frame = tk.LabelFrame(root, text=i18n.t("config_list"), padx=4, pady=4)
    ui_elements['config_list_frame'] = (config_list_frame, 'config_list', False)
    config_list_frame.grid(row=1, column=2, rowspan=5, sticky="nsew", **padding)
    config_list_scrollbar = tk.Scrollbar(config_list_frame, orient=tk.VERTICAL)
    config_list_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    config_listbox = tk.Listbox(
        config_list_frame,
        width=25,
        height=20,
        yscrollcommand=config_list_scrollbar.set,
    )
    config_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    config_list_scrollbar.config(command=config_listbox.yview)
    config_listbox.bind("<<ListboxSelect>>", on_config_select)
    config_listbox.bind("<Double-Button-1>", on_config_double_click)
    config_listbox.bind("<Button-3>", on_config_right_click)

    config_menu = tk.Menu(root, tearoff=0)
    config_menu.add_command(label=i18n.t("open_in_editor"), command=open_selected_config_in_editor)

    # Bind events to composite listbox
    composite_listbox.bind("<Double-Button-1>", on_composite_double_click)
    composite_listbox.bind("<Delete>", on_composite_delete_key)

    def on_hotkey_stop() -> None:
        if running:
            stop_event.set()
            status_var.set("Stopping...")
            return
        if recorder.recording:
            stop_recording()

    def on_goods_capture() -> None:
        template_value = goods_template_var.get()
        if template_value in {"gudi", "wuling"}:
            template_path = template_value
        else:
            template_path = get_resource_path("templates") / template_value
        
        if recorder.recording:
            # Add goods_ocr event to timeline with template info
            recorder._add_event("goods_ocr", template=goods_template_var.get())
            status_var.set("Goods OCR step recorded")
            app_logger.info(f"Recorded goods_ocr step with template: {goods_template_var.get()}")
            
            # Now execute the goods_ocr operation immediately
            # Set flag to skip recording all internal operations
            def execute_goods_capture() -> None:
                try:
                    # Disable recording of all internal operations
                    recorder._skip_recording = True
                    
                    time.sleep(0.3)
                    result = process_goods_image(save_screenshot=False, template_path=template_path)
                    app_logger.info(
                        "goods_ocr result: template=%s region=%s cols=%s rows=%s",
                        result.get("template"),
                        result.get("region"),
                        result.get("cols"),
                        result.get("rows"),
                    )
                    for item_line in format_goods_ocr_items(result):
                        app_logger.info("goods_ocr item: %s", item_line)
                    
                    # Analyze goods data and auto-click the cheapest item
                    analysis = analyze_goods_data(result, cols=result.get("cols", 7), rows=result.get("rows", 2))
                    if analysis:
                        time.sleep(0.1)
                        # Auto-click the cheapest item - this and any related ops won't be recorded
                        pyautogui.click(analysis["center_x"], analysis["center_y"])
                    else:
                        ui_call(lambda: status_var.set("No valid goods found (no green arrows)"))
                finally:
                    # Re-enable recording
                    recorder._skip_recording = False
            
            threading.Thread(target=execute_goods_capture, daemon=True).start()
            return

        minimize_gui()
        status_var.set("Capturing goods...")
        app_logger.info("Starting goods capture...")

        def process() -> None:
            try:
                time.sleep(0.8)
                result = process_goods_image(save_screenshot=False, template_path=template_path)
                app_logger.info(f"Goods processing result: {json.dumps(result, ensure_ascii=False)}")
                app_logger.info(
                    "goods_ocr result: template=%s region=%s cols=%s rows=%s",
                    result.get("template"),
                    result.get("region"),
                    result.get("cols"),
                    result.get("rows"),
                )
                for item_line in format_goods_ocr_items(result):
                    app_logger.info("goods_ocr item: %s", item_line)
                
                # Analyze goods data and auto-click the cheapest item
                analysis = analyze_goods_data(result, cols=result.get("cols", 7), rows=result.get("rows", 2))
                if analysis:
                    app_logger.info(f"Found cheapest: Row {analysis['row']}, Col {analysis['col']} ({analysis['percent']})")
                    ui_call(lambda: status_var.set(f"Found cheapest: Row {analysis['row']}, Col {analysis['col']} ({analysis['percent']}) - Clicking..."))
                    time.sleep(0.3)
                    # Auto-click the cheapest item
                    pyautogui.click(analysis["center_x"], analysis["center_y"])
                    app_logger.info(f"Clicked cheapest item at ({analysis['center_x']}, {analysis['center_y']})")
                    ui_call(lambda: status_var.set(f"Clicked cheapest item at ({analysis['center_x']}, {analysis['center_y']})"))
                else:
                    app_logger.warning("No valid goods found (no green arrows)")
                    ui_call(lambda: status_var.set("No valid goods found (no green arrows)"))
            except Exception as e:
                app_logger.error(f"Error processing goods: {e}", exc_info=True)
                ui_call(lambda: status_var.set("Error processing goods"))
            finally:
                ui_call(show_gui)

        threading.Thread(target=process, daemon=True).start()

    def on_home_assist_ocr() -> None:
        """
        Home Assistant OCR - screenshot recognition.
        Recognize templates/home_use_assistance in full screenshot.
        If confidence > 90%, click twice with 0.5s interval.
        """
        if recorder.recording:
            # During recording, add home_assist_ocr event to timeline
            recorder._add_event("home_assist_ocr")
            status_var.set("Home Assist OCR step recorded")
            app_logger.info("Recorded home_assist_ocr step")
            
            # Execute the home_assist_ocr operation immediately (inline)
            def execute_home_assist() -> None:
                try:
                    # Disable recording of all internal operations
                    recorder._skip_recording = True
                    
                    time.sleep(0.3)
                    # Take full screenshot
                    screenshot = pyautogui.screenshot()
                    
                    # Recognize template: templates/home_use_assistance
                    from ocr import recognize_template
                    result = recognize_template(screenshot, "home_use_assistance.png")
                    
                    if result and result['confidence'] > 90:
                        x, y = result['x'], result['y']
                        app_logger.info(f"Template recognized with {result['confidence']:.1f}% confidence, clicking at ({x}, {y})")
                        
                        # Click twice with 0.5s interval
                        pyautogui.click(x, y)
                        time.sleep(0.5)
                        pyautogui.click(x, y)
                        status_var.set(f"Home Assist: Clicked at ({x}, {y})")
                    else:
                        confidence = result['confidence'] if result else 0
                        app_logger.info(f"Template not recognized (confidence: {confidence:.1f}%)")
                        status_var.set(f"Home Assist: Confidence too low ({confidence:.1f}%)")
                finally:
                    # Re-enable recording
                    recorder._skip_recording = False
            
            threading.Thread(target=execute_home_assist, daemon=True).start()
            return
        
        # In IDLE state, execute directly
        minimize_gui()
        status_var.set("Home Assist: Capturing screenshot...")
        app_logger.info("Starting home assist OCR...")
        
        def process() -> None:
            try:
                time.sleep(0.8)
                # Take full screenshot
                screenshot = pyautogui.screenshot()
                
                # Recognize template: templates/home_use_assistance
                from ocr import recognize_template
                result = recognize_template(screenshot, "home_use_assistance.png")
                
                if result and result['confidence'] > 90:
                    x, y = result['x'], result['y']
                    app_logger.info(f"Template recognized with {result['confidence']:.1f}% confidence, clicking at ({x}, {y})")
                    
                    # Click twice with 0.5s interval
                    pyautogui.click(x, y)
                    time.sleep(0.5)
                    pyautogui.click(x, y)
                    ui_call(lambda: status_var.set(f"Home Assist: Clicked at ({x}, {y})"))
                else:
                    confidence = result['confidence'] if result else 0
                    app_logger.info(f"Template not recognized (confidence: {confidence:.1f}%)")
                    ui_call(lambda: status_var.set(f"Home Assist: Confidence too low ({confidence:.1f}%)"))
            except Exception as e:
                app_logger.error(f"Error in home assist OCR: {e}", exc_info=True)
                ui_call(lambda: status_var.set("Home Assist: Error"))
            finally:
                ui_call(show_gui)
        
        threading.Thread(target=process, daemon=True).start()

    def on_qingbao_hotkey() -> None:
        config_path = get_resource_path("configs/情报循环.json")
        if not config_path.exists():
            app_logger.error(f"Qingbao loop config not found: {config_path}")
            ui_call(messagebox.showerror, "Error", f"Config not found: {config_path}")
            return

        if recorder.recording:
            from automation import load_steps
            from qingbao_processor import run_qingbao_loop

            params = {
                "config_found": "configs/情报访问.json",
                "config_not_found": "configs/好友列表下滑.json",
                "max_clicks": 5,
                "max_recognitions": 20,
                "match_threshold": 0.7,
            }

            try:
                data = load_steps(config_path)
                if isinstance(data, list) and data:
                    step = data[0]
                    if step.get("action") == "qingbao_loop":
                        params.update(
                            {
                                "config_found": step.get("config_found", params["config_found"]),
                                "config_not_found": step.get("config_not_found", params["config_not_found"]),
                                "max_clicks": int(step.get("max_clicks", params["max_clicks"])),
                                "max_recognitions": int(step.get("max_recognitions", params["max_recognitions"])),
                                "match_threshold": float(step.get("match_threshold", params["match_threshold"])),
                            }
                        )
            except Exception as exc:
                app_logger.error(f"Failed to load qingbao params: {exc}")

            recorder._add_event("qingbao_loop", **params)
            status_var.set("Qingbao loop step recorded")
            app_logger.info("Recorded qingbao_loop step")

            def execute_qingbao_loop() -> None:
                try:
                    recorder._skip_recording = True
                    run_qingbao_loop(**params)
                finally:
                    recorder._skip_recording = False

            threading.Thread(target=execute_qingbao_loop, daemon=True).start()
            return

        config_var.set(str(config_path))
        app_logger.info(f"Hotkey qingbao loop: {config_path}")
        run_unified_config()

    def start_hotkey_listener() -> None:
        nonlocal hotkey_listener, goods_listener
        if hotkey_listener is None:
            hotkey_listener = keyboard.GlobalHotKeys(
                {"<ctrl>+x": lambda: ui_call(on_hotkey_stop)}
            )
            hotkey_listener.start()
        if goods_listener is None:
            goods_listener = keyboard.GlobalHotKeys(
                {
                    "<ctrl>+<shift>+s": lambda: ui_call(on_goods_capture),
                    "<ctrl>+<shift>+p": lambda: ui_call(on_home_assist_ocr),
                    "<ctrl>+<shift>+a": lambda: ui_call(on_qingbao_hotkey)
                }
            )
            goods_listener.start()
        # Start the arrow key hook for mouse movement
        _start_arrow_key_hook()

    def save_current_comment() -> None:
        """Save the current comment to the config file."""
        config_path_str = config_var.get().strip()
        if not config_path_str:
            return
        
        config_path = Path(config_path_str)
        if not config_path.exists():
            return
        
        # Get current comment from text box
        current_comment = comment_text.get("1.0", tk.END).rstrip()
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Only save if comment has changed
            if data.get("comment") != current_comment:
                data["comment"] = current_comment
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                app_logger.info(f"Saved comment to {config_path}")
        except Exception as e:
            app_logger.error(f"Failed to save comment: {e}")

    def on_window_close() -> None:
        nonlocal should_close
        # Save current comment before closing
        save_current_comment()
        app_logger.info("Saving current comment before close")
        should_close = True
        if hotkey_listener:
            hotkey_listener.stop()
        if goods_listener:
            goods_listener.stop()
        if idle_listener:
            idle_listener.stop()
        # Stop the arrow key hook
        _stop_arrow_key_hook()
        root.destroy()

    start_hotkey_listener()
    # Auto-load configs folder on startup
    configs_folder = Path("configs")
    if configs_folder.exists() and configs_folder.is_dir():
        load_config_folder_by_path(configs_folder)
    root.protocol("WM_DELETE_WINDOW", on_window_close)
    app_logger.info("GUI initialized, entering main loop")
    root.mainloop()
    app_logger.info("Application closed")
    app_logger.info("=" * 50)
    return 0
