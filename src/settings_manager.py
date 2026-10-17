import os
import shutil
import tomllib
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.toml"
ENV_PATH = PROJECT_ROOT / ".env"
STARTUP_DIR = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
STARTUP_VBS_DEST = STARTUP_DIR / "ELION_Background_Daemon.vbs"
SOURCE_VBS = PROJECT_ROOT / "start_elion_background.vbs"

class SystemSettingsManager:
    """
    Unified settings manager for ELION.
    Manages both config.toml and .env, allowing zero-code UI administration
    without touching batch scripts, terminal commands, or text editors.
    """

    @staticmethod
    def get_settings(daemon=None) -> dict:
        config = {}
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, "rb") as f:
                    config = tomllib.load(f)
            except Exception:
                pass

        daemon_cfg = config.get("daemon", {})
        limits_cfg = config.get("limits", {})
        fetch_cfg = config.get("fetch", {})
        transcribe_cfg = config.get("transcribe", {})
        safety_cfg = config.get("safety", {})
        ai_cfg = config.get("ai", {})

        autostart_active = STARTUP_VBS_DEST.exists()
        clipboard_active = daemon.clipboard_enabled if daemon and hasattr(daemon, "clipboard_enabled") else daemon_cfg.get("watch_clipboard", True)
        phone_active = daemon.phone_share_enabled if daemon and hasattr(daemon, "phone_share_enabled") else daemon_cfg.get("phone_share_enabled", True)

        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        openai_key = os.getenv("OPENAI_API_KEY", "")
        gemini_key = os.getenv("GEMINI_API_KEY", "")
        ig_user = os.getenv("INSTAGRAM_USERNAME", "")
        ig_session = os.getenv("INSTAGRAM_SESSION_ID", "")

        return {
            "autostart_on_boot": autostart_active,
            "watch_clipboard": clipboard_active,
            "phone_share_enabled": phone_active,
            "instagram_sync_enabled": daemon_cfg.get("instagram_sync_enabled", False),
            "instagram_poll_minutes": daemon_cfg.get("instagram_poll_minutes", 30),
            "cleanup_audio_after_transcription": fetch_cfg.get("cleanup_audio_after_transcription", True),
            "share_to_download_enabled": fetch_cfg.get("share_to_download_enabled", False),
            "transcription_engine": transcribe_cfg.get("engine", "whisper_cpp"),
            "transcription_model": transcribe_cfg.get("model", "base.en"),
            "daily_spend_cap_usd": limits_cfg.get("daily_spend_cap_usd", 1.00),
            "queue_markdown_skills": safety_cfg.get("queue_markdown_skills", True),
            "bind_address": daemon_cfg.get("bind_address", "127.0.0.1"),
            "allow_tailscale": daemon_cfg.get("allow_tailscale", False),
            "ai_provider": ai_cfg.get("provider", "claude"),
            "ollama_endpoint": ai_cfg.get("ollama_endpoint", "http://localhost:11434"),
            "ollama_model": ai_cfg.get("ollama_model", "llama3.2"),
            "has_anthropic_key": bool(anthropic_key),
            "has_openai_key": bool(openai_key),
            "has_gemini_key": bool(gemini_key),
            "instagram_username": ig_user,
            "has_instagram_session": bool(ig_session)
        }

    @staticmethod
    def set_autostart(enable: bool) -> bool:
        """Toggle automatic startup on Windows boot without running .bat files."""
        try:
            if enable:
                if SOURCE_VBS.exists() and STARTUP_DIR.exists():
                    shutil.copy2(SOURCE_VBS, STARTUP_VBS_DEST)
                    return True
            else:
                if STARTUP_VBS_DEST.exists():
                    STARTUP_VBS_DEST.unlink()
                    return True
        except Exception as e:
            print(f"[SystemSettingsManager] Autostart error: {e}")
        return False

    @staticmethod
    def update_env_value(key: str, value: str):
        """Update or add an environment variable to .env and active os.environ."""
        val_clean = str(value).strip()
        os.environ[key] = val_clean

        env_lines = []
        if ENV_PATH.exists():
            try:
                env_lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
            except Exception:
                pass

        updated = False
        new_lines = []
        for line in env_lines:
            stripped = line.strip()
            if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} ="):
                new_lines.append(f"{key}={val_clean}")
                updated = True
            else:
                new_lines.append(line)

        if not updated:
            new_lines.append(f"{key}={val_clean}")

        ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    @staticmethod
    def update_config_value(section: str, key: str, value):
        """Update a specific setting inside config.toml cleanly."""
        if not CONFIG_PATH.exists():
            return

        text = CONFIG_PATH.read_text(encoding="utf-8")
        lines = text.splitlines()
        current_section = None
        updated = False
        new_lines = []

        formatted_val = str(value).lower() if isinstance(value, bool) else (f'"{value}"' if isinstance(value, str) else str(value))

        for line in lines:
            trimmed = line.strip()
            if trimmed.startswith("[") and trimmed.endswith("]"):
                current_section = trimmed[1:-1].strip()
            elif current_section == section and "=" in line:
                k = line.split("=")[0].strip()
                if k == key:
                    new_lines.append(f"{key} = {formatted_val}")
                    updated = True
                    continue
            new_lines.append(line)

        if not updated:
            final_lines = []
            current_section = None
            added = False
            for line in new_lines:
                trimmed = line.strip()
                if trimmed.startswith("[") and trimmed.endswith("]"):
                    if current_section == section and not added:
                        final_lines.append(f"{key} = {formatted_val}")
                        added = True
                    current_section = trimmed[1:-1].strip()
                final_lines.append(line)
            if current_section == section and not added:
                final_lines.append(f"{key} = {formatted_val}")
                added = True
            new_lines = final_lines

        CONFIG_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    @classmethod
    def save_all_settings(cls, payload: dict, daemon=None) -> dict:
        """
        Applies a full settings payload from the Dashboard Settings UI:
        persists to config.toml, .env, and modifies running daemon state.
        """
        # 1. Daemon toggles
        if "watch_clipboard" in payload:
            val = bool(payload["watch_clipboard"])
            cls.update_config_value("daemon", "watch_clipboard", val)
            if daemon and hasattr(daemon, "set_clipboard_active"):
                daemon.set_clipboard_active(val)

        if "phone_share_enabled" in payload:
            val = bool(payload["phone_share_enabled"])
            cls.update_config_value("daemon", "phone_share_enabled", val)
            if daemon and hasattr(daemon, "phone_share_enabled"):
                daemon.phone_share_enabled = val

        if "instagram_sync_enabled" in payload:
            val = bool(payload["instagram_sync_enabled"])
            cls.update_config_value("daemon", "instagram_sync_enabled", val)

        if "instagram_poll_minutes" in payload:
            try:
                val = int(payload["instagram_poll_minutes"])
                cls.update_config_value("daemon", "instagram_poll_minutes", val)
            except (ValueError, TypeError):
                pass

        if "allow_tailscale" in payload:
            val = bool(payload["allow_tailscale"])
            cls.update_config_value("daemon", "allow_tailscale", val)

        # 2. Windows Autostart
        if "autostart_on_boot" in payload:
            cls.set_autostart(bool(payload["autostart_on_boot"]))

        # 3. Audio & Transcription
        if "cleanup_audio_after_transcription" in payload:
            val = bool(payload["cleanup_audio_after_transcription"])
            cls.update_config_value("fetch", "cleanup_audio_after_transcription", val)

        if "share_to_download_enabled" in payload:
            val = bool(payload["share_to_download_enabled"])
            cls.update_config_value("fetch", "share_to_download_enabled", val)
            if daemon and hasattr(daemon, "config"):
                if "fetch" not in daemon.config:
                    daemon.config["fetch"] = {}
                daemon.config["fetch"]["share_to_download_enabled"] = val

        if "transcription_engine" in payload:
            eng = str(payload["transcription_engine"]).strip()
            if eng in ("whisper_cpp", "faster_whisper", "python_whisper"):
                cls.update_config_value("transcribe", "engine", eng)

        if "transcription_model" in payload:
            mod = str(payload["transcription_model"]).strip()
            cls.update_config_value("transcribe", "model", mod)

        # 4. Limits & Spend Cap
        if "daily_spend_cap_usd" in payload:
            try:
                cap = float(payload["daily_spend_cap_usd"])
                cls.update_config_value("limits", "daily_spend_cap_usd", cap)
                if daemon and hasattr(daemon, "state_mgr"):
                    daemon.state_mgr.daily_spend_cap = cap
            except (ValueError, TypeError):
                pass

        # 5. AI Provider settings
        if "ai_provider" in payload:
            prov = str(payload["ai_provider"]).strip().lower()
            if prov in ("claude", "openai", "gemini", "ollama", "none"):
                cls.update_config_value("ai", "provider", prov)
                if daemon and hasattr(daemon, "classifier"):
                    daemon.classifier = daemon.classifier.__class__(
                        state_manager=daemon.state_mgr,
                        provider=prov
                    )

        if "ollama_endpoint" in payload:
            cls.update_config_value("ai", "ollama_endpoint", str(payload["ollama_endpoint"]).strip())

        if "ollama_model" in payload:
            cls.update_config_value("ai", "ollama_model", str(payload["ollama_model"]).strip())

        # 6. Credentials saved to .env
        if payload.get("anthropic_api_key"):
            cls.update_env_value("ANTHROPIC_API_KEY", payload["anthropic_api_key"])
        if payload.get("openai_api_key"):
            cls.update_env_value("OPENAI_API_KEY", payload["openai_api_key"])
        if payload.get("gemini_api_key"):
            cls.update_env_value("GEMINI_API_KEY", payload["gemini_api_key"])
        if "instagram_username" in payload:
            cls.update_env_value("INSTAGRAM_USERNAME", payload["instagram_username"])
        if payload.get("instagram_session_id"):
            cls.update_env_value("INSTAGRAM_SESSION_ID", payload["instagram_session_id"])

        return cls.get_settings(daemon)
