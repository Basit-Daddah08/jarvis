# ELION (JARVIS): Private Background Software — Overview & Roadmap

> **Owner:** Awodeyi Ayoolamikun  
> **Team:** ELION Friend Group  
> **Type:** Private Laptop Background Software Daemon + Mobile Integration  

---

## 1. Core Design Philosophy

1. **Never Leave the App You Are Using:**  
   When scrolling Instagram, TikTok, or YouTube on your phone, you should **never** have to switch apps or open a browser to save a video. You just save/share inside the app you're already using.
2. **A Private Background Software Tool (Not a Public Consumer App):**  
   ELION lives quietly on your laptop as a background daemon (`src/daemon.py`). It runs invisibly in the background (`start_elion_background.vbs`), watches your saves, downloads **audio only**, and transcribes videos locally using Whisper.
3. **Zero-Friction Mobile Compatibility:**  
   Your phone integrates with your laptop daemon in three ways without interrupting your scrolling:
   - **Native Instagram Bookmark Sync:** Tap the normal *Save* icon inside Instagram; the laptop daemon pulls your Saved folder in the background.
   - **Silent In-App Share Sheet Webhook (`<10ms`):** Tap *Share $\rightarrow$ Save to ELION* via iOS Shortcut / Android HTTP Share. It hits `http://<LAPTOP-IP>:8080/api/webhook/save?url=` silently in the background without opening any window.
   - **Cross-Device Clipboard Auto-Capture:** Tap *Copy Link* on your phone (synced via Windows Phone Link / Universal Clipboard) or laptop; the background daemon detects the video URL automatically and transcribes it.

---

## 2. How the Background Software Works

```
[Inside Instagram / TikTok / YouTube on Phone]
   │
   ├── Option A: Tap native "Save" (Bookmark) inside Instagram
   ├── Option B: Tap "Share -> Save to ELION" (Silent background webhook)
   └── Option C: Tap "Copy Link" (Cross-device clipboard watcher)
   │
   ▼
[ELION Laptop Background Daemon (src/daemon.py)]
   │  (Runs invisibly on Windows via start_elion_background.vbs)
   ▼
[Background Audio-Only Extractor (src/fetch/media_extractor.py)]
   │  (Uses yt-dlp / instaloader to fetch audio stream to tmp/, never keeps video)
   ▼
[Local Whisper Transcriber (src/transcribe/transcriber.py)]
   │  (Transcribes audio locally for $0 + merges post caption/links, then deletes tmp audio)
   ▼
[Two-Stage Classifier (src/classify/)]
   ├── AI / Tool Video ──> Summary + Step-by-Step Checklist + Extracted Tools
   │                              │
   │                              ▼
   │                    [GitHub Skill Inspector (src/skills/)]
   │                    (Quarantines any code in vault/approvals/)
   │
   └── Everything Else ──> Full Verbatim Transcript
   │
   ▼
[Markdown Vault (vault/notes/*.md + vault/INBOX.md)]
   ├── Query via Claude Code MCP (src/mcp/server.py)
   └── Inspect via Local Control Center (http://localhost:8080)
```

---

## 3. How to Run It

### A. Run Silently in the Windows Background (Recommended)
- Double-click **`start_elion_background.vbs`** to start ELION invisibly with **zero** terminal windows.
- Or double-click **`install_autostart.bat`** once so ELION starts automatically in the background every time you turn on your laptop.
- To stop the background daemon at any time, double-click **`stop_elion_background.bat`**.

### B. Open the Local Control Center
While the daemon is running in the background, open **`http://localhost:8080`** on your laptop (or `http://<YOUR-LAPTOP-IP>:8080` on your phone over Wi-Fi) to:
- View real-time background daemon status & activity logs.
- Browse transcribed notes (`All`, `Tools`, `AI`, `Other`).
- Approve or reject quarantined GitHub skills with 1 click.
- Ask questions about your vault in the **Ask** tab.

---

## 4. What Is Completed

- [x] **Background Software Daemon (`src/daemon.py`)**: Continuous multi-threaded background worker watching the mobile webhook queue, clipboard, drop folder, and Instagram Saved collection.
- [x] **Invisible Windows Launchers**: `start_elion_background.vbs`, `install_autostart.bat`, and `stop_elion_background.bat`.
- [x] **Real Background Audio Extraction (`src/fetch/media_extractor.py`)**: Uses `yt-dlp` and `instaloader` to pull audio-only streams and post metadata automatically.
- [x] **Zero-Interruption Mobile Compatibility**:
  - Silent `<10ms` webhook (`GET/POST /api/webhook/save`).
  - Cross-device clipboard auto-watcher (`src/fetch/clipboard_watcher.py`).
  - Paced Instagram Saved folder background sync (`src/fetch/instagram_adapter.py`).
- [x] **Local Whisper Transcription + Caption Fusion (`src/transcribe/transcriber.py`)**.
- [x] **Two-Stage Classifier & Spend Cap (`src/classify/`, `state/spend.json`)**.
- [x] **GitHub Skill Quarantine & Prompt Injection Scanner (`src/skills/`)**.
- [x] **Claude Code MCP Server (`src/mcp/server.py`) & Control Center UI (`src/dashboard/`)**.
- [x] **16 Automated Unit Tests (`tests/`)**: All 16 tests passing.

---

## 5. What Still Needs to Be Done (Next Steps for Deployment)

1. **Download Local `whisper.cpp` Model Weights (`ggml-base.en.bin`)**:
   - Place the `whisper-cli.exe` binary and `models/ggml-base.en.bin` into the project folder (or `pip install faster-whisper`) so offline audio transcription runs at maximum speed on your laptop CPU/GPU.
2. **Add `.env` Instagram Session Cookie (Optional for Native Bookmark Sync)**:
   - Copy `.env.example` to `.env` and add `INSTAGRAM_USERNAME` and `INSTAGRAM_SESSION_ID` (or set `browser_cookies = "edge"` / `"chrome"` in `config.toml`) to enable automatic Instagram Saved folder polling.
3. **One-Time iOS Shortcut / Android HTTP Share Setup (2 minutes)**:
   - On iPhone: Create a 1-action Shortcut ("Get Contents of URL" $\rightarrow$ `http://<LAPTOP-IP>:8080/api/webhook/save?url=[Shortcut Input]`) and enable *Show in Share Sheet*.
   - On Android: Use the free *HTTP Shortcuts* app to add "Save to ELION" to your native Android Share menu, or simply use "Copy Link" with Windows Phone Link clipboard sync enabled.
4. **Tailscale (Optional for Out-of-Home Mobile Sync)**:
   - Install free **Tailscale** on your laptop and phone so your phone's in-app Share webhook reaches your laptop's background daemon even when you're on mobile data away from home Wi-Fi.
