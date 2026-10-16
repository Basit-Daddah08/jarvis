# ELION (JARVIS): Private Background Video Vault & Transcription Software

> Built for **ELION** by Awodeyi Ayoolamikun.  
> **ELION** is a private background software tool that lives on your laptop, connects seamlessly to your mobile apps (Instagram, TikTok, YouTube), and automatically transcribes your saved videos in the background using local Whisper models.

---

## 1. How It Works (Zero Interruption — Never Leave Your App)

You **never** have to leave Instagram, TikTok, or YouTube to use ELION. While you scroll on your phone or laptop, ELION runs silently in the background on your laptop and captures your saves in **3 automatic ways**:

1. **Native Instagram "Save" (Bookmark) Sync**:
   - Just tap the normal **Bookmark / Save** icon inside Instagram on your phone.
   - ELION's background daemon periodically checks your Saved collection, downloads **audio only**, transcribes it locally with Whisper, and deletes the temporary audio file.
2. **Silent In-App Mobile Share Webhook (`<10ms`)**:
   - Point an iOS Shortcut or Android "HTTP Share" shortcut to your laptop's background webhook:  
     `http://<YOUR-LAPTOP-IP>:8080/api/webhook/save?url=`
   - When you tap **Share $\rightarrow$ Save to ELION** inside Instagram or TikTok, it sends the link silently in the background in 10ms—**you stay right inside Instagram without switching apps.**
3. **Cross-Device Clipboard Auto-Capture**:
   - Tap **"Copy Link"** inside Instagram, TikTok, or YouTube (works across your phone and laptop via Windows Phone Link / Cross-Device Copy-Paste).
   - ELION's background clipboard watcher detects the video link automatically and starts transcribing in the background.

---

## 2. Running ELION Invisibly in the Background (No Terminal Needed)

ELION is built as a **Windows background daemon**:

- **Start Invisibly Right Now:**  
  Double-click **`start_elion_background.vbs`** (starts the daemon in the background with **zero** PowerShell/CMD windows).
- **Auto-Start When Laptop Turns On:**  
  Double-click **`install_autostart.bat`** once. ELION will automatically start in the background every time you boot your laptop.
- **Stop the Background Daemon:**  
  Double-click **`stop_elion_background.bat`**.

---

## 3. Private Control Center & Vault Viewer

Whenever you want to read your transcribed notes, review quarantined GitHub skills, or check the background daemon's activity log, open your browser to:

👉 **`http://localhost:8080`** *(or `http://<YOUR-LAPTOP-IP>:8080` from your phone on Wi-Fi)*

- **Live Daemon Bar:** Shows real-time background status (`Idle`, `Extracting audio...`, `Transcribing...`).
- **Today's INBOX & Library:** Browse all auto-transcribed notes filtered by `Tools`, `AI`, or `Other`.
- **1-Tap Skill Quarantine Approvals:** Approve or reject tools containing executable code.
- **Ask Your Vault (MCP + Chat):** Ask *"What tools did we save this week?"* from the Control Center or via Claude Code MCP (`src/mcp/server.py`).

---

## 4. Architecture

```
jarvis/
├── start_elion_background.vbs      # Launches daemon invisibly (no terminal window)
├── install_autostart.bat           # Registers ELION in Windows Startup
├── stop_elion_background.bat       # Stops the background daemon cleanly
├── run_nightly.bat                 # One-shot batch runner for Task Scheduler
├── config.toml                     # Daemon settings, spend cap ($1.00), pacing
├── .env.example                    # Optional Instagram session & LLM keys
├── src/
│   ├── daemon.py                   # Core Background Software Engine (ElionDaemon)
│   ├── fetch/
│   │   ├── media_extractor.py      # Background audio-only stream downloader (yt-dlp)
│   │   ├── clipboard_watcher.py    # Cross-device clipboard URL detector
│   │   ├── instagram_adapter.py    # Background Instagram Saved folder poller
│   │   └── manual_adapter.py       # Drop folder & webhook queue adapter
│   ├── transcribe/
│   │   └── transcriber.py          # Local Whisper audio transcription + caption fusion
│   ├── classify/                   # Keyword rules ($0) + spend-capped LLM fallback
│   ├── notes/                      # Obsidian-compatible Markdown & INBOX.md writer
│   ├── skills/                     # Code quarantine & prompt-injection inspector
│   ├── mcp/                        # Claude Code MCP stdio server & /saved CLI
│   └── dashboard/                  # Local Control Center & Mobile Share Webhook server
├── vault/
│   ├── notes/                      # One Markdown note per transcribed video
│   ├── INBOX.md                    # Daily chronological digest
│   ├── approvals/                  # Quarantined skills awaiting your OK
│   └── drop/                       # Optional drag-and-drop folder
└── state/
    ├── daemon_status.json          # Live background daemon state & event log
    ├── processed.json              # Idempotency log (never processes twice)
    └── spend.json                  # Daily AI spend counter
```
