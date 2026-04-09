"""
╔══════════════════════════════════════════════════════════════════╗
║         SCREEN RESOLUTION AI ASSISTANT  v1.0.0                  ║
║         Civilian Edition — Powered by Claude AI                  ║
╚══════════════════════════════════════════════════════════════════╝

Diagnoses and fixes Windows display/resolution issues using AI.
Supports resolution change, DPI scaling, refresh rate, registry
edits, ICC profiles, and driver-level diagnostics.
"""

import os
import sys
import json
import re
import time
import ctypes
import struct
import winreg
import threading
import subprocess
import platform
import shutil
import logging
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Third-party ──────────────────────────────────────────────────────────────
try:
    import customtkinter as ctk
    from tkinter import messagebox, filedialog
    import tkinter as tk
except ImportError:
    print("customtkinter not found. Run:  pip install customtkinter")
    sys.exit(1)

try:
    import anthropic
except ImportError:
    print("anthropic not found. Run:  pip install anthropic")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
APP_NAME    = "Screen Resolution AI Assistant"
APP_VERSION = "1.0.0"
APP_AUTHOR  = "Screen AI Tools"

CONFIG_DIR  = Path(os.environ.get("APPDATA", ".")) / "ScreenResAI"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_FILE    = CONFIG_DIR / "assistant.log"

ACCENT   = "#2563EB"
ACCENT2  = "#1D4ED8"
SUCCESS  = "#16A34A"
WARN     = "#D97706"
DANGER   = "#DC2626"
BG_DARK  = "#0F172A"
BG_MID   = "#1E293B"
BG_LIGHT = "#334155"
FG_MAIN  = "#F1F5F9"
FG_DIM   = "#94A3B8"

MODEL = "claude-opus-4-5"

CONFIG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("ScreenResAI")

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text("utf-8"))
        except Exception:
            pass
    return {"api_key": "", "auto_confirm": False, "theme": "dark"}

def save_config(cfg: dict):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2), "utf-8")

ENUM_CURRENT_SETTINGS  = -1
CDS_UPDATEREGISTRY     = 0x01
DISP_CHANGE_SUCCESSFUL = 0
DISP_CHANGE_RESTART    = 1
DM_PELSWIDTH           = 0x00080000
DM_PELSHEIGHT          = 0x00100000
DM_DISPLAYFREQUENCY    = 0x00400000
DM_BITSPERPEL          = 0x00040000

class DEVMODEW(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName",       ctypes.c_wchar * 32),
        ("dmSpecVersion",      ctypes.c_ushort),
        ("dmDriverVersion",    ctypes.c_ushort),
        ("dmSize",             ctypes.c_ushort),
        ("dmDriverExtra",      ctypes.c_ushort),
        ("dmFields",           ctypes.c_ulong),
        ("dmPositionX",        ctypes.c_long),
        ("dmPositionY",        ctypes.c_long),
        ("dmDisplayOrientation", ctypes.c_ulong),
        ("dmDisplayFixedOutput", ctypes.c_ulong),
        ("dmColor",            ctypes.c_short),
        ("dmDuplex",           ctypes.c_short),
        ("dmYResolution",      ctypes.c_short),
        ("dmTTOption",         ctypes.c_short),
        ("dmCollate",          ctypes.c_short),
        ("dmFormName",         ctypes.c_wchar * 32),
        ("dmLogPixels",        ctypes.c_ushort),
        ("dmBitsPerPel",       ctypes.c_ulong),
        ("dmPelsWidth",        ctypes.c_ulong),
        ("dmPelsHeight",       ctypes.c_ulong),
        ("dmDisplayFlags",     ctypes.c_ulong),
        ("dmDisplayFrequency", ctypes.c_ulong),
        ("dmICMMethod",        ctypes.c_ulong),
        ("dmICMIntent",        ctypes.c_ulong),
        ("dmMediaType",        ctypes.c_ulong),
        ("dmDitherType",       ctypes.c_ulong),
        ("dmReserved1",        ctypes.c_ulong),
        ("dmReserved2",        ctypes.c_ulong),
        ("dmPanningWidth",     ctypes.c_ulong),
        ("dmPanningHeight",    ctypes.c_ulong),
    ]

class DisplayManager:
    """Windows display control via ctypes + winreg + PowerShell."""

    @staticmethod
    def get_current_settings(device: str = None) -> dict:
        dm = DEVMODEW()
        dm.dmSize = ctypes.sizeof(DEVMODEW)
        dev_arg = device or ctypes.c_wchar_p(None)
        ctypes.windll.user32.EnumDisplaySettingsW(dev_arg, ENUM_CURRENT_SETTINGS, ctypes.byref(dm))
        return {
            "width": dm.dmPelsWidth, "height": dm.dmPelsHeight,
            "frequency": dm.dmDisplayFrequency, "bit_depth": dm.dmBitsPerPel,
            "position_x": dm.dmPositionX, "position_y": dm.dmPositionY,
            "orientation": dm.dmDisplayOrientation, "log_pixels": dm.dmLogPixels,
        }

    @staticmethod
    def enumerate_modes(device: str = None) -> list[dict]:
        modes = []
        dm = DEVMODEW()
        dm.dmSize = ctypes.sizeof(DEVMODEW)
        i = 0
        dev_arg = device or ctypes.c_wchar_p(None)
        while ctypes.windll.user32.EnumDisplaySettingsW(dev_arg, i, ctypes.byref(dm)):
            modes.append({"width": dm.dmPelsWidth, "height": dm.dmPelsHeight,
                          "frequency": dm.dmDisplayFrequency, "bit_depth": dm.dmBitsPerPel})
            i += 1
        seen, unique = set(), []
        for m in modes:
            k = (m["width"], m["height"], m["frequency"], m["bit_depth"])
            if k not in seen:
                seen.add(k)
                unique.append(m)
        return sorted(unique, key=lambda x: (x["width"], x["height"], x["frequency"]), reverse=True)

    @staticmethod
    def set_resolution(width: int, height: int, frequency: int = 0, device: str = None) -> tuple[bool, str]:
        dm = DEVMODEW()
        dm.dmSize = ctypes.sizeof(DEVMODEW)
        dev_arg = device or ctypes.c_wchar_p(None)
        ctypes.windll.user32.EnumDisplaySettingsW(dev_arg, ENUM_CURRENT_SETTINGS, ctypes.byref(dm))
        dm.dmPelsWidth = width
        dm.dmPelsHeight = height
        dm.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT
        if frequency:
            dm.dmDisplayFrequency = frequency
            dm.dmFields |= DM_DISPLAYFREQUENCY
        result = ctypes.windll.user32.ChangeDisplaySettingsW(ctypes.byref(dm), CDS_UPDATEREGISTRY)
        if result == DISP_CHANGE_SUCCESSFUL:
            return True, f"Resolution set to {width}x{height}" + (f" @ {frequency}Hz" if frequency else "")
        elif result == DISP_CHANGE_RESTART:
            return True, "Resolution set — restart required."
        return False, f"ChangeDisplaySettings failed (code {result})."

    @staticmethod
    def get_dpi_scaling() -> dict:
        result = {"system_dpi": 96, "per_monitor": False}
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop", 0, winreg.KEY_READ)
            try:
                val, _ = winreg.QueryValueEx(key, "LogPixels")
                result["system_dpi"] = int(val)
            except FileNotFoundError:
                pass
            winreg.CloseKey(key)
            result["scale_percent"] = round((result["system_dpi"] / 96) * 100)
        except Exception as e:
            log.warning(f"DPI registry read error: {e}")
        return result

    @staticmethod
    def set_dpi_scaling(dpi: int) -> tuple[bool, str]:
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop", 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "LogPixels", 0, winreg.REG_DWORD, dpi)
            winreg.CloseKey(key)
            key2 = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop", 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key2, "Win8DpiScaling", 0, winreg.REG_DWORD, 1)
            winreg.CloseKey(key2)
            return True, f"DPI set to {dpi} ({round(dpi/96*100)}%). Sign out to apply."
        except Exception as e:
            return False, f"Failed to set DPI: {e}"

    @staticmethod
    def set_refresh_rate(hz: int, device: str = None) -> tuple[bool, str]:
        dm = DEVMODEW()
        dm.dmSize = ctypes.sizeof(DEVMODEW)
        dev_arg = device or ctypes.c_wchar_p(None)
        ctypes.windll.user32.EnumDisplaySettingsW(dev_arg, ENUM_CURRENT_SETTINGS, ctypes.byref(dm))
        dm.dmDisplayFrequency = hz
        dm.dmFields = DM_DISPLAYFREQUENCY
        result = ctypes.windll.user32.ChangeDisplaySettingsW(ctypes.byref(dm), CDS_UPDATEREGISTRY)
        if result in (DISP_CHANGE_SUCCESSFUL, DISP_CHANGE_RESTART):
            return True, f"Refresh rate set to {hz}Hz"
        return False, f"Failed to set {hz}Hz."

    @staticmethod
    def get_monitors() -> list[dict]:
        monitors = []
        def callback(hMonitor, hdcMonitor, lprcMonitor, dwData):
            info = ctypes.create_string_buffer(40 + 8 * 4)
            struct.pack_into("I", info, 0, 40)
            ctypes.windll.user32.GetMonitorInfoW(hMonitor, info)
            monitors.append({
                "handle": hMonitor,
                "left": struct.unpack_from("i", info, 4)[0],
                "top": struct.unpack_from("i", info, 8)[0],
                "right": struct.unpack_from("i", info, 12)[0],
                "bottom": struct.unpack_from("i", info, 16)[0],
                "primary": bool(struct.unpack_from("I", info, 36)[0] & 1),
            })
            return True
        MONITORENUMPROC = ctypes.WINFUNCTYPE(
            ctypes.c_bool, ctypes.c_ulong, ctypes.c_ulong,
            ctypes.POINTER(ctypes.wintypes.RECT), ctypes.c_double)
        try:
            ctypes.windll.user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(callback), 0)
        except Exception as e:
            log.warning(f"Monitor enum error: {e}")
        return monitors

    @staticmethod
    def run_powershell(cmd: str, timeout: int = 30) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                ["powershell", "-NonInteractive", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                capture_output=True, text=True, timeout=timeout
            )
            return result.returncode == 0, (result.stdout + result.stderr).strip()
        except Exception as e:
            return False, str(e)

    @staticmethod
    def restart_graphics_driver() -> tuple[bool, str]:
        VK_B, VK_WIN, VK_CTRL, VK_SHIFT = 0x42, 0x5B, 0x11, 0x10
        KEYEVENTF_KEYUP = 0x0002
        ki = ctypes.windll.user32.keybd_event
        for k in [VK_WIN, VK_CTRL, VK_SHIFT, VK_B]:
            ki(k, 0, 0, 0)
        time.sleep(0.05)
        for k in reversed([VK_WIN, VK_CTRL, VK_SHIFT, VK_B]):
            ki(k, 0, KEYEVENTF_KEYUP, 0)
        return True, "GPU driver restart signal sent. Screen may flicker briefly."

    @staticmethod
    def clear_font_cache() -> tuple[bool, str]:
        ok, out = DisplayManager.run_powershell(
            "Stop-Service -Name FontCache -Force -ErrorAction SilentlyContinue; "
            "Remove-Item -Path '$env:SystemRoot\\ServiceProfiles\\LocalService\\AppData\\Local\\FontCache\\*' "
            "-Recurse -Force -ErrorAction SilentlyContinue; "
            "Start-Service -Name FontCache -ErrorAction SilentlyContinue; Write-Output 'Font cache cleared.'"
        )
        return ok, out or "Font cache operation completed."

    @staticmethod
    def toggle_cleartype(enable: bool) -> tuple[bool, str]:
        val = 2 if enable else 0
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop", 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "FontSmoothingType", 0, winreg.REG_DWORD, val)
            winreg.SetValueEx(key, "FontSmoothing", 0, winreg.REG_DWORD, 1 if enable else 0)
            winreg.CloseKey(key)
            ctypes.windll.user32.SystemParametersInfoW(0x001A, 0, None, 3)
            return True, f"ClearType {'enabled' if enable else 'disabled'}."
        except Exception as e:
            return False, f"ClearType toggle failed: {e}"

    @staticmethod
    def get_full_system_snapshot() -> dict:
        current = DisplayManager.get_current_settings()
        modes   = DisplayManager.enumerate_modes()
        dpi     = DisplayManager.get_dpi_scaling()
        monitors = DisplayManager.get_monitors()
        sw  = ctypes.windll.user32.GetSystemMetrics(0)
        sh  = ctypes.windll.user32.GetSystemMetrics(1)
        vsw = ctypes.windll.user32.GetSystemMetrics(78)
        vsh = ctypes.windll.user32.GetSystemMetrics(79)
        mc  = ctypes.windll.user32.GetSystemMetrics(80)
        ok, gpu_info = DisplayManager.run_powershell(
            "Get-WmiObject Win32_VideoController | "
            "Select-Object Name,CurrentHorizontalResolution,CurrentVerticalResolution,"
            "CurrentRefreshRate,CurrentBitsPerPixel,DriverVersion,VideoModeDescription "
            "| ConvertTo-Json -Compress"
        )
        return {
            "os": f"Windows {platform.release()} (Build {platform.version()})",
            "primary_monitor": current, "monitor_count": mc, "monitors": monitors,
            "virtual_desktop": {"width": vsw, "height": vsh},
            "system_metrics": {"width": sw, "height": sh},
            "dpi_info": dpi, "available_modes": modes[:30],
            "gpu_wmi": gpu_info if ok else "Unavailable",
        }

SYSTEM_PROMPT = """You are the Screen Resolution AI Assistant — an expert Windows display engineer embedded in a desktop diagnostic tool.

You have DIRECT ACCESS to the user's Windows system via the following tool primitives (executed by the host app):
  - set_resolution(width, height, frequency?)
  - set_refresh_rate(hz)
  - set_dpi(dpi_value)
  - restart_gpu_driver()
  - clear_font_cache()
  - toggle_cleartype(enable: bool)
  - run_powershell(command)
  - open_settings(panel)

BEHAVIOR RULES:
1. Diagnose the user's problem using the system snapshot provided.
2. Propose a minimal, ordered set of actions to fix the issue.
3. Always explain WHY each action is needed in plain English.
4. Return ONLY valid JSON — no markdown fences, no preamble.

JSON SCHEMA:
{
  "diagnosis": "Short description of what's wrong",
  "explanation": "Longer plain-English explanation",
  "actions": [
    {
      "id": 1,
      "label": "Human-readable label",
      "tool": "tool_name",
      "params": {},
      "risk": "low|medium|high",
      "reversible": true,
      "reason": "Why this helps"
    }
  ],
  "warnings": [],
  "requires_restart": false,
  "follow_up": "What to check after"
}
"""

class AIEngine:
    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.history: list[dict] = []

    def _parse(self, raw: str) -> dict:
        raw = re.sub(r"^```json\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"diagnosis": "AI returned unstructured response.", "explanation": raw,
                    "actions": [], "warnings": ["Could not parse structured response."],
                    "requires_restart": False, "follow_up": ""}

    def analyze(self, user_message: str, snapshot: dict) -> dict:
        context = json.dumps(snapshot, indent=2)
        user_content = f"SYSTEM SNAPSHOT:\n```json\n{context}\n```\n\nUSER PROBLEM:\n{user_message}"
        self.history.append({"role": "user", "content": user_content})
        response = self.client.messages.create(
            model=MODEL, max_tokens=2048, system=SYSTEM_PROMPT, messages=self.history)
        raw = response.content[0].text
        self.history.append({"role": "assistant", "content": raw})
        return self._parse(raw)

    def followup(self, user_message: str) -> dict:
        self.history.append({"role": "user", "content": user_message})
        response = self.client.messages.create(
            model=MODEL, max_tokens=2048, system=SYSTEM_PROMPT, messages=self.history)
        raw = response.content[0].text
        self.history.append({"role": "assistant", "content": raw})
        return self._parse(raw)

    def reset(self):
        self.history.clear()

class ActionExecutor:
    def __init__(self, dm: DisplayManager):
        self.dm = dm

    def execute(self, action: dict) -> tuple[bool, str]:
        tool = action.get("tool", "")
        params = action.get("params", {})
        log.info(f"Executing: {tool} with {params}")
        try:
            if tool == "set_resolution":
                return self.dm.set_resolution(int(params["width"]), int(params["height"]), int(params.get("frequency", 0)))
            elif tool == "set_refresh_rate":
                return self.dm.set_refresh_rate(int(params["hz"]))
            elif tool == "set_dpi":
                return self.dm.set_dpi_scaling(int(params["dpi_value"]))
            elif tool == "restart_gpu_driver":
                return self.dm.restart_graphics_driver()
            elif tool == "clear_font_cache":
                return self.dm.clear_font_cache()
            elif tool == "toggle_cleartype":
                return self.dm.toggle_cleartype(bool(params.get("enable", True)))
            elif tool == "run_powershell":
                return self.dm.run_powershell(params.get("command", ""))
            elif tool == "open_settings":
                panel = params.get("panel", "ms-settings:display")
                os.startfile(panel)
                return True, f"Opened: {panel}"
            return False, f"Unknown tool: {tool}"
        except Exception as e:
            log.error(f"Action execution error: {e}")
            return False, str(e)

class APIKeyDialog(ctk.CTkToplevel):
    def __init__(self, parent, current_key: str = ""):
        super().__init__(parent)
        self.title("Configure API Key")
        self.geometry("480x260")
        self.resizable(False, False)
        self.grab_set()
        self.result = None
        self.configure(fg_color=BG_MID)
        ctk.CTkLabel(self, text="🔑  Anthropic API Key", font=("Consolas", 16, "bold"), text_color=FG_MAIN).pack(pady=(24, 4))
        ctk.CTkLabel(self, text="Enter your Claude API key from console.anthropic.com",
                     font=("Consolas", 11), text_color=FG_DIM).pack(pady=(0, 16))
        self.key_entry = ctk.CTkEntry(self, width=400, height=38, placeholder_text="sk-ant-...", show="•",
            font=("Consolas", 12), fg_color=BG_DARK, border_color=ACCENT, text_color=FG_MAIN)
        self.key_entry.pack(pady=(0, 4))
        if current_key:
            self.key_entry.insert(0, current_key)
        self.show_var = tk.BooleanVar()
        ctk.CTkCheckBox(self, text="Show key", variable=self.show_var, font=("Consolas", 11),
            text_color=FG_DIM, command=lambda: self.key_entry.configure(show="" if self.show_var.get() else "•")).pack(pady=(4, 16))
        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack()
        ctk.CTkButton(btns, text="Cancel", width=100, fg_color=BG_LIGHT, hover_color=BG_MID, command=self.destroy).pack(side="left", padx=8)
        ctk.CTkButton(btns, text="Save", width=120, fg_color=ACCENT, hover_color=ACCENT2, command=self._save).pack(side="left", padx=8)

    def _save(self):
        key = self.key_entry.get().strip()
        if not key.startswith("sk-ant-"):
            messagebox.showwarning("Invalid Key", "Key should start with 'sk-ant-'.", parent=self)
            return
        self.result = key
        self.destroy()

class ActionCard(ctk.CTkFrame):
    RISK_COLORS = {"low": SUCCESS, "medium": WARN, "high": DANGER}

    def __init__(self, parent, action: dict, index: int, on_execute):
        super().__init__(parent, fg_color=BG_DARK, corner_radius=8, border_width=1, border_color=BG_LIGHT)
        self.pack(fill="x", padx=0, pady=4)
        risk = action.get("risk", "low")
        color = self.RISK_COLORS.get(risk, SUCCESS)
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10, 2))
        ctk.CTkLabel(top, text=f"  {index}  ", font=("Consolas", 11, "bold"),
            fg_color=color, text_color="white", corner_radius=4, width=28).pack(side="left")
        ctk.CTkLabel(top, text=action.get("label", "Action"), font=("Consolas", 12, "bold"),
            text_color=FG_MAIN, anchor="w").pack(side="left", padx=10)
        ctk.CTkLabel(top, text=f"[{risk.upper()}]", font=("Consolas", 10), text_color=color).pack(side="right")
        reason = action.get("reason", "")
        if reason:
            ctk.CTkLabel(self, text=reason, font=("Consolas", 10), text_color=FG_DIM,
                anchor="w", wraplength=540, justify="left").pack(fill="x", padx=12, pady=(0, 4))
        ctk.CTkLabel(self, text=f"Tool: {action.get('tool','')}  |  Reversible: {'Yes' if action.get('reversible') else 'No'}",
            font=("Consolas", 9), text_color=BG_LIGHT, anchor="w").pack(fill="x", padx=12, pady=(0, 6))
        ctk.CTkButton(self, text="Execute This Step", height=30, font=("Consolas", 11, "bold"),
            fg_color=ACCENT, hover_color=ACCENT2, command=lambda: on_execute(action)).pack(padx=12, pady=(0, 10), anchor="e")

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME}  v{APP_VERSION}")
        self.geometry("1100x740")
        self.minsize(900, 640)
        self.configure(fg_color=BG_DARK)
        try:
            self.iconbitmap(default="icon.ico")
        except Exception:
            pass
        self.cfg = load_config()
        self.dm = DisplayManager()
        self.executor = ActionExecutor(self.dm)
        self.engine: Optional[AIEngine] = None
        self.snapshot: Optional[dict] = None
        self._init_engine()
        self._build_ui()
        self._refresh_snapshot()

    def _init_engine(self):
        key = self.cfg.get("api_key", "")
        if key:
            try:
                self.engine = AIEngine(key)
                log.info("AI engine initialized.")
            except Exception as e:
                log.error(f"Engine init failed: {e}")

    def _build_ui(self):
        bar = ctk.CTkFrame(self, fg_color=BG_MID, height=52, corner_radius=0)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        ctk.CTkLabel(bar, text="Screen Resolution AI Assistant",
            font=("Consolas", 15, "bold"), text_color=FG_MAIN, anchor="w").pack(side="left", padx=20)
        ctk.CTkButton(bar, text="API Key", width=100, height=32, font=("Consolas", 11),
            fg_color=BG_LIGHT, hover_color=BG_MID, command=self._open_api_dialog).pack(side="right", padx=8)
        ctk.CTkButton(bar, text="Refresh", width=90, height=32, font=("Consolas", 11),
            fg_color=BG_LIGHT, hover_color=BG_MID, command=self._refresh_snapshot).pack(side="right", padx=4)
        ctk.CTkButton(bar, text="Reset Session", width=120, height=32, font=("Consolas", 11),
            fg_color=BG_LIGHT, hover_color=BG_MID, command=self._reset_session).pack(side="right", padx=4)
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=8)
        left = ctk.CTkFrame(body, fg_color=BG_MID, width=310, corner_radius=8)
        left.pack(side="left", fill="y", padx=(0, 8))
        left.pack_propagate(False)
        self._build_left_panel(left)
        right = ctk.CTkFrame(body, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True)
        self._build_right_panel(right)
        self.status_var = tk.StringVar(value="Ready.")
        status = ctk.CTkFrame(self, fg_color=BG_MID, height=28, corner_radius=0)
        status.pack(fill="x", side="bottom")
        status.pack_propagate(False)
        ctk.CTkLabel(status, textvariable=self.status_var, font=("Consolas", 10),
            text_color=FG_DIM, anchor="w").pack(side="left", padx=12, pady=4)

    def _build_left_panel(self, parent):
        ctk.CTkLabel(parent, text="DISPLAY INFO", font=("Consolas", 11, "bold"),
            text_color=ACCENT, anchor="w").pack(fill="x", padx=12, pady=(12, 4))
        self.info_box = ctk.CTkTextbox(parent, font=("Consolas", 10), fg_color=BG_DARK,
            text_color=FG_DIM, border_width=0, wrap="word")
        self.info_box.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.info_box.configure(state="disabled")
        ctk.CTkLabel(parent, text="AVAILABLE MODES", font=("Consolas", 11, "bold"),
            text_color=ACCENT, anchor="w").pack(fill="x", padx=12, pady=(4, 2))
        self.modes_box = ctk.CTkTextbox(parent, font=("Consolas", 9), fg_color=BG_DARK,
            text_color=FG_DIM, border_width=0, height=160)
        self.modes_box.pack(fill="x", padx=8, pady=(0, 12))
        self.modes_box.configure(state="disabled")

    def _build_right_panel(self, parent):
        ctk.CTkLabel(parent, text="AI ASSISTANT", font=("Consolas", 11, "bold"),
            text_color=ACCENT, anchor="w").pack(fill="x")
        self.chat_box = ctk.CTkScrollableFrame(parent, fg_color=BG_MID, corner_radius=8, label_text="")
        self.chat_box.pack(fill="both", expand=True, pady=(4, 8))
        ctk.CTkLabel(parent, text="SUGGESTED ACTIONS", font=("Consolas", 11, "bold"),
            text_color=ACCENT, anchor="w").pack(fill="x")
        self.actions_frame = ctk.CTkScrollableFrame(parent, fg_color=BG_MID, corner_radius=8, height=200, label_text="")
        self.actions_frame.pack(fill="x", pady=(4, 8))
        input_row = ctk.CTkFrame(parent, fg_color="transparent")
        input_row.pack(fill="x")
        self.msg_entry = ctk.CTkEntry(input_row, height=40,
            placeholder_text="Describe your display problem...",
            font=("Consolas", 12), fg_color=BG_MID, border_color=ACCENT, text_color=FG_MAIN)
        self.msg_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.msg_entry.bind("<Return>", lambda e: self._send_message())
        self.send_btn = ctk.CTkButton(input_row, text="Analyze", width=120, height=40,
            font=("Consolas", 12, "bold"), fg_color=ACCENT, hover_color=ACCENT2, command=self._send_message)
        self.send_btn.pack(side="right")

    def _refresh_snapshot(self):
        self._set_status("Collecting system display info...")
        def _run():
            try:
                snap = self.dm.get_full_system_snapshot()
                self.snapshot = snap
                self.after(0, lambda: self._update_info_panel(snap))
            except Exception as e:
                log.error(f"Snapshot error: {e}")
                self.after(0, lambda: self._set_status(f"Snapshot error: {e}"))
        threading.Thread(target=_run, daemon=True).start()

    def _update_info_panel(self, snap: dict):
        pm = snap.get("primary_monitor", {})
        dpi = snap.get("dpi_info", {})
        lines = [
            f"OS:          {snap.get('os', 'N/A')}",
            f"Monitors:    {snap.get('monitor_count', '?')}",
            f"Resolution:  {pm.get('width', '?')}x{pm.get('height', '?')}",
            f"Refresh:     {pm.get('frequency', '?')} Hz",
            f"Bit Depth:   {pm.get('bit_depth', '?')} bpp",
            f"DPI:         {dpi.get('system_dpi', '?')}",
            f"Scale:       {dpi.get('scale_percent', '?')}%",
            f"Virtual:     {snap.get('virtual_desktop', {}).get('width', '?')}x{snap.get('virtual_desktop', {}).get('height', '?')}",
        ]
        gpu = snap.get("gpu_wmi", "")
        if gpu and gpu != "Unavailable":
            try:
                gdata = json.loads(gpu)
                if isinstance(gdata, list): gdata = gdata[0]
                lines += ["", "GPU:", f"  {gdata.get('Name', 'N/A')}", f"  Driver: {gdata.get('DriverVersion', 'N/A')}"]
            except Exception:
                pass
        self._set_textbox(self.info_box, "\n".join(lines))
        modes = snap.get("available_modes", [])
        mode_lines = [f"{m['width']}x{m['height']} @ {m['frequency']}Hz" for m in modes[:25]]
        self._set_textbox(self.modes_box, "\n".join(mode_lines) or "No modes found.")
        self._set_status("System snapshot updated.")

    def _send_message(self):
        msg = self.msg_entry.get().strip()
        if not msg:
            return
        if not self.engine:
            self._open_api_dialog()
            return
        self.msg_entry.delete(0, "end")
        self._add_chat_bubble("You", msg, is_user=True)
        self.send_btn.configure(state="disabled", text="Analyzing...")
        self._set_status("Sending to AI...")
        def _run():
            try:
                if not self.snapshot:
                    self.snapshot = self.dm.get_full_system_snapshot()
                result = self.engine.analyze(msg, self.snapshot) if len(self.engine.history) == 0 else self.engine.followup(msg)
                self.after(0, lambda: self._handle_ai_response(result))
            except anthropic.AuthenticationError:
                self.after(0, self._on_auth_error)
            except Exception as e:
                self.after(0, lambda: self._on_error(str(e)))
        threading.Thread(target=_run, daemon=True).start()

    def _handle_ai_response(self, result: dict):
        self.send_btn.configure(state="normal", text="Analyze")
        parts = []
        if d := result.get("diagnosis"): parts.append(f"DIAGNOSIS\n{d}")
        if e := result.get("explanation"): parts.append(f"EXPLANATION\n{e}")
        if w := result.get("warnings"): parts.append("WARNINGS\n" + "\n".join(f"  - {x}" for x in w))
        if f := result.get("follow_up"): parts.append(f"FOLLOW-UP\n{f}")
        if result.get("requires_restart"): parts.append("NOTE: A system restart may be required.")
        self._add_chat_bubble("AI Assistant", "\n\n".join(parts), is_user=False)
        for widget in self.actions_frame.winfo_children():
            widget.destroy()
        actions = result.get("actions", [])
        if actions:
            for i, act in enumerate(actions, 1):
                ActionCard(self.actions_frame, act, i, self._confirm_and_execute)
        else:
            ctk.CTkLabel(self.actions_frame, text="No automatic actions recommended. Clarify your issue above.",
                font=("Consolas", 11), text_color=FG_DIM).pack(pady=12)
        self._set_status(f"AI response received — {len(actions)} action(s) suggested.")

    def _confirm_and_execute(self, action: dict):
        risk = action.get("risk", "low")
        label = action.get("label", "this action")
        rev = "Reversible" if action.get("reversible") else "NOT REVERSIBLE"
        msg = f"Execute: {label}\n\nRisk: {risk.upper()}\n{rev}\n\nReason: {action.get('reason', '')}\n\nProceed?"
        if not messagebox.askyesno("Confirm Action", msg):
            return
        self._set_status(f"Executing: {label}...")
        def _run():
            ok, output = self.executor.execute(action)
            self.after(0, lambda: self._on_exec_result(ok, output, label))
        threading.Thread(target=_run, daemon=True).start()

    def _on_exec_result(self, ok: bool, output: str, label: str):
        self._add_chat_bubble("System", f"{'OK' if ok else 'FAILED'}: {label}\n{output}",
            is_user=False, color=SUCCESS if ok else DANGER)
        self._set_status(f"{'Success' if ok else 'Failed'}: {label}")
        if ok:
            self._refresh_snapshot()

    def _add_chat_bubble(self, sender: str, text: str, is_user: bool, color: str = None):
        bubble = ctk.CTkFrame(self.chat_box, fg_color=BG_DARK if is_user else BG_MID,
            corner_radius=8, border_width=1, border_color=ACCENT if is_user else BG_LIGHT)
        bubble.pack(fill="x", pady=4, padx=(40 if is_user else 0, 0 if is_user else 40))
        hdr = ctk.CTkFrame(bubble, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=(8, 2))
        ctk.CTkLabel(hdr, text=sender, font=("Consolas", 10, "bold"),
            text_color=color or (ACCENT if is_user else FG_DIM)).pack(side="left")
        ctk.CTkLabel(hdr, text=datetime.now().strftime("%H:%M:%S"),
            font=("Consolas", 9), text_color=BG_LIGHT).pack(side="right")
        ctk.CTkLabel(bubble, text=text, font=("Consolas", 11), text_color=FG_MAIN,
            anchor="nw", justify="left", wraplength=600).pack(fill="x", padx=10, pady=(0, 10))
        self.chat_box._parent_canvas.yview_moveto(1.0)

    def _set_textbox(self, box, text):
        box.configure(state="normal")
        box.delete("1.0", "end")
        box.insert("1.0", text)
        box.configure(state="disabled")

    def _set_status(self, msg):
        self.status_var.set(f"  {msg}")

    def _open_api_dialog(self):
        dlg = APIKeyDialog(self, self.cfg.get("api_key", ""))
        self.wait_window(dlg)
        if dlg.result:
            self.cfg["api_key"] = dlg.result
            save_config(self.cfg)
            self._init_engine()
            self._set_status("API key saved. AI engine ready.")

    def _reset_session(self):
        if self.engine:
            self.engine.reset()
        for w in self.chat_box.winfo_children():
            w.destroy()
        for w in self.actions_frame.winfo_children():
            w.destroy()
        self._set_status("Session reset.")

    def _on_auth_error(self):
        self.send_btn.configure(state="normal", text="Analyze")
        messagebox.showerror("Auth Error", "Invalid API key.")
        self._open_api_dialog()

    def _on_error(self, msg: str):
        self.send_btn.configure(state="normal", text="Analyze")
        self._add_chat_bubble("Error", msg, is_user=False, color=DANGER)
        self._set_status(f"Error: {msg}")

def main():
    if sys.platform == "win32":
        try:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin()
        except Exception:
            is_admin = False
        if not is_admin:
            params = " ".join(f'"{a}"' for a in sys.argv)
            ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
            if ret > 32:
                sys.exit(0)
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = App()
    app.mainloop()

if __name__ == "__main__":
    main()
