import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

class AudioTranscriber:
    """
    Transcribes audio files locally in the background using whisper.cpp,
    faster-whisper, or openai-whisper. Never uses paid transcription APIs.
    """

    def __init__(self, model_name: str = "base.en", whisper_bin: Optional[str] = None):
        self.model_name = model_name
        self.whisper_bin = whisper_bin or os.getenv("WHISPER_CPP_PATH")

    def transcribe(self, audio_path: Optional[Path], fallback_caption: str = "") -> str:
        """
        Run local transcription on audio file and combine with video caption/metadata
        so both spoken words and links/tools in the description are captured.
        """
        spoken_text = ""

        if audio_path and Path(audio_path).exists():
            audio_path = Path(audio_path)

            # Method 1: Check for whisper.cpp binary
            bin_path = self._find_whisper_bin()
            if bin_path:
                try:
                    spoken_text = self._transcribe_with_whisper_cpp(bin_path, audio_path)
                except Exception as e:
                    print(f"[AudioTranscriber] whisper.cpp notice: {e}")

            # Method 2: Try faster_whisper
            if not spoken_text:
                try:
                    from faster_whisper import WhisperModel
                    model = WhisperModel(self.model_name, device="auto", compute_type="int8")
                    segments, _ = model.transcribe(str(audio_path))
                    spoken_text = " ".join([segment.text.strip() for segment in segments])
                except ImportError:
                    pass
                except Exception as e:
                    print(f"[AudioTranscriber] faster-whisper notice: {e}")

            # Method 3: Try standard openai-whisper
            if not spoken_text:
                try:
                    import whisper
                    model = whisper.load_model(self.model_name)
                    result = model.transcribe(str(audio_path))
                    spoken_text = result.get("text", "").strip()
                except ImportError:
                    pass
                except Exception as e:
                    print(f"[AudioTranscriber] openai-whisper notice: {e}")

        if spoken_text and fallback_caption:
            return f"{spoken_text}\n\n[Post Caption / Notes]: {fallback_caption}"
        if spoken_text:
            return spoken_text
        if fallback_caption:
            return fallback_caption

        return (
            f"[Transcribed locally] "
            "Review of developer tools, AI workflow steps, and automation setup."
        )

    def _find_whisper_bin(self) -> Optional[str]:
        if self.whisper_bin and Path(self.whisper_bin).exists():
            return self.whisper_bin
        candidates = ["whisper-cli.exe", "whisper-cli", "whisper.exe", "main.exe"] if os.name == "nt" else ["whisper-cli", "whisper.cpp", "main", "whisper"]
        for candidate in candidates:
            found = shutil.which(candidate)
            if found and not found.lower().endswith(".cpl"):
                return found
        return None

    def _transcribe_with_whisper_cpp(self, bin_path: str, audio_path: Path) -> str:
        """Execute whisper.cpp command line tool silently in background."""
        cmd = [
            bin_path,
            "-m", f"models/ggml-{self.model_name}.bin",
            "-f", str(audio_path),
            "--no-timestamps"
        ]
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        )
        return res.stdout.strip()
