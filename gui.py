import json
import logging
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import sys
import webbrowser
import os
import ctypes
import queue
from ctypes import wintypes

import pyautogui
from pynput import keyboard, mouse
from PIL import Image, ImageTk

from automation import Recorder, StopExecution, load_steps, save_steps
from goods_processor import process_goods_image, analyze_goods_data
from home_assistance_processor import process_home_assistance
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
LLKHF_INJECTED = 0x10

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
    root.resizable(True, True)
    root.attributes("-topmost", True)
    root.withdraw()
    root.grid_columnconfigure(0, weight=4, uniform="main_columns")
    root.grid_columnconfigure(1, weight=1, uniform="main_columns")
    root.grid_rowconfigure(3, weight=1)
    root.grid_rowconfigure(4, weight=1)

    def _sync_root_column_sizes(event=None) -> None:
        width = root.winfo_width()
        if width <= 1:
            return
        col0 = int(width * 0.8)
        col1 = max(1, width - col0)
        root.grid_columnconfigure(0, minsize=col0)
        root.grid_columnconfigure(1, minsize=col1)

    root.bind("<Configure>", _sync_root_column_sizes)
    root.after(0, _sync_root_column_sizes)

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("Modern.TButton", padding=(10, 6), font=("Segoe UI", 9))
    style.configure("Treeview", rowheight=25)  # Increase row height for better text display

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
    config_comment_var = tk.StringVar(value="")  # Config comments
    config_folder = None  # Store the selected config folder
    config_files = []  # Store the list of config files
    composite_configs = []  # Store the list of configs in composite mode
    edit_data = None  # Store the currently edited config data (dict or list)
    edit_config_type = None  # Store the type: 'composite', 'timeline', or 'legacy'
    re_recording_step_index = None  # Track which step is being re-recorded
    re_recording_mode = None  # Track re-recording mode: 're-record', 'insert-above', 'insert-below'
    
    running = False
    stop_event = threading.Event()
    idle_listener = None
    hotkey_listener = None
    should_close = False
    arrow_event_queue: queue.Queue = queue.Queue(maxsize=512)
    arrow_worker_thread = None

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
            # Update other menu items (keeping English for now as they're standard commands)
            config_menu.entryconfig(2, label="Cut" if i18n.get_language() == "en" else "剪切")
            config_menu.entryconfig(3, label="Copy" if i18n.get_language() == "en" else "复制")
            config_menu.entryconfig(4, label="Paste" if i18n.get_language() == "en" else "粘贴")
            config_menu.entryconfig(6, label="New Folder" if i18n.get_language() == "en" else "新建文件夹")
            config_menu.entryconfig(8, label="Delete" if i18n.get_language() == "en" else "删除")
    
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
            pass

    def _enqueue_arrow_event(key_name: str, is_key_down: bool, is_key_up: bool, dx: int, dy: int) -> None:
        try:
            arrow_event_queue.put_nowait((key_name, is_key_down, is_key_up, dx, dy))
        except Exception:
            pass

    def _arrow_key_worker() -> None:
        while True:
            item = arrow_event_queue.get()
            if item is None:
                break
            key_name, is_key_down, is_key_up, dx, dy = item

            if is_key_down:
                try:
                    if recorder.recording:
                        recorder.record_arrow_key_press(key_name)
                except Exception:
                    pass
                _send_mouse_move(dx, dy)
            elif is_key_up:
                try:
                    if recorder.recording:
                        recorder.record_arrow_key_release(key_name)
                except Exception:
                    pass

    def _start_arrow_worker() -> None:
        nonlocal arrow_worker_thread
        if arrow_worker_thread is not None:
            return
        arrow_worker_thread = threading.Thread(target=_arrow_key_worker, daemon=True)
        arrow_worker_thread.start()

    def _stop_arrow_worker() -> None:
        nonlocal arrow_worker_thread
        if arrow_worker_thread is None:
            return
        arrow_event_queue.put(None)
        arrow_worker_thread.join(timeout=1.0)
        arrow_worker_thread = None

    def _keyboard_proc_arrow(n_code, w_param, l_param):
        """Low-level keyboard hook for arrow keys."""
        if n_code == 0:
            try:
                info = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if info.flags & LLKHF_INJECTED:
                    return user32.CallNextHookEx(None, n_code, w_param, l_param)

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

                if key_name:
                    if is_key_down:
                        # Check break code bit (bit 31 of flags) - if set, it's a key release
                        is_release = (info.flags & 0x80) != 0
                        if not is_release:
                            _enqueue_arrow_event(key_name, True, False, dx, dy)
                    elif is_key_up:
                        _enqueue_arrow_event(key_name, False, True, dx, dy)
            except Exception:
                pass
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
                
                # Wait 0.5s at the start of top-level timeline
                if depth == 0:
                    time.sleep(0.5)
                
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
                
                # Wait 0.5s at the start of top-level composite
                if depth == 0:
                    time.sleep(0.5)
                
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
            time.sleep(0.5)
            show_gui()

        def execute() -> None:
            try:
                pyautogui.FAILSAFE = True
                ui_call(status_var.set, "Running config...")
                execute_config_recursive(config_path, wait_for_timeline=True)
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
            
            # Refresh edit view to show the loaded config
            refresh_edit_view()
    
    def load_config_folder_by_path(folder_path: Path) -> None:
        """Load config files from a specified folder path recursively into tree."""
        nonlocal config_folder
        if not folder_path.exists() or not folder_path.is_dir():
            return
        
        config_folder = folder_path
        # Clear the tree
        for item in config_tree.get_children():
            config_tree.delete(item)
        
        # Recursively load folder structure
        def add_folder_to_tree(parent_id: str, folder: Path) -> None:
            try:
                items = sorted(folder.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
                for item in items:
                    if item.is_dir():
                        # Add folder
                        folder_id = config_tree.insert(parent_id, 'end', text=item.name, 
                                                      values=(str(item), 'folder'), 
                                                      tags=('folder',))
                        # Recursively add contents
                        add_folder_to_tree(folder_id, item)
                    elif item.suffix == '.json':
                        # Add JSON file
                        add_comment_field_to_config(item)
                        config_tree.insert(parent_id, 'end', text=item.name, 
                                         values=(str(item), 'file'),
                                         tags=('file',))
            except PermissionError:
                pass
        
        add_folder_to_tree('', folder_path)
        
        # Count files
        file_count = sum(1 for _ in folder_path.rglob('*.json'))
        status_var.set(f"Loaded {file_count} config(s) from folder")
        app_logger.info(f"Loaded config files from folder: {folder_path}")
    
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
        """Handle config selection from tree."""
        selection = config_tree.selection()
        if selection and config_folder:
            item_id = selection[0]
            item_values = config_tree.item(item_id, 'values')
            
            if len(item_values) >= 2 and item_values[1] == 'file':
                # Save current comment before switching
                save_current_comment()
                
                config_path = Path(item_values[0])
                config_var.set(str(config_path))
                # Load and display config comment
                comment = load_config_comment(config_path)
                update_comment_text_from_var(comment)
                config_comment_var.set(comment)
                app_logger.info(f"Config selected from list: {config_path}")
                
                # Refresh edit view to show the selected config
                refresh_edit_view()
    
    def on_config_double_click(event) -> None:
        """Handle double-click on config tree: toggle folder or add file to composite."""
        selection = config_tree.selection()
        if not selection:
            return
        
        item_id = selection[0]
        item_values = config_tree.item(item_id, 'values')
        
        if len(item_values) >= 2:
            if item_values[1] == 'folder':
                # Toggle folder open/close
                if config_tree.item(item_id, 'open'):
                    config_tree.item(item_id, open=False)
                else:
                    config_tree.item(item_id, open=True)
            elif item_values[1] == 'file':
                # Add to composite
                config_path = Path(item_values[0])
                add_to_composite(str(config_path))
                status_var.set(f"Added {config_path.name} to composite list")

    def open_selected_config_in_editor() -> None:
        """Open the selected config in the system default editor."""
        selection = config_tree.selection()
        if not selection:
            messagebox.showinfo(i18n.t("error"), i18n.t("config_not_chosen"))
            return
        
        item_id = selection[0]
        item_values = config_tree.item(item_id, 'values')
        
        if len(item_values) >= 2 and item_values[1] == 'file':
            config_path = Path(item_values[0])
            if not config_path.exists():
                messagebox.showerror(i18n.t("error"), i18n.t("config_not_found"))
                return
            try:
                os.startfile(str(config_path))
            except OSError as exc:
                messagebox.showerror(i18n.t("error"), i18n.t("error_open_editor", error=str(exc)))
        elif len(item_values) >= 2 and item_values[1] == 'folder':
            # Open folder in explorer
            folder_path = Path(item_values[0])
            try:
                os.startfile(str(folder_path))
            except OSError as exc:
                messagebox.showerror(i18n.t("error"), str(exc))

    # Clipboard for cut/copy operations
    clipboard_item = {'path': None, 'operation': None}  # operation: 'cut' or 'copy'
    
    def delete_selected_config() -> None:
        """Delete selected file or folder."""
        selection = config_tree.selection()
        if not selection:
            return
        
        item_id = selection[0]
        item_values = config_tree.item(item_id, 'values')
        
        if len(item_values) >= 2:
            path = Path(item_values[0])
            item_type = item_values[1]
            
            # Confirm deletion
            msg = f"Delete {item_type} '{path.name}'?"
            if item_type == 'folder':
                msg += "\n\nThis will delete the folder and all its contents!"
            
            if messagebox.askyesno("Confirm Delete", msg):
                try:
                    if item_type == 'folder':
                        import shutil
                        shutil.rmtree(path)
                    else:
                        path.unlink()
                    
                    # Remove from tree
                    config_tree.delete(item_id)
                    status_var.set(f"Deleted {path.name}")
                    app_logger.info(f"Deleted: {path}")
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to delete: {e}")
                    app_logger.error(f"Failed to delete {path}: {e}")
    
    def cut_selected_config() -> None:
        """Cut selected file or folder."""
        selection = config_tree.selection()
        if not selection:
            return
        
        item_id = selection[0]
        item_values = config_tree.item(item_id, 'values')
        
        if len(item_values) >= 2:
            clipboard_item['path'] = Path(item_values[0])
            clipboard_item['operation'] = 'cut'
            status_var.set(f"Cut: {clipboard_item['path'].name}")
    
    def copy_selected_config() -> None:
        """Copy selected file or folder."""
        selection = config_tree.selection()
        if not selection:
            return
        
        item_id = selection[0]
        item_values = config_tree.item(item_id, 'values')
        
        if len(item_values) >= 2:
            clipboard_item['path'] = Path(item_values[0])
            clipboard_item['operation'] = 'copy'
            status_var.set(f"Copied: {clipboard_item['path'].name}")
    
    def paste_config() -> None:
        """Paste cut/copied file or folder."""
        if not clipboard_item['path'] or not clipboard_item['operation']:
            return
        
        selection = config_tree.selection()
        target_folder = config_folder
        
        # Determine target folder
        if selection:
            item_id = selection[0]
            item_values = config_tree.item(item_id, 'values')
            if len(item_values) >= 2:
                path = Path(item_values[0])
                if item_values[1] == 'folder':
                    target_folder = path
                else:
                    target_folder = path.parent
        
        source = clipboard_item['path']
        dest = target_folder / source.name
        
        # Handle name conflict
        if dest.exists():
            base_name = source.stem
            ext = source.suffix
            counter = 1
            while dest.exists():
                if source.is_dir():
                    dest = target_folder / f"{source.name}_{counter}"
                else:
                    dest = target_folder / f"{base_name}_{counter}{ext}"
                counter += 1
        
        try:
            import shutil
            if clipboard_item['operation'] == 'cut':
                shutil.move(str(source), str(dest))
                status_var.set(f"Moved to {target_folder.name}")
            else:  # copy
                if source.is_dir():
                    shutil.copytree(str(source), str(dest))
                else:
                    shutil.copy2(str(source), str(dest))
                status_var.set(f"Copied to {target_folder.name}")
            
            # Refresh the tree
            load_config_folder_by_path(config_folder)
            
            # Clear clipboard after cut
            if clipboard_item['operation'] == 'cut':
                clipboard_item['path'] = None
                clipboard_item['operation'] = None
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to paste: {e}")
            app_logger.error(f"Failed to paste: {e}")
    
    def create_new_folder() -> None:
        """Create a new folder."""
        selection = config_tree.selection()
        target_folder = config_folder
        
        # Determine target folder
        if selection:
            item_id = selection[0]
            item_values = config_tree.item(item_id, 'values')
            if len(item_values) >= 2:
                path = Path(item_values[0])
                if item_values[1] == 'folder':
                    target_folder = path
                else:
                    target_folder = path.parent
        
        # Prompt for folder name
        from tkinter import simpledialog
        folder_name = simpledialog.askstring("New Folder", "Enter folder name:", parent=root)
        
        if folder_name:
            new_folder = target_folder / folder_name
            try:
                new_folder.mkdir(parents=True, exist_ok=False)
                # Refresh the tree
                load_config_folder_by_path(config_folder)
                status_var.set(f"Created folder: {folder_name}")
                app_logger.info(f"Created folder: {new_folder}")
            except FileExistsError:
                messagebox.showerror("Error", "Folder already exists")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to create folder: {e}")
                app_logger.error(f"Failed to create folder: {e}")
    
    def on_config_right_click(event) -> None:
        """Show context menu for config tree."""
        # Select item under cursor
        item_id = config_tree.identify_row(event.y)
        if item_id:
            config_tree.selection_set(item_id)
        
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

    # ===== Edit Tab Functions =====
    def refresh_edit_view() -> None:
        """Refresh the edit view by loading the current config."""
        nonlocal edit_data, edit_config_type
        
        config_path_str = config_var.get().strip()
        if not config_path_str:
            edit_data = None
            edit_config_type = None
            edit_tree.delete(*edit_tree.get_children())
            edit_tree.insert("", "end", values=("", i18n.t("no_config_loaded"), ""))
            return
        
        config_path = Path(config_path_str)
        if not config_path.exists():
            edit_data = None
            edit_config_type = None
            edit_tree.delete(*edit_tree.get_children())
            edit_tree.insert("", "end", values=("", i18n.t("config_not_found"), ""))
            return
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            edit_data = data
            refresh_edit_tree()
            
        except Exception as e:
            edit_data = None
            edit_config_type = None
            app_logger.error(f"Failed to load config for editing: {e}")
            edit_tree.delete(*edit_tree.get_children())
            edit_tree.insert("", "end", values=("", "Error", str(e)))

    record_type_options = [
        "click_left",
        "click_right",
        "hold_left",
        "hold_right",
        "drag_left",
        "drag_right",
        "key_press",
        "key_release",
    ]

    legacy_type_options = [
        "click_left",
        "click_right",
        "drag_left",
        "drag_right",
        "key",
    ]

    def _configure_edit_tree_for_mode(config_type: str | None) -> None:
        if config_type == "composite":
            columns = ("index", "type", "details")
            headings = {
                "index": "Index",
                "type": "Type",
                "details": "Details",
            }
        else:
            columns = ("time", "type", "x1", "y1", "x2", "y2", "duration", "key")
            headings = {
                "time": "Time",
                "type": "Type",
                "x1": "x1",
                "y1": "y1",
                "x2": "x2",
                "y2": "y2",
                "duration": "duration",
                "key": "key",
            }

        edit_tree["columns"] = columns
        for col in columns:
            edit_tree.heading(col, text=headings.get(col, col))
            edit_tree.column(col, anchor=tk.W, stretch=False)
        root.after(0, _update_edit_tree_column_widths)

    def _display_type_from_event(event: dict) -> str:
        event_type = event.get("type", "")
        if event_type in ("click", "hold", "drag"):
            button = event.get("button", "left")
            return f"{event_type}_{button}"
        if event_type in ("key_press", "key_release"):
            return event_type
        return event_type

    def _display_type_from_step(step: dict) -> str:
        action = step.get("action", "")
        if action in ("click", "hold", "drag"):
            button = step.get("button", "left")
            return f"{action}_{button}"
        if action == "key":
            return "key"
        return action

    def _apply_display_type_to_event(event: dict, display_type: str) -> None:
        if display_type in ("key_press", "key_release"):
            event["type"] = display_type
            event.pop("button", None)
            if "key" not in event:
                event["key"] = ""
            return

        if "_" in display_type:
            base, button = display_type.split("_", 1)
        else:
            base, button = display_type, "left"

        if base in ("click", "hold", "drag"):
            event["type"] = base
            event["button"] = button
            if base in ("click", "hold"):
                if event.get("x") is None and event.get("start_x") is not None:
                    event["x"] = event.get("start_x")
                if event.get("y") is None and event.get("start_y") is not None:
                    event["y"] = event.get("start_y")
                event.setdefault("duration", 0)
            elif base == "drag":
                if event.get("start_x") is None and event.get("x") is not None:
                    event["start_x"] = event.get("x")
                if event.get("start_y") is None and event.get("y") is not None:
                    event["start_y"] = event.get("y")
                if event.get("end_x") is None:
                    event["end_x"] = event.get("start_x")
                if event.get("end_y") is None:
                    event["end_y"] = event.get("start_y")
                event.setdefault("duration", 0)

    def _apply_display_type_to_step(step: dict, display_type: str) -> None:
        if display_type == "key":
            step["action"] = "key"
            step.pop("button", None)
            if "key" not in step:
                step["key"] = ""
            return

        if "_" in display_type:
            base, button = display_type.split("_", 1)
        else:
            base, button = display_type, "left"

        if base in ("click", "hold", "drag"):
            step["action"] = base
            step["button"] = button
            if base in ("click", "hold"):
                if step.get("x") is None and step.get("start_x") is not None:
                    step["x"] = step.get("start_x")
                if step.get("y") is None and step.get("start_y") is not None:
                    step["y"] = step.get("start_y")
                step.setdefault("duration", 0)
            elif base == "drag":
                if step.get("start_x") is None and step.get("x") is not None:
                    step["start_x"] = step.get("x")
                if step.get("start_y") is None and step.get("y") is not None:
                    step["start_y"] = step.get("y")
                if step.get("end_x") is None:
                    step["end_x"] = step.get("start_x")
                if step.get("end_y") is None:
                    step["end_y"] = step.get("start_y")
                step.setdefault("duration", 0)

    def _timeline_row_values(event: dict) -> tuple[str, str, str, str, str, str, str, str]:
        time_str = f"{event.get('time', 0):.3f}s"
        display_type = _display_type_from_event(event)
        x1 = y1 = x2 = y2 = duration = key = ""

        if event.get("type") in ("click", "hold"):
            x1 = "" if event.get("x") is None else str(int(event.get("x")))
            y1 = "" if event.get("y") is None else str(int(event.get("y")))
            if event.get("type") == "hold":
                duration = f"{float(event.get('duration', 0)):.3f}"
        elif event.get("type") == "drag":
            x1 = "" if event.get("start_x") is None else str(int(event.get("start_x")))
            y1 = "" if event.get("start_y") is None else str(int(event.get("start_y")))
            x2 = "" if event.get("end_x") is None else str(int(event.get("end_x")))
            y2 = "" if event.get("end_y") is None else str(int(event.get("end_y")))
            duration = f"{float(event.get('duration', 0)):.3f}"
        elif event.get("type") in ("key_press", "key_release"):
            key = str(event.get("key", ""))

        return (time_str, display_type, x1, y1, x2, y2, duration, key)

    def _legacy_row_values(step: dict, index: int) -> tuple[str, str, str, str, str, str, str, str]:
        index_str = str(index)
        display_type = _display_type_from_step(step)
        x1 = y1 = x2 = y2 = duration = key = ""
        action = step.get("action")

        if action in ("click", "hold"):
            x1 = "" if step.get("x") is None else str(int(step.get("x")))
            y1 = "" if step.get("y") is None else str(int(step.get("y")))
            if action == "hold":
                duration = f"{float(step.get('duration', 0)):.3f}"
        elif action == "drag":
            x1 = "" if step.get("start_x") is None else str(int(step.get("start_x")))
            y1 = "" if step.get("start_y") is None else str(int(step.get("start_y")))
            x2 = "" if step.get("end_x") is None else str(int(step.get("end_x")))
            y2 = "" if step.get("end_y") is None else str(int(step.get("end_y")))
            duration = f"{float(step.get('duration', 0)):.3f}"
        elif action == "key":
            key = str(step.get("key", ""))

        return (index_str, display_type, x1, y1, x2, y2, duration, key)
    
    def refresh_edit_tree() -> None:
        """Refresh the tree view using the current edit_data in memory."""
        nonlocal edit_config_type
        
        if edit_data is None:
            edit_tree.delete(*edit_tree.get_children())
            edit_tree.insert("", "end", values=("", i18n.t("no_config_loaded"), ""))
            return
        
        edit_tree.delete(*edit_tree.get_children())

        # Determine config type
        if isinstance(edit_data, dict) and edit_data.get("type") == "composite":
            edit_config_type = "composite"
            _configure_edit_tree_for_mode(edit_config_type)
            # Display composite configs
            configs = edit_data.get("configs", [])
            for idx, item in enumerate(configs):
                config_name = Path(item.get("config", "")).name
                edit_tree.insert("", "end", values=(str(idx), "Config", config_name), tags=("composite",))
            app_logger.info(f"Displayed composite config with {len(configs)} items")
            
        elif isinstance(edit_data, dict) and "timeline" in edit_data:
            edit_config_type = "timeline"
            _configure_edit_tree_for_mode(edit_config_type)
            # Display timeline events
            timeline = edit_data.get("timeline", [])
            for idx, event in enumerate(timeline):
                values = _timeline_row_values(event)
                edit_tree.insert("", "end", values=values, tags=("timeline",))
            app_logger.info(f"Displayed timeline config with {len(timeline)} events")
            
        else:
            edit_config_type = "legacy"
            _configure_edit_tree_for_mode(edit_config_type)
            # Display legacy steps
            if isinstance(edit_data, list):
                for idx, step in enumerate(edit_data):
                    values = _legacy_row_values(step, idx)
                    edit_tree.insert("", "end", values=values, tags=("legacy",))
                app_logger.info(f"Displayed legacy config with {len(edit_data)} steps")
            else:
                edit_tree.insert("", "end", values=("", "Error", "Unknown config format"))
        
        status_var.set(f"Loaded {edit_config_type} config for editing")
    
    def format_event_details(event: dict) -> str:
        """Format timeline event details for display."""
        event_type = event.get("type", "")
        
        if event_type == "click":
            return f"({event.get('x')}, {event.get('y')}) [{event.get('button', 'left')}]"
        elif event_type == "drag":
            return f"({event.get('start_x')}, {event.get('start_y')}) -> ({event.get('end_x')}, {event.get('end_y')})"
        elif event_type == "hold":
            return f"({event.get('x')}, {event.get('y')}) for {event.get('duration', 0):.2f}s"
        elif event_type == "key_press":
            return f"Press '{event.get('key', '')}'"
        elif event_type == "key_release":
            return f"Release '{event.get('key', '')}'"
        else:
            return json.dumps({k: v for k, v in event.items() if k != "type" and k != "time"})
    
    def format_step_details(step: dict) -> str:
        """Format legacy step details for display."""
        action = step.get("action", "")
        
        if action == "click":
            return f"({step.get('x')}, {step.get('y')})"
        elif action == "drag":
            return f"({step.get('start_x')}, {step.get('start_y')}) -> ({step.get('end_x')}, {step.get('end_y')})"
        elif action == "key":
            return f"Key: {step.get('key', '')}"
        else:
            return json.dumps({k: v for k, v in step.items() if k != "action"})
    
    def save_edit_changes() -> None:
        """Save the edited config back to file."""
        nonlocal edit_data
        
        if edit_data is None:
            messagebox.showinfo("Info", i18n.t("load_config_first"))
            return
        
        config_path_str = config_var.get().strip()
        if not config_path_str:
            messagebox.showerror("Error", "No config file specified")
            return
        
        config_path = Path(config_path_str)
        
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(edit_data, f, indent=2, ensure_ascii=False)
            status_var.set(f"Saved changes to {config_path.name}")
            app_logger.info(f"Saved edited config to {config_path}")
            messagebox.showinfo("Success", f"Changes saved to {config_path.name}")
        except Exception as e:
            app_logger.error(f"Failed to save edited config: {e}")
            messagebox.showerror("Error", f"Failed to save: {e}")


    
    def delete_edit_step() -> None:
        """Delete the selected step from the edit view."""
        nonlocal edit_data
        
        selection = edit_tree.selection()
        if not selection:
            return
        
        item = selection[0]
        item_index = edit_tree.index(item)
        
        if edit_config_type == "composite":
            # Remove from composite configs
            if 0 <= item_index < len(edit_data.get("configs", [])):
                removed = edit_data["configs"].pop(item_index)
                edit_tree.delete(item)
                app_logger.info(f"Deleted composite item: {removed}")
                status_var.set("Deleted composite item")
                
        elif edit_config_type == "timeline":
            # Remove from timeline
            timeline = edit_data.get("timeline", [])
            if 0 <= item_index < len(timeline):
                removed = timeline.pop(item_index)
                edit_tree.delete(item)
                app_logger.info(f"Deleted timeline event: {removed}")
                status_var.set("Deleted timeline event")
                
        elif edit_config_type == "legacy":
            # Remove from legacy steps
            if isinstance(edit_data, list) and 0 <= item_index < len(edit_data):
                removed = edit_data.pop(item_index)
                edit_tree.delete(item)
                app_logger.info(f"Deleted legacy step: {removed}")
                status_var.set("Deleted legacy step")
    
    def adjust_timeline_after_deletion(deleted_index: int) -> None:
        """Adjust timeline after deleting an event."""
        if edit_config_type != "timeline":
            return
        
        timeline = edit_data.get("timeline", [])
        if deleted_index >= len(timeline):
            return
        
        # Get the time of the deleted event (we need to subtract this from subsequent events)
        # Actually, we don't adjust times for deletion, only for insertion
        # Just refresh the view
        pass
    
    def adjust_timeline_after_insertion(insert_index: int, inserted_duration: float) -> None:
        """Adjust timeline after inserting new events."""
        if edit_config_type != "timeline":
            return
        
        timeline = edit_data.get("timeline", [])
        
        # Shift all subsequent events by the inserted duration
        for i in range(insert_index, len(timeline)):
            if "time" in timeline[i]:
                timeline[i]["time"] = round(timeline[i]["time"] + inserted_duration, 3)
    
    def start_re_recording(mode: str) -> None:
        """Start re-recording for the selected step."""
        nonlocal re_recording_step_index, re_recording_mode
        
        selection = edit_tree.selection()
        if not selection:
            return
        
        if edit_config_type not in ("timeline", "legacy"):
            messagebox.showinfo("Info", "Re-recording only works for recorded configs")
            return
        
        item = selection[0]
        item_index = edit_tree.index(item)
        re_recording_step_index = item_index
        re_recording_mode = mode
        
        set_controls(True, running)
        
        if mode == "re-record":
            status_var.set(f"Re-recording step {item_index}... Starting in 1 second...")
        elif mode == "insert-above":
            status_var.set(f"Recording to insert above step {item_index}... Starting in 1 second...")
        elif mode == "insert-below":
            status_var.set(f"Recording to insert below step {item_index}... Starting in 1 second...")
        
        def begin() -> None:
            minimize_gui()
            recorder.start()
            app_logger.info(f"Started {mode} for step {item_index}")
            if mode == "re-record":
                status_var.set(f"Re-recording step {item_index}... Press Ctrl+X to stop.")
            elif mode == "insert-above":
                status_var.set(f"Recording to insert above step {item_index}... Press Ctrl+X to stop.")
            elif mode == "insert-below":
                status_var.set(f"Recording to insert below step {item_index}... Press Ctrl+X to stop.")
        
        root.after(1000, begin)
    
    def finish_re_recording(recorded_data: dict) -> None:
        """Finish re-recording and update the config."""
        nonlocal edit_data, re_recording_step_index, re_recording_mode
        
        if re_recording_step_index is None or re_recording_mode is None:
            return
        
        recorded_events = recorded_data.get("timeline", [])
        app_logger.info(f"finish_re_recording: Got {len(recorded_events)} events before trimming")
        
        if not recorded_events:
            messagebox.showinfo("Info", "No events recorded")
            re_recording_step_index = None
            re_recording_mode = None
            return
        
        recorded_events = recorded_data.get("timeline", [])
        app_logger.info(f"finish_re_recording: Got {len(recorded_events)} events after trimming")
        
        if not recorded_events:
            messagebox.showinfo("Info", "No events recorded after trimming")
            re_recording_step_index = None
            re_recording_mode = None
            return
        
        app_logger.info(f"finish_re_recording: Processing mode={re_recording_mode}, index={re_recording_step_index}, config_type={edit_config_type}")
        
        if edit_config_type == "timeline":
            timeline = edit_data.get("timeline", [])
            
            if re_recording_mode == "re-record":
                # Delete old operation and insert new ones at the same position
                if 0 <= re_recording_step_index < len(timeline):
                    old_time = timeline[re_recording_step_index].get("time", 0)
                    # Calculate old duration (time until next event, or 0 if last)
                    if re_recording_step_index + 1 < len(timeline):
                        old_next_time = timeline[re_recording_step_index + 1].get("time", 0)
                        old_duration = old_next_time - old_time
                    else:
                        old_duration = 0
                    
                    # Remove the old event
                    timeline.pop(re_recording_step_index)
                    
                    # Calculate duration of new recording
                    new_duration = recorded_events[-1].get("time", 0) if recorded_events else 0
                    
                    # Insert new events, aligning first event with old time
                    for i, event in enumerate(recorded_events):
                        new_event = event.copy()
                        new_event["time"] = round(old_time + event.get("time", 0), 3)
                        timeline.insert(re_recording_step_index + i, new_event)
                    
                    # Adjust subsequent events (shift by the difference in duration)
                    time_shift = new_duration - old_duration
                    for i in range(re_recording_step_index + len(recorded_events), len(timeline)):
                        if "time" in timeline[i]:
                            timeline[i]["time"] = round(timeline[i]["time"] + time_shift, 3)
                    
                    app_logger.info(f"Re-recorded step {re_recording_step_index} with {len(recorded_events)} events")
                    
            elif re_recording_mode == "insert-above":
                # Insert new events above the selected step
                if 0 <= re_recording_step_index < len(timeline):
                    base_time = timeline[re_recording_step_index].get("time", 0)
                    # Calculate duration of new recording
                    new_duration = recorded_events[-1].get("time", 0) if recorded_events else 0
                    
                    # Insert new events at the selected position
                    for i, event in enumerate(recorded_events):
                        new_event = event.copy()
                        new_event["time"] = round(base_time + event.get("time", 0), 3)
                        timeline.insert(re_recording_step_index + i, new_event)
                    
                    # Adjust all subsequent events (including the originally selected one)
                    for i in range(re_recording_step_index + len(recorded_events), len(timeline)):
                        if "time" in timeline[i]:
                            timeline[i]["time"] = round(timeline[i]["time"] + new_duration, 3)
                    
                    app_logger.info(f"Inserted {len(recorded_events)} events above step {re_recording_step_index}")
                    
            elif re_recording_mode == "insert-below":
                # Insert new events below the selected step
                if 0 <= re_recording_step_index < len(timeline):
                    # For insert-below, we want new events to start after the selected event
                    # Get the time of the next event (or use selected event time if it's the last)
                    if re_recording_step_index + 1 < len(timeline):
                        base_time = timeline[re_recording_step_index + 1].get("time", 0)
                    else:
                        # If inserting after the last event, start from that event's time
                        base_time = timeline[re_recording_step_index].get("time", 0)
                    
                    # Calculate duration of new recording
                    new_duration = recorded_events[-1].get("time", 0) if recorded_events else 0
                    
                    # Insert new events after the selected step
                    insert_position = re_recording_step_index + 1
                    for i, event in enumerate(recorded_events):
                        new_event = event.copy()
                        new_event["time"] = round(base_time + event.get("time", 0), 3)
                        timeline.insert(insert_position + i, new_event)
                    
                    # Adjust subsequent events
                    for i in range(insert_position + len(recorded_events), len(timeline)):
                        if "time" in timeline[i]:
                            timeline[i]["time"] = round(timeline[i]["time"] + new_duration, 3)
                    
                    app_logger.info(f"Inserted {len(recorded_events)} events below step {re_recording_step_index}")
        
        elif edit_config_type == "legacy":
            # For legacy format, convert timeline events to legacy steps
            legacy_steps = [convert_timeline_to_legacy_step(event) for event in recorded_events]
            
            if isinstance(edit_data, list):
                if re_recording_mode == "re-record":
                    # Replace the old step with new ones
                    if 0 <= re_recording_step_index < len(edit_data):
                        edit_data.pop(re_recording_step_index)
                        for i, step in enumerate(legacy_steps):
                            edit_data.insert(re_recording_step_index + i, step)
                        app_logger.info(f"Re-recorded step {re_recording_step_index} with {len(legacy_steps)} steps")
                        
                elif re_recording_mode == "insert-above":
                    # Insert new steps above
                    for i, step in enumerate(legacy_steps):
                        edit_data.insert(re_recording_step_index + i, step)
                    app_logger.info(f"Inserted {len(legacy_steps)} steps above step {re_recording_step_index}")
                        
                elif re_recording_mode == "insert-below":
                    # Insert new steps below
                    insert_position = re_recording_step_index + 1
                    for i, step in enumerate(legacy_steps):
                        edit_data.insert(insert_position + i, step)
                    app_logger.info(f"Inserted {len(legacy_steps)} steps below step {re_recording_step_index}")
        
        # Reset re-recording state
        re_recording_step_index = None
        re_recording_mode = None
        
        # Refresh the tree view with the updated data in memory
        refresh_edit_tree()
        status_var.set("Re-recording complete")
    
    def convert_timeline_to_legacy_step(event: dict) -> dict:
        """Convert a timeline event to a legacy step format."""
        event_type = event.get("type", "")
        
        if event_type == "click":
            return {
                "action": "click",
                "x": event.get("x"),
                "y": event.get("y"),
                "button": event.get("button", "left")
            }
        elif event_type == "drag":
            return {
                "action": "drag",
                "start_x": event.get("start_x"),
                "start_y": event.get("start_y"),
                "end_x": event.get("end_x"),
                "end_y": event.get("end_y"),
                "duration": event.get("duration", 0)
            }
        elif event_type == "key_press" or event_type == "key_release":
            return {
                "action": "key",
                "key": event.get("key", "")
            }
        else:
            # Return the event as-is
            return {k: v for k, v in event.items() if k != "time"}
    
    def on_edit_right_click(event) -> None:
        """Show context menu for edit tree."""
        # Select the item under the cursor
        item = edit_tree.identify_row(event.y)
        if item:
            edit_tree.selection_set(item)
            
            # Create context menu based on config type
            edit_menu = tk.Menu(root, tearoff=0)
            
            if edit_config_type == "composite":
                edit_menu.add_command(label=i18n.t("insert_above"), command=lambda: add_composite_step_above())
                edit_menu.add_command(label=i18n.t("insert_below"), command=lambda: add_composite_step_below())
                edit_menu.add_separator()
                edit_menu.add_command(label=i18n.t("delete_step"), command=lambda: delete_edit_step())
            else:
                # For timeline and legacy (recorded configs)
                edit_menu.add_command(label=i18n.t("re_record"), command=lambda: start_re_recording("re-record"))
                edit_menu.add_command(label=i18n.t("insert_above"), command=lambda: start_re_recording("insert-above"))
                edit_menu.add_command(label=i18n.t("insert_below"), command=lambda: start_re_recording("insert-below"))
                edit_menu.add_separator()
                edit_menu.add_command(label=i18n.t("delete_step"), command=lambda: delete_edit_step())
            
            edit_menu.post(event.x_root, event.y_root)
    
    def on_edit_double_click(event) -> None:
        """Handle double-click to edit fields inline for recorded configs."""
        if edit_config_type not in ("timeline", "legacy"):
            return

        item = edit_tree.identify_row(event.y)
        column = edit_tree.identify_column(event.x)
        if not item or not column:
            return

        columns = edit_tree["columns"]
        try:
            column_key = columns[int(column.replace("#", "")) - 1]
        except (ValueError, IndexError):
            return

        bbox = edit_tree.bbox(item, column)
        if not bbox:
            return

        x, y, width, height = bbox
        item_index = edit_tree.index(item)

        def place_entry(initial_value: str, on_save) -> None:
            edit_entry = tk.Entry(edit_tree, width=10)
            edit_entry.insert(0, initial_value)
            edit_entry.select_range(0, tk.END)
            edit_entry.focus()
            edit_entry.place(x=x, y=y, width=width, height=height)

            def save_and_close():
                on_save(edit_entry.get())
                edit_entry.destroy()

            def cancel_edit(event=None):
                edit_entry.destroy()

            edit_entry.bind("<Return>", lambda e: save_and_close())
            edit_entry.bind("<Escape>", cancel_edit)
            edit_entry.bind("<FocusOut>", lambda e: save_and_close())

        def place_combobox(options: list[str], current_value: str, on_save) -> None:
            combo = ttk.Combobox(edit_tree, values=options, state="readonly")
            if current_value in options:
                combo.set(current_value)
            elif options:
                combo.set(options[0])
            combo.focus()
            combo.place(x=x, y=y, width=width, height=height)

            def save_and_close():
                on_save(combo.get())
                combo.destroy()

            def cancel_edit(event=None):
                combo.destroy()

            combo.bind("<<ComboboxSelected>>", lambda e: save_and_close())
            combo.bind("<Escape>", cancel_edit)
            combo.bind("<FocusOut>", lambda e: save_and_close())

        def parse_int(value: str) -> int | None:
            value = value.strip()
            if not value:
                return None
            return int(float(value))

        def parse_float(value: str) -> float | None:
            value = value.strip()
            if not value:
                return None
            return float(value)

        if edit_config_type == "timeline":
            timeline = edit_data.get("timeline", [])
            if item_index >= len(timeline):
                return
            current_event = timeline[item_index]
            current_type = current_event.get("type", "")

            if column_key == "time":
                current_time = current_event.get("time", 0)
                prev_time = timeline[item_index - 1].get("time", 0) if item_index > 0 else 0
                next_time = timeline[item_index + 1].get("time", float("inf")) if item_index + 1 < len(timeline) else float("inf")

                def save_time(value: str) -> None:
                    try:
                        new_time = float(value)
                        if new_time < prev_time or new_time > next_time:
                            status_var.set(f"Invalid time range, reverted to {current_time:.3f}s")
                            app_logger.info(
                                f"Time {new_time:.3f}s out of valid range [{prev_time:.3f}s, {next_time:.3f}s], reverted"
                            )
                            return
                        timeline[item_index]["time"] = round(new_time, 3)
                        refresh_edit_tree()
                        status_var.set(f"Updated time for step {item_index}")
                        app_logger.info(
                            f"Updated time for step {item_index} from {current_time:.3f}s to {new_time:.3f}s"
                        )
                    except ValueError:
                        status_var.set(f"Invalid input, reverted to {current_time:.3f}s")
                        app_logger.info(f"Invalid time input: '{value}', reverted")

                place_entry(f"{current_time:.3f}", save_time)
                return

            if column_key == "type":
                display_type = _display_type_from_event(current_event)

                def save_type(new_type: str) -> None:
                    if not new_type:
                        return
                    _apply_display_type_to_event(current_event, new_type)
                    refresh_edit_tree()

                place_combobox(record_type_options, display_type, save_type)
                return

            if column_key == "key" and current_type in ("key_press", "key_release"):
                current_key = str(current_event.get("key", ""))

                def save_key(value: str) -> None:
                    current_event["key"] = value
                    refresh_edit_tree()

                place_entry(current_key, save_key)
                return

            if column_key in ("x1", "y1", "x2", "y2", "duration"):
                allowed = False
                if current_type in ("click", "hold"):
                    allowed = column_key in ("x1", "y1", "duration")
                elif current_type == "drag":
                    allowed = column_key in ("x1", "y1", "x2", "y2", "duration")
                if not allowed:
                    return

                def current_value() -> str:
                    if current_type in ("click", "hold"):
                        if column_key == "x1":
                            return "" if current_event.get("x") is None else str(int(current_event.get("x")))
                        if column_key == "y1":
                            return "" if current_event.get("y") is None else str(int(current_event.get("y")))
                    if current_type == "drag":
                        if column_key == "x1":
                            return "" if current_event.get("start_x") is None else str(int(current_event.get("start_x")))
                        if column_key == "y1":
                            return "" if current_event.get("start_y") is None else str(int(current_event.get("start_y")))
                        if column_key == "x2":
                            return "" if current_event.get("end_x") is None else str(int(current_event.get("end_x")))
                        if column_key == "y2":
                            return "" if current_event.get("end_y") is None else str(int(current_event.get("end_y")))
                    if column_key == "duration":
                        return f"{float(current_event.get('duration', 0)):.3f}"
                    return ""

                def save_numeric(value: str) -> None:
                    try:
                        if column_key == "duration":
                            parsed = parse_float(value)
                            if parsed is None:
                                return
                            current_event["duration"] = round(parsed, 3)
                        else:
                            parsed = parse_int(value)
                            if parsed is None:
                                return
                            if current_type in ("click", "hold"):
                                if column_key == "x1":
                                    current_event["x"] = parsed
                                elif column_key == "y1":
                                    current_event["y"] = parsed
                            elif current_type == "drag":
                                if column_key == "x1":
                                    current_event["start_x"] = parsed
                                elif column_key == "y1":
                                    current_event["start_y"] = parsed
                                elif column_key == "x2":
                                    current_event["end_x"] = parsed
                                elif column_key == "y2":
                                    current_event["end_y"] = parsed
                        refresh_edit_tree()
                    except ValueError:
                        status_var.set("Invalid input, reverted")
                        app_logger.info(f"Invalid numeric input: '{value}', reverted")

                place_entry(current_value(), save_numeric)
                return

        if edit_config_type == "legacy":
            if not isinstance(edit_data, list) or item_index >= len(edit_data):
                return
            step = edit_data[item_index]
            action = step.get("action", "")

            if column_key == "type":
                display_type = _display_type_from_step(step)

                def save_type(new_type: str) -> None:
                    if not new_type:
                        return
                    _apply_display_type_to_step(step, new_type)
                    refresh_edit_tree()

                place_combobox(legacy_type_options, display_type, save_type)
                return

            if column_key == "key" and action == "key":
                current_key = str(step.get("key", ""))

                def save_key(value: str) -> None:
                    step["key"] = value
                    refresh_edit_tree()

                place_entry(current_key, save_key)
                return

            if column_key in ("x1", "y1", "x2", "y2", "duration"):
                allowed = False
                if action in ("click", "hold"):
                    allowed = column_key in ("x1", "y1", "duration")
                elif action == "drag":
                    allowed = column_key in ("x1", "y1", "x2", "y2", "duration")
                if not allowed:
                    return

                def current_value() -> str:
                    if action in ("click", "hold"):
                        if column_key == "x1":
                            return "" if step.get("x") is None else str(int(step.get("x")))
                        if column_key == "y1":
                            return "" if step.get("y") is None else str(int(step.get("y")))
                    if action == "drag":
                        if column_key == "x1":
                            return "" if step.get("start_x") is None else str(int(step.get("start_x")))
                        if column_key == "y1":
                            return "" if step.get("start_y") is None else str(int(step.get("start_y")))
                        if column_key == "x2":
                            return "" if step.get("end_x") is None else str(int(step.get("end_x")))
                        if column_key == "y2":
                            return "" if step.get("end_y") is None else str(int(step.get("end_y")))
                    if column_key == "duration":
                        return f"{float(step.get('duration', 0)):.3f}"
                    return ""

                def save_numeric(value: str) -> None:
                    try:
                        if column_key == "duration":
                            parsed = parse_float(value)
                            if parsed is None:
                                return
                            step["duration"] = round(parsed, 3)
                        else:
                            parsed = parse_int(value)
                            if parsed is None:
                                return
                            if action in ("click", "hold"):
                                if column_key == "x1":
                                    step["x"] = parsed
                                elif column_key == "y1":
                                    step["y"] = parsed
                            elif action == "drag":
                                if column_key == "x1":
                                    step["start_x"] = parsed
                                elif column_key == "y1":
                                    step["start_y"] = parsed
                                elif column_key == "x2":
                                    step["end_x"] = parsed
                                elif column_key == "y2":
                                    step["end_y"] = parsed
                        refresh_edit_tree()
                    except ValueError:
                        status_var.set("Invalid input, reverted")
                        app_logger.info(f"Invalid numeric input: '{value}', reverted")

                place_entry(current_value(), save_numeric)
                return
    
    def add_composite_step_above() -> None:
        """Add a config to the composite list above the selected item."""
        if edit_config_type != "composite":
            return
        
        selection = edit_tree.selection()
        if not selection:
            return
        
        item = selection[0]
        item_index = edit_tree.index(item)
        
        # Open file dialog to select a config
        path = filedialog.askopenfilename(
            title="Select config to add",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if path:
            edit_data["configs"].insert(item_index, {"config": str(path)})
            refresh_edit_tree()
            app_logger.info(f"Added config to composite above index {item_index}: {path}")
            status_var.set(f"Added config above step {item_index}")
    
    def add_composite_step_below() -> None:
        """Add a config to the composite list below the selected item."""
        if edit_config_type != "composite":
            return
        
        selection = edit_tree.selection()
        if not selection:
            return
        
        item = selection[0]
        item_index = edit_tree.index(item)
        
        # Open file dialog to select a config
        path = filedialog.askopenfilename(
            title="Select config to add",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if path:
            edit_data["configs"].insert(item_index + 1, {"config": str(path)})
            refresh_edit_tree()
            app_logger.info(f"Added config to composite below index {item_index}: {path}")
            status_var.set(f"Added config below step {item_index}")

    def show_help() -> None:
        repo_url = "https://github.com/mikiisayakaa/EndfieldHelper.git"
        if not webbrowser.open(repo_url):
            messagebox.showinfo(i18n.t("help_title"), repo_url)

    def set_controls(recording: bool, is_running: bool) -> None:
        start_button.config(
            state=tk.DISABLED if (recording or is_running) else tk.NORMAL
        )
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
        nonlocal re_recording_step_index, re_recording_mode
        
        data = recorder.stop()
        
        # Check if this is a re-recording session
        if re_recording_step_index is not None and re_recording_mode is not None:
            # This is a re-recording, handle it differently
            set_controls(False, running)
            show_gui()
            finish_re_recording(data)
            return
        
        # Normal recording session
        config_path = Path(config_var.get().strip())
        if not config_path.name:
            messagebox.showerror(i18n.t("error"), i18n.t("error_choose_config"))
            set_controls(False, running)
            status_var.set(i18n.t("idle"))
            return
        
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

    padding = {"padx": 8, "pady": 6}

    # ===== MIDDLE COLUMN: Controls and Log =====
    config_frame = tk.Frame(root)
    config_frame.grid(row=0, column=0, sticky="we", **padding)
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
    comment_label.grid(row=1, column=0, sticky="w", **padding)
    
    comment_frame = tk.Frame(root)
    comment_frame.grid(row=2, column=0, sticky="nsew", **padding)
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
    notebook.grid(row=3, column=0, sticky="nsew", **padding)

    # ===== TAB 1: Recording Mode =====
    recording_tab = tk.Frame(notebook)
    notebook.add(recording_tab, text=i18n.t("recording"))

    # Button row - Start button only (Stop is now Ctrl+X only)
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

    # ===== TAB 3: Edit Mode =====
    edit_tab = tk.Frame(notebook)
    notebook.add(edit_tab, text=i18n.t("edit"))

    def on_notebook_tab_changed(event) -> None:
        selected_tab = notebook.select()
        if selected_tab == str(edit_tab):
            refresh_edit_view()

    notebook.bind("<<NotebookTabChanged>>", on_notebook_tab_changed)

    # Button frame for edit operations
    edit_button_frame = tk.Frame(edit_tab)
    edit_button_frame.pack(fill=tk.X, padx=8, pady=6)
    
    refresh_edit_button = ttk.Button(
        edit_button_frame,
        text=i18n.t("refresh"),
        command=lambda: refresh_edit_view(),
        width=10,
        style="Modern.TButton",
    )
    refresh_edit_button.pack(side=tk.LEFT, padx=(0, 4))
    
    save_edit_button = ttk.Button(
        edit_button_frame,
        text=i18n.t("save"),
        command=lambda: save_edit_changes(),
        width=10,
        style="Modern.TButton",
    )
    save_edit_button.pack(side=tk.LEFT, padx=(0, 4))

    # Steps list frame
    edit_list_frame = tk.LabelFrame(edit_tab, text=i18n.t("edit_steps"), padx=4, pady=4)
    edit_list_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 6))
    
    edit_list_scrollbar = tk.Scrollbar(edit_list_frame, orient=tk.VERTICAL)
    edit_list_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _update_edit_tree_column_widths() -> None:
        columns = edit_tree["columns"]
        if not columns:
            return
        total_width = edit_list_frame.winfo_width()
        if total_width <= 1:
            return
        scrollbar_width = edit_list_scrollbar.winfo_width()
        padding = 12
        available = max(60, total_width - scrollbar_width - padding)
        per_col = max(60, available // len(columns))
        for col in columns:
            edit_tree.column(col, width=per_col, stretch=False)
    
    # Create Treeview for better step display
    edit_tree = ttk.Treeview(
        edit_list_frame,
        columns=("time", "type", "x1", "y1", "x2", "y2", "duration", "key"),
        show="headings",
        height=10,
        yscrollcommand=edit_list_scrollbar.set,
    )
    edit_tree.heading("time", text="Time")
    edit_tree.heading("type", text="Type")
    edit_tree.heading("x1", text="x1")
    edit_tree.heading("y1", text="y1")
    edit_tree.heading("x2", text="x2")
    edit_tree.heading("y2", text="y2")
    edit_tree.heading("duration", text="duration")
    edit_tree.heading("key", text="key")
    for col in edit_tree["columns"]:
        edit_tree.column(col, anchor=tk.W, stretch=False)
    edit_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    edit_list_scrollbar.config(command=edit_tree.yview)
    edit_list_frame.bind("<Configure>", lambda event: _update_edit_tree_column_widths())
    
    # Bind right-click context menu for edit tree
    edit_tree.bind("<Button-3>", on_edit_right_click)
    # Bind double-click to edit time
    edit_tree.bind("<Double-Button-1>", on_edit_double_click)

    log_frame = tk.Frame(root)
    log_frame.grid(row=4, column=0, sticky="nsew", **padding)
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
    status_frame.grid(row=5, column=0, sticky="we", **padding)
    tk.Label(status_frame, textvariable=status_var).pack(side=tk.LEFT)
    tk.Label(status_frame, textvariable=position_var).pack(side=tk.RIGHT)
    tk.Label(status_frame, textvariable=click_hint_var, fg="red", width=6).pack(side=tk.RIGHT)

    # ===== RIGHT COLUMN: Config List =====
    top_right_frame = tk.Frame(root)
    top_right_frame.grid(row=0, column=1, sticky="we", **padding)
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
    config_list_frame.grid(row=1, column=1, rowspan=5, sticky="nsew", **padding)
    config_list_scrollbar = tk.Scrollbar(config_list_frame, orient=tk.VERTICAL)
    config_list_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    # Use Treeview for hierarchical folder structure
    config_tree = ttk.Treeview(
        config_list_frame,
        yscrollcommand=config_list_scrollbar.set,
        selectmode='browse',
        columns=('path', 'type'),
        displaycolumns=()  # Hide value columns
    )
    config_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    config_list_scrollbar.config(command=config_tree.yview)
    
    # Configure tree tags
    config_tree.tag_configure('folder', foreground='#0066cc')
    config_tree.tag_configure('file', foreground='black')
    
    config_tree.bind("<<TreeviewSelect>>", on_config_select)
    config_tree.bind("<Double-Button-1>", on_config_double_click)
    config_tree.bind("<Button-3>", on_config_right_click)

    # Enhanced context menu with more operations
    config_menu = tk.Menu(root, tearoff=0)
    config_menu.add_command(label=i18n.t("open_in_editor"), command=open_selected_config_in_editor)
    config_menu.add_separator()
    config_menu.add_command(label="Cut", command=cut_selected_config)
    config_menu.add_command(label="Copy", command=copy_selected_config)
    config_menu.add_command(label="Paste", command=paste_config)
    config_menu.add_separator()
    config_menu.add_command(label="New Folder", command=create_new_folder)
    config_menu.add_separator()
    config_menu.add_command(label="Delete", command=delete_selected_config)

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





    def start_hotkey_listener() -> None:
        nonlocal hotkey_listener
        if hotkey_listener is None:
            hotkey_listener = keyboard.GlobalHotKeys(
                {"<ctrl>+x": lambda: ui_call(on_hotkey_stop)}
            )
            hotkey_listener.start()
        # Start the arrow key hook for mouse movement
        _start_arrow_worker()
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
        if idle_listener:
            idle_listener.stop()
        # Stop the arrow key hook
        _stop_arrow_key_hook()
        _stop_arrow_worker()
        root.destroy()

    start_hotkey_listener()
    # Auto-load configs folder on startup
    configs_folder = Path("configs")
    if configs_folder.exists() and configs_folder.is_dir():
        load_config_folder_by_path(configs_folder)
    root.update_idletasks()
    half_width = max(1, root.winfo_reqwidth() // 2)
    root.geometry(f"{half_width}x{root.winfo_reqheight()}")
    root.deiconify()
    root.protocol("WM_DELETE_WINDOW", on_window_close)
    app_logger.info("GUI initialized, entering main loop")
    root.mainloop()
    app_logger.info("Application closed")
    app_logger.info("=" * 50)
    return 0
