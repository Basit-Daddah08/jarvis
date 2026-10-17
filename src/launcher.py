import argparse
import ctypes
from ctypes import wintypes
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = PROJECT_ROOT / "state"
LOG_FILE = STATE_DIR / "daemon.log"
PID_FILE = STATE_DIR / "daemon.pid"
VBS_LAUNCHER = PROJECT_ROOT / "start_elion_background.vbs"
SERVE_SCRIPT = PROJECT_ROOT / "src" / "dashboard" / "serve.py"

STARTUP_FOLDER = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
STARTUP_DEST_VBS = STARTUP_FOLDER / "ELION_Background_Daemon.vbs"
TASK_SCHEDULER_NAME = "ELION_Background_Daemon"

DEFAULT_PORT = 8080

def get_venv_python(windowless: bool = True) -> Optional[Path]:
    """
    Locates the project's own virtual environment python.
    Prioritizes .venv/Scripts/pythonw.exe for windowless background execution.
    Never relies on whatever python is on the global system PATH.
    """
    scripts_dir = PROJECT_ROOT / ".venv" / "Scripts"
    if not scripts_dir.exists():
        # Also check unix-style venv (.venv/bin)
        scripts_dir = PROJECT_ROOT / ".venv" / "bin"

    if not scripts_dir.exists():
        return None

    if windowless:
        pythonw = scripts_dir / "pythonw.exe"
        if pythonw.exists():
            return pythonw

    python_exe = scripts_dir / ("python.exe" if sys.platform == "win32" else "python")
    if python_exe.exists():
        return python_exe

    return None

def show_error_notification(title: str, message: str, timeout_seconds: int = 15):
    """
    Displays an error dialog on Windows desktop with an error icon,
    ensuring notifications are visible even when no console window is open.
    Automatically times out after timeout_seconds so it never hangs indefinitely.
    """
    # 1. Log error to daemon.log
    log_message(f"[ERROR NOTIFICATION] {title}: {message}")

    if sys.platform == "win32":
        try:
            user32 = ctypes.windll.user32
            # 0x10 = MB_ICONERROR, 0x40000 = MB_TOPMOST, 0x0 = MB_OK
            u_type = 0x10 | 0x40000
            if hasattr(user32, "MessageBoxTimeoutW"):
                user32.MessageBoxTimeoutW.argtypes = [
                    wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR,
                    wintypes.UINT, wintypes.WORD, wintypes.DWORD
                ]
                user32.MessageBoxTimeoutW(
                    None,
                    message,
                    title,
                    u_type,
                    0,
                    int(timeout_seconds * 1000)
                )
                return
            else:
                user32.MessageBoxW(None, message, title, u_type)
                return
        except Exception:
            pass

        # Fallback via PowerShell
        try:
            clean_msg = message.replace("'", "''").replace("\n", "`n")
            ps_cmd = f"""
            Add-Type -AssemblyName System.Windows.Forms
            [System.Windows.Forms.MessageBox]::Show('{clean_msg}', '{title}', [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error)
            """
            subprocess.run(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_cmd],
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
                timeout=timeout_seconds + 2
            )
        except Exception:
            pass

def log_message(msg: str):
    """Appends a timestamped message to state/daemon.log."""
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass

def get_last_log_lines(n: int = 10) -> str:
    """Reads the last n lines from state/daemon.log."""
    if not LOG_FILE.exists():
        return ""
    try:
        lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-n:])
    except Exception:
        return ""

def is_pid_alive(pid: int) -> bool:
    """Checks whether a process with given PID is currently active."""
    if pid <= 0:
        return False

    if sys.platform == "win32":
        try:
            kernel32 = ctypes.windll.kernel32
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            h_proc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if h_proc:
                code = wintypes.DWORD()
                kernel32.GetExitCodeProcess(h_proc, ctypes.byref(code))
                kernel32.CloseHandle(h_proc)
                return code.value == 259  # STILL_ACTIVE
        except Exception:
            pass

    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False

def check_http_health(port: int = DEFAULT_PORT, timeout: float = 1.5) -> Tuple[bool, dict]:
    """Queries GET /api/daemon/status to verify the server is responding."""
    url = f"http://127.0.0.1:{port}/api/daemon/status"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ElionLauncher/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return True, data
    except Exception:
        pass
    return False, {}

def get_running_daemon_pid() -> Optional[int]:
    """Reads PID from state/daemon.pid and checks if process is actually running."""
    if not PID_FILE.exists():
        return None
    try:
        raw = PID_FILE.read_text(encoding="utf-8").strip()
        if raw.isdigit():
            pid = int(raw)
            if is_pid_alive(pid):
                return pid
    except Exception:
        pass
    return None

def start_daemon(background: bool = True, port: int = DEFAULT_PORT) -> int:
    """
    Starts the ELION background daemon using the project's own venv Python.
    Verifies that the process starts cleanly, redirects output to state/daemon.log,
    and shows an error notification if startup fails.
    """
    existing_pid = get_running_daemon_pid()
    healthy, status_data = check_http_health(port=port)
    if existing_pid and healthy:
        print(f"[*] ELION daemon is already running (PID: {existing_pid}).")
        print(f"[*] Control Center: http://127.0.0.1:{port}")
        return 0

    venv_python = get_venv_python(windowless=background)
    if not venv_python or not venv_python.exists():
        err = (
            f"ELION cannot start in the background:\n\n"
            f"The project's virtual environment (.venv) was not found at:\n"
            f"{PROJECT_ROOT / '.venv'}\n\n"
            f"Please run setup.bat in the project directory first to create the venv."
        )
        print(f"[ERROR] {err}")
        show_error_notification("ELION Daemon Startup Error", err)
        return 1

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    log_message(f"--- Launching ELION daemon (background={background}) using {venv_python} ---")

    cmd = [str(venv_python), "-u", str(SERVE_SCRIPT)]

    creationflags = 0
    if sys.platform == "win32" and background:
        # DETACHED_PROCESS (0x8) and CREATE_NO_WINDOW (0x08000000)
        creationflags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS

    try:
        log_f = open(LOG_FILE, "a", encoding="utf-8")
        proc = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            stdout=log_f,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
            close_fds=(sys.platform != "win32")
        )
    except Exception as e:
        err = f"Failed to execute daemon process:\n{e}"
        print(f"[ERROR] {err}")
        show_error_notification("ELION Launch Error", err)
        return 1

    # Wait up to 3.5 seconds to verify successful startup
    success = False
    start_time = time.time()
    while time.time() - start_time < 3.5:
        # Check if process crashed immediately
        poll_res = proc.poll()
        if poll_res is not None:
            break

        # Check HTTP health
        healthy, _ = check_http_health(port=port, timeout=0.8)
        if healthy:
            success = True
            break
        time.sleep(0.3)

    if not success:
        last_logs = get_last_log_lines(8)
        err = (
            f"ELION daemon failed to start or crashed on launch.\n\n"
            f"Recent log output:\n{last_logs or 'No output recorded in log file.'}\n\n"
            f"Check {LOG_FILE} for full details."
        )
        print(f"[ERROR] {err}")
        show_error_notification("ELION Daemon Failed to Start", err)
        return 1

    # Write confirmed PID
    PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    log_message(f"[SUCCESS] ELION background daemon is active with PID {proc.pid}.")

    print("============================================================")
    print(" ELION (JARVIS) Background Software Daemon Started")
    print("============================================================")
    print(f" * Process PID         : {proc.pid}")
    print(f" * Python Binary       : {venv_python}")
    print(f" * Local Control Center: http://127.0.0.1:{port}")
    print(f" * Daemon Log File     : {LOG_FILE}")
    print("============================================================")
    return 0

def stop_daemon() -> int:
    """Stops the running ELION background daemon process."""
    pid = get_running_daemon_pid()
    if not pid:
        if PID_FILE.exists():
            PID_FILE.unlink(missing_ok=True)
        print("[*] ELION background daemon is not currently running.")
        return 0

    print(f"[*] Stopping ELION daemon process (PID: {pid})...")
    log_message(f"--- Stopping ELION daemon (PID: {pid}) ---")

    if sys.platform == "win32":
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        except Exception:
            pass
    else:
        try:
            os.kill(pid, 15)  # SIGTERM
            time.sleep(0.5)
            if is_pid_alive(pid):
                os.kill(pid, 9)  # SIGKILL
        except Exception:
            pass

    PID_FILE.unlink(missing_ok=True)
    log_message(f"[STOPPED] ELION daemon stopped.")
    print(f"[OK] ELION background daemon stopped successfully.")
    return 0

def get_autostart_status() -> dict:
    """Checks the auto-start registration in Startup Folder and Task Scheduler."""
    startup_enabled = STARTUP_DEST_VBS.exists()
    task_scheduler_enabled = False

    if sys.platform == "win32":
        try:
            res = subprocess.run(
                ["schtasks", "/query", "/tn", TASK_SCHEDULER_NAME],
                capture_output=True,
                text=True
            )
            task_scheduler_enabled = (res.returncode == 0)
        except Exception:
            pass

    return {
        "startup_folder": startup_enabled,
        "task_scheduler": task_scheduler_enabled,
        "is_enabled": startup_enabled or task_scheduler_enabled
    }

def set_autostart(enable: bool, use_task_scheduler: bool = False) -> int:
    """Configures automatic start on Windows login."""
    if not sys.platform == "win32":
        print("[*] Auto-start on login configuration is currently supported on Windows.")
        return 1

    if enable:
        if not VBS_LAUNCHER.exists():
            print(f"[ERROR] Launcher script not found: {VBS_LAUNCHER}")
            return 1

        # 1. Startup folder method (Preferred, zero admin privileges needed)
        try:
            STARTUP_FOLDER.mkdir(parents=True, exist_ok=True)
            shutil.copy2(VBS_LAUNCHER, STARTUP_DEST_VBS)
            print(f"[OK] Registered in Windows Startup folder:")
            print(f"     {STARTUP_DEST_VBS}")
        except Exception as e:
            print(f"[ERROR] Failed to write to Startup folder: {e}")
            return 1

        # 2. Optional Task Scheduler method
        if use_task_scheduler:
            try:
                cmd = f'schtasks /create /tn "{TASK_SCHEDULER_NAME}" /tr "wscript.exe \\"{VBS_LAUNCHER}\\"" /sc onlogon /f'
                res = subprocess.run(cmd, capture_output=True, text=True, shell=True)
                if res.returncode == 0:
                    print(f"[OK] Registered Task Scheduler task: {TASK_SCHEDULER_NAME}")
                else:
                    print(f"[WARN] Task Scheduler notice: {res.stderr.strip()}")
            except Exception as e:
                print(f"[WARN] Task Scheduler registration skipped: {e}")

        print("[SUCCESS] ELION will now launch automatically in the background whenever you log into Windows.")
        return 0

    else:
        # Disable auto-start
        removed = False
        if STARTUP_DEST_VBS.exists():
            try:
                STARTUP_DEST_VBS.unlink()
                print(f"[OK] Removed shortcut from Windows Startup folder.")
                removed = True
            except Exception as e:
                print(f"[ERROR] Could not remove startup file: {e}")

        try:
            subprocess.run(
                ["schtasks", "/delete", "/tn", TASK_SCHEDULER_NAME, "/f"],
                capture_output=True,
                text=True
            )
            removed = True
        except Exception:
            pass

        print("[OK] Auto-start on login has been disabled.")
        return 0

def status_daemon(port: int = DEFAULT_PORT) -> int:
    """Prints comprehensive health, process, and configuration status."""
    pid = get_running_daemon_pid()
    healthy, data = check_http_health(port=port)
    autostart = get_autostart_status()
    venv_python = get_venv_python(windowless=True)

    print("============================================================")
    print(" ELION (JARVIS) — Background Daemon Status")
    print("============================================================")

    if pid and healthy:
        print(f" Status             : RUNNING (Active)")
        print(f" Process PID        : {pid}")
        print(f" Local Control Center: http://127.0.0.1:{port}")
        print(f" Current Task       : {data.get('current_task', 'Active')}")
        print(f" Queue Size         : {data.get('queue_size', 0)} pending")
        print(f" Total Processed    : {data.get('total_processed_all_time', 0)} saves")
        print(f" Clipboard Watcher  : {'ACTIVE' if data.get('clipboard_watcher_active') else 'PAUSED'}")
    elif pid and not healthy:
        print(f" Status             : STALLED / STARTING (PID {pid} alive, port {port} unresponsive)")
    else:
        print(f" Status             : STOPPED (Not running)")

    print(f" Venv Python Binary : {venv_python or 'NOT FOUND (run setup.bat)'}")
    print(f" Auto-start on Login: {'ENABLED' if autostart['is_enabled'] else 'DISABLED'}")
    if autostart['startup_folder']:
        print(f"   * Startup Folder : ACTIVE ({STARTUP_DEST_VBS.name})")
    if autostart['task_scheduler']:
        print(f"   * Task Scheduler : ACTIVE ({TASK_SCHEDULER_NAME})")

    print(f" Daemon Log File    : {LOG_FILE}")
    print("============================================================")
    return 0 if (pid and healthy) else (1 if pid else 2)

def main():
    parser = argparse.ArgumentParser(description="ELION (JARVIS) Windows Background Service Manager")
    subparsers = parser.add_subparsers(dest="command")

    start_p = subparsers.add_parser("start", help="Start ELION background daemon")
    start_p.add_argument("--foreground", action="store_true", help="Run in foreground instead of detached background")
    start_p.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to listen on")

    stop_p = subparsers.add_parser("stop", help="Stop ELION background daemon")

    status_p = subparsers.add_parser("status", help="Check daemon status and health")
    status_p.add_argument("--port", type=int, default=DEFAULT_PORT, help="Daemon port")

    restart_p = subparsers.add_parser("restart", help="Restart ELION background daemon")
    restart_p.add_argument("--port", type=int, default=DEFAULT_PORT, help="Daemon port")

    auto_p = subparsers.add_parser("autostart", help="Configure auto-start on Windows login")
    auto_p.add_argument("action", choices=["enable", "disable", "status"], default="status", nargs="?")
    auto_p.add_argument("--task-scheduler", action="store_true", help="Also register in Windows Task Scheduler")

    args = parser.parse_args()

    if args.command == "start" or not args.command:
        sys.exit(start_daemon(background=not getattr(args, "foreground", False), port=getattr(args, "port", DEFAULT_PORT)))
    elif args.command == "stop":
        sys.exit(stop_daemon())
    elif args.command == "status":
        sys.exit(status_daemon(port=getattr(args, "port", DEFAULT_PORT)))
    elif args.command == "restart":
        stop_daemon()
        time.sleep(1)
        sys.exit(start_daemon(background=True, port=getattr(args, "port", DEFAULT_PORT)))
    elif args.command == "autostart":
        action = args.action
        if action == "enable":
            sys.exit(set_autostart(True, use_task_scheduler=args.task_scheduler))
        elif action == "disable":
            sys.exit(set_autostart(False))
        else:
            status = get_autostart_status()
            print(f"Auto-start on Login: {'ENABLED' if status['is_enabled'] else 'DISABLED'}")
            print(f"  Startup folder : {'YES' if status['startup_folder'] else 'NO'}")
            print(f"  Task Scheduler : {'YES' if status['task_scheduler'] else 'NO'}")
            sys.exit(0)

if __name__ == "__main__":
    main()
