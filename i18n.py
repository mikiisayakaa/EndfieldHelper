"""
Internationalization (i18n) module for Endfield Helper
Provides multilingual support for the GUI
"""

# Translation dictionary
TRANSLATIONS = {
    "en": {
        # Window and titles
        "app_title": "Endfield Helper",
        
        # Main labels
        "config": "Config",
        "comment": "Comment",
        
        # Buttons - Main
        "start_recording": "Start Recording",
        "stop": "Stop",
        "run_config": "Run Config",
        "help": "Help",
        "open": "Open",
        "open_folder": "Open Folder",
        "refresh": "Reload",
        "save": "Save",
        
        # Buttons - Composite
        "save_composite": "Save Composite",
        "run_composite": "Run Composite",
        "clear": "Clear",
        "up": "↑",
        "down": "↓",
        
        # Frame titles
        "goods_template": "Goods Template",
        "composite_config_list": "Composite Config List",
        "config_list": "Config List",
        "recording": "Recording",
        "composite": "Composite",
        "edit": "Edit",
        "edit_steps": "Steps",
        
        # Status messages
        "idle": "Idle",
        "starting_recording": "Starting in 1 second...",
        "recording_status": "Recording... Press Ctrl+X to stop.",
        "recording_saved": "Saved {count} steps to {path}",
        "loading_configs": "Loaded {count} config(s) from folder",
        "composite_added": "Added {name} to composite list",
        "composite_removed": "Removed {name} from composite list",
        "composite_moved_up": "Moved up: {name}",
        "composite_moved_down": "Moved down: {name}",
        "stopping": "Stopping...",
        "running_composite": "Running composite config...",
        "running_config_n": "Running config {idx}/{total}: {name}",
        "composite_empty": "Composite list is empty.",
        "config_not_chosen": "Please choose a config file.",
        "config_not_found": "Config file not found.",
        "config_exists": "Config already exists. Overwrite and re-record?",
        "clear_composite_list": "Clear the composite config list?",
        "open_in_editor": "Open in Default Editor",
        "add_step": "Add Step",
        "delete_step": "Delete Step",
        "re_record": "Re-record",
        "insert_above": "Insert Above",
        "insert_below": "Insert Below",
        "no_config_loaded": "No config loaded",
        "load_config_first": "Please load a config first",
        
        # Instructions
        "composite_instructions": "Double-click configs from right panel to add • Double-click/Del to remove • ↑↓ to reorder",
        
        # Help text
        "help_title": "Help - Endfield Helper",
        "help_content": (
            "Usage Guide:\n"
            "\n"
            "1. Normal config recording: Enter a config name (or path, must be a JSON file) and click Start Recording. "
            "If the config already exists, you will be asked whether to overwrite. The UI hides after 1 second, then you can operate "
            "the Endfield PC client. The following actions are recorded:\n"
            "- Keyboard keys (movement, hotkey Y to open base panel, etc.)\n"
            "- Mouse clicks (click or drag)\n"
            "- Special hotkeys (pre-set OCR operations, see below)\n"
            "\n"
            "The following actions are NOT recorded:\n"
            "- Mouse look (so precise route recording is difficult; try WASD + middle click to reset the front view)\n"
            "\n"
            "**NEW: Arrow Keys for Mouse Movement Control\n"
            "\n"
            "After the script starts, you can use arrow keys to directly control mouse movement. Each key press moves 50 pixels:\n"
            "- Up arrow: Move mouse up\n"
            "- Down arrow: Move mouse down\n"
            "- Left arrow: Move mouse left\n"
            "- Right arrow: Move mouse right\n"
            "\n"
            "These arrow key operations support:\n"
            "1. Real-time control: Works in any window while the script is running\n"
            "2. Recording: Arrow key presses/releases are recorded as key_press/key_release events\n"
            "3. Playback: Playback executes key events at the recorded timing and simultaneously moves the mouse (since the hook remains active)\n"
            "\n"
            "This allows you to use arrow keys instead of the mouse for precise camera control and reliable route automation.\n"
            "\n"
            "While recording, press Ctrl+X to stop. The config will be saved to the path in the config field.\n"
            "\n"
            "Mouse click steps are recorded in absolute screen pixel coordinates, so they are NOT portable across devices. "
            "The provided configs were recorded on a 2560x1600 display.\n"
            "\n"
            "2. Ctrl+Shift+S auto-select elastic goods (OCR): When recording, enter the elastic goods purchase screen and drag "
            "the scrollbar so all items are visible. Press this hotkey to capture the goods, read prices, and click the biggest discount. "
            "After ~1s it will click automatically. If nothing is clicked, recognition likely failed. After clicking, you can continue recording. "
            "The left panel options correspond to Gudi/Wuling templates; choose the correct one before recording.\n"
            "\n"
            "3. Common daily automations:\n"
            "- Base harvest (Y, click/drag, ESC)\n"
            "- Base dispatch (Y, click, J)\n"
            "- Base collect dispatch (Y, click)\n"
            "- Trade: can be recorded in segments (sample configs split into 4 parts: 1) buy goods with Ctrl+Shift+S, 2) click goods and "
            "visit highest-price friend ship, 3) walk from reception to goods terminal, 4) sell goods)\n"
            "- Friend assist (type friend name, click)\n"
            "- Accept Wuling photo tasks (click only; does not complete task)\n"
            "\n"
            "4. Pending or hard automations:\n"
            "- Dijang harvest (needs assist handling; no technical blockers, needs testing and more OCR hotkeys)\n"
            "- Bag cleanup (needs more OCR and user-defined templates)\n"
            "- Auto gift (contact station landing position is not fixed)\n"
            "- Auto scheduling (too much data and unclear logic)\n"
            "- Auto stamina grind (needs model to detect red flash for dodge or it will die)\n"
            "- Auto delivery (camera control is hard; if doable with only WASD, try it)\n"
            "\n"
            "5. Normal config playback: Enter a config name and click Run Config. The UI hides and replays the recorded steps. "
            "Observe the first runs; press Ctrl+X to stop if something goes wrong.\n"
            "\n"
            "6. Composite config: Switch to the Composite tab. Open a folder to load configs on the right, double-click to add into "
            "the composite list. Double-click in the composite list to remove. After building, edit the config name and click Save. "
            "Composite configs run all items sequentially and can be nested, so you can combine short stable configs into complex flows. "
            "Make sure the end state of one config matches the start state of the next.\n"
            "\n"
            "7. Config list context menu: Right-click a config in the list to open it with the system default editor for easy viewing "
            "and editing.\n"
            "\n"
            "8. Disclaimer: This tool replays input actions. If run in an incorrect scenario or under high latency, it may cause loss. "
            "The developer is not responsible for such results."
        ),
        
        # Error messages
        "error": "Error",
        "error_choose_config": "Error - Please choose a config file.",
        "error_clear_config": "Error - Failed to clear config: {error}",
        "error_save": "Error - Failed to save: {error}",
        "error_load_config": "Error - Failed to load config",
        "error_run_config": "Error - Run config error",
        "error_process_goods": "Error - Processing goods error",
        "error_home_assist": "Error - Home assist OCR error",
        "error_open_editor": "Error - Failed to open in editor: {error}",
        
        # Other
        "overwrite": "Overwrite?",
        "choose_config_file": "Browse for config file",
        "language": "English",
        "toggle_language": "中文",  # Show Chinese as option when in English
    },
    
    "zh": {
        # Window and titles
        "app_title": "Endfield Helper",
        
        # Main labels
        "config": "配置",
        "comment": "备注",
        
        # Buttons - Main
        "start_recording": "开始录制",
        "stop": "停止",
        "run_config": "运行配置",
        "help": "帮助",
        "open": "打开",
        "open_folder": "打开文件夹",
        "refresh": "重新加载",
        "save": "保存",
        
        # Buttons - Composite
        "save_composite": "保存组合配置",
        "run_composite": "运行组合配置",
        "clear": "清除",
        "up": "↑",
        "down": "↓",
        "edit": "编辑",
        "edit_steps": "步骤",
        
        # Frame titles
        "goods_template": "商品模板",
        "composite_config_list": "组合配置列表",
        "config_list": "配置列表",
        "recording": "录制",
        "composite": "组合",
        
        # Status messages
        "idle": "空闲",
        "starting_recording": "1秒后开始...",
        "recording_status": "录制中... 按 Ctrl+X 停止。",
        "recording_saved": "已保存 {count} 步到 {path}",
        "loading_configs": "从文件夹加载了 {count} 个配置",
        "composite_added": "已添加 {name} 到组合列表",
        "composite_removed": "已从组合列表移除 {name}",
        "composite_moved_up": "上移: {name}",
        "composite_moved_down": "下移: {name}",
        "stopping": "停止中...",
        "running_composite": "运行组合配置中...",
        "running_config_n": "运行配置 {idx}/{total}: {name}",
        "composite_empty": "组合列表为空。",
        "config_not_chosen": "请选择配置文件。",
        "config_not_found": "配置文件未找到。",
        "config_exists": "配置文件已存在。覆盖并重新录制?",
        "clear_composite_list": "清空组合配置列表?",
        "open_in_editor": "用默认编辑器打开",
        "add_step": "添加步骤",
        "delete_step": "删除步骤",
        "re_record": "重新录制",
        "insert_above": "在上方插入",
        "insert_below": "在下方插入",
        "no_config_loaded": "未加载配置",
        "load_config_first": "请先加载配置",
        
        # Instructions
        "composite_instructions": "从右边面板双击配置添加 • 双击/删除键移除 • ↑↓重新排序",
        
        # Help text
        "help_title": "帮助 - Endfield Helper",
        "help_content": (
            "用法说明：\n"
            "\n"
            "1. 普通config录制：在配置栏填入config名称（或路径，必须是json文件），然后点击开始录制。如果config是已经存在的，开始录制会提示是否覆盖。界面会等待1秒后隐藏，此时可以在终末地PC客户端中进行操作，以下操作会被记录：\n"
            "- 键盘按键（如移动，快捷键Y呼出基建面板等）\n"
            "- 鼠标按键（点击或拖动）\n"
            "- 特殊快捷键（执行一些预设的OCR识别操作，见后文）\n"
            "\n"
            "以下操作不会被记录：\n"
            "- 鼠标调整视角（因此，想精确录制跑图过程比较困难，尝试用WASD组合+鼠标中键重置正面视角可以试试，会有误差）\n"
            "\n"
            "**新增功能：上下左右方向键控制鼠标移动\n"
            "\n"
            "脚本启动后，可以使用方向键直接控制鼠标移动。每次按下方向键移动 50 像素：\n"
            "- 上箭头键：鼠标向上移动\n"
            "- 下箭头键：鼠标向下移动\n"
            "- 左箭头键：鼠标向左移动\n"
            "- 右箭头键：鼠标向右移动\n"
            "\n"
            "这些方向键操作同时支持：\n"
            "1. 实时控制：脚本运行时在任何窗口中都能使用\n"
            "2. 录制：按下/抬起方向键时会被记录为 key_press/key_release 事件\n"
            "3. 回放：回放时会按相同时机执行按键和鼠标移动，由于钩子仍然生效，回放的鼠标控制也能生效\n"
            "\n"
            "这样可以用方向键代替鼠标来精确控制视角，实现更可靠的跑图自动化。\n"
            "\n"
            "录制开始后，Ctrl+X快捷键退出录制，config会自动保存到配置栏的路径中。\n"
            "\n"
            "config保存的鼠标左键操作都是基于屏幕空间像素坐标的，因此不同的设备之间无法通用，需要自行录制。提供的配置文件是在(2560,1600)大小的电脑上录制的。\n"
            "\n"
            "2. Ctrl+Shift+S自动选择弹性物资：用于自动倒货的OCR功能，录制状态下，在进入弹性物资购买界面后，拖动滚动条确保所有可购买物资都处于界面中，这时按这一快捷键会自动截取物资的图片并读取其价格，选择降价幅度最大的物资进行点击，稍等1秒会完成点击，如果没有点击货物说明识别出问题了。点击货物后你可以继续录制操作。左侧边栏的选项分别对应谷地和武陵的识别模板，在开始录制前要选择正确的模板，否则识别结果不对。\n"
            "\n"
            "3. 一些常见日常功能的自动化：\n"
            "- 基建收菜（按键组合：键盘Y，点击/拖动，键盘ESC）\n"
            "- 基建派单（按键组合：键盘Y，点击，键盘J）\n"
            "- 基建收单（按键组合：键盘Y，点击）\n"
            "- 倒货：比较复杂，可以分段录制（提供的config里分割为四段，1. 购买货物，用到Ctrl+Shift+S进行识别，2. 点击货物找到价格最高的好友进入好友飞船，3. 从会客室走到物资终端，4. 进行售卖）\n"
            "- 好友助力（指定好友完成助力，按键组合：键盘输入好友名，点击）\n"
            "- 接取武陵拍照任务（不包括完成任务，按键组合：点击）\n"
            "\n"
            "4. 有待开发/不容易做的自动化：\n"
            "- 帝江号收菜（需要处理助力，目前已经没有技术障碍，但还需要一些测试，需要额外引入一些OCR快捷键）\n"
            "- 背包清理（目前已经没有技术障碍，需要引入更多OCR和用户自动配置模板图片的功能）\n"
            "- 自动送礼物（有一定问题，干员联络台呼叫干员每次落点是不固定的，不好识别位置）\n"
            "- 自动排班（不懂排班逻辑，需要导入很多数据，太麻烦了）\n"
            "- 自动刷体力（自动战斗需要额外训练模型做红圈闪光的识别来实现自动闪避，否则很容易死）\n"
            "- 自动送货（视角操作目前难以读取，如果能仅用WASD，不动鼠标完成送货的可以试试）\n"
            "\n"
            "5. 普通config回放：在配置栏填入config名称，然后点击运行配置。界面会隐藏，然后回放用户录制的操作。建议前几次使用时都观察一下回放过程，如果回放过程出现问题可以随时Ctrl+X打断退出，确保config稳定运行无误。\n"
            "\n"
            "6. 组合式config：点击composite选项卡切换到组合式config构建，在右侧config栏上方打开文件夹导入其中所有config，双击可以将其中的config添加到组合式config，在组合栏双击则可以删除。组合式config构建完成后，修改config名称点击保存（直接保存的话config栏大概是某个其他config的名称，这时会提示你要不要覆盖，点不要覆盖，修改名称保存一个新的）。组合式config运行时会自动按顺序运行列表中的所有config，可以嵌套（组合式config里的条目也可以是其他组合式config），从而构建复杂的自动化操作。因此，你不需要为一个复杂的操作录制一个很长的config，这样容易出错，可以录制几个短的config然后构建组合式config，只要保证相邻的config之间起始状态和结束状态可以对上就行（比如都在3D大世界场景下）。\n"
            "\n"
            "7. 配置列表右键菜单：在右侧配置列表中右键某个配置，可以用系统默认编辑器打开，便于查看和编辑。\n"
            "\n"
            "8. 声明：本软件主要功能是按键脚本，回放的config在不正确的使用场景或延迟下可能误操作造成损失，开发者不对这类损失结果负责。"
        ),
        
        # Error messages
        "error": "错误",
        "error_choose_config": "错误 - 请选择配置文件。",
        "error_clear_config": "错误 - 清空配置失败: {error}",
        "error_save": "错误 - 保存失败: {error}",
        "error_load_config": "错误 - 加载配置失败",
        "error_run_config": "错误 - 运行配置出错",
        "error_process_goods": "错误 - 处理商品出错",
        "error_home_assist": "错误 - 家庭助手OCR出错",
        "error_open_editor": "错误 - 用默认编辑器打开失败: {error}",
        
        # Other
        "overwrite": "覆盖?",
        "choose_config_file": "浏览配置文件",
        "language": "中文",
        "toggle_language": "English",  # Show English as option when in Chinese
    }
}

class I18n:
    """Internationalization helper class"""
    
    def __init__(self, language: str = "en"):
        self.language = language if language in TRANSLATIONS else "en"
    
    def set_language(self, language: str) -> None:
        """Set the current language"""
        if language in TRANSLATIONS:
            self.language = language
    
    def get_language(self) -> str:
        """Get the current language"""
        return self.language
    
    def t(self, key: str, **kwargs) -> str:
        """
        Translate a key to the current language.
        Supports format strings with keyword arguments.
        
        Args:
            key: Translation key
            **kwargs: Format arguments for string formatting
            
        Returns:
            Translated string
        """
        try:
            text = TRANSLATIONS[self.language].get(key, key)
            if kwargs:
                return text.format(**kwargs)
            return text
        except KeyError:
            # Fallback to English if key not found
            fallback = TRANSLATIONS["en"].get(key, key)
            if kwargs:
                return fallback.format(**kwargs)
            return fallback
