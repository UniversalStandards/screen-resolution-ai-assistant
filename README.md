# Screen Resolution AI Assistant
**v1.0.0 — Civilian Edition | Powered by Claude AI**

> AI-driven Windows display diagnostic and repair tool. Describe your screen problem in plain English — the AI diagnoses it, proposes an ordered fix plan, and executes changes directly on your system.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows%2010%2F11-blue)]()
[![Powered by Claude](https://img.shields.io/badge/AI-Claude%20(Anthropic)-orange)](https://anthropic.com)

---

## What it does

A standalone Windows desktop app that:
- Collects a full display system snapshot (resolution, DPI, refresh rate, GPU info, all available modes, monitor count, virtual desktop size)
- Lets you describe your display problem in plain English via a chat interface
- Sends the problem + snapshot to Claude AI for diagnosis
- Returns a structured, ordered fix plan with risk ratings for each step
- Executes each fix with your explicit per-step approval

---

## Quick Start

### Prerequisites
- Windows 10/11 (64-bit)
- Python 3.10+ from https://python.org
- Anthropic API key from https://console.anthropic.com

### Build the EXE

```bat
# 1. Extract the project folder
# 2. Double-click build.bat
# 3. Wait 2-4 minutes for compilation
# 4. Run dist\ScreenResAI.exe
```

### First Run
1. Windows will prompt for admin elevation — approve it
2. Click **API Key** and paste your Anthropic key
3. Type your display issue in the chat box → **Analyze**

---

## Capabilities

| Feature | Implementation |
|---|---|
| Resolution change | `ChangeDisplaySettingsW` (native Win32 API) |
| Refresh rate change | `ChangeDisplaySettingsW` on frequency field |
| DPI / Scaling | Registry write to `HKCU\Control Panel\Desktop` |
| GPU driver restart | `Win+Ctrl+Shift+B` keystroke signal |
| Font cache flush | Stops/clears/restarts `FontCache` Windows service |
| ClearType toggle | Registry + `SystemParametersInfoW` |
| PowerShell commands | Arbitrary PS1 with `-ExecutionPolicy Bypass` |
| Open Settings panels | `ms-settings:display` etc. via `os.startfile` |

---

## Architecture

```
App (CTk GUI)
├── DisplayManager      # ctypes + winreg + PowerShell
│   ├── get_full_system_snapshot()
│   ├── set_resolution() / set_refresh_rate() / set_dpi_scaling()
│   ├── restart_graphics_driver() / clear_font_cache()
│   └── run_powershell()
├── AIEngine            # Anthropic API + conversation history
│   ├── analyze(user_message, snapshot) → ActionPlan
│   └── followup(user_message) → ActionPlan
└── ActionExecutor      # Routes ActionPlan steps to DisplayManager
```

---

## File Locations

| Path | Contents |
|---|---|
| `%APPDATA%\ScreenResAI\config.json` | API key + preferences |
| `%APPDATA%\ScreenResAI\assistant.log` | Full debug log |

---

## Example Problems it Can Solve

- *"Screen is blurry after connecting a 4K monitor"*
- *"Resolution resets to 1024x768 every time I reboot"*
- *"Everything looks tiny on my new 27-inch display"*
- *"Games run at wrong aspect ratio"*
- *"Second monitor shows wrong resolution and I can't change it"*
- *"Text is fuzzy / ClearType not working"*
- *"Refresh rate stuck at 60Hz but monitor supports 144Hz"*

---

## Security

- API key stored locally in `%APPDATA%\ScreenResAI\config.json`
- UAC elevation requested at launch for registry/driver access
- Every action card shows risk level + reversibility before execution
- Nothing executes without your explicit click

---

## License

MIT — see [LICENSE](LICENSE)
