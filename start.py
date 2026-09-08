#!/usr/bin/env python3
"""AURA Quant Terminal — reliable GUI/CLI launcher and dependency controller."""
from __future__ import annotations

import atexit
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get("SYM_PORT", "8787"))
BASE_URL = f"http://127.0.0.1:{PORT}"
UNIVERSE_FILE = ROOT / "data" / "bitget_usdt_futures_universe.json"
RELAY_PROC: subprocess.Popen | None = None
DASHBOARD_OPENED = False


def node_executable() -> str | None:
    """Resolve Node from the verified bootstrap path or the current PATH."""
    configured = os.environ.get("SYM_NODE")
    if configured and Path(configured).is_file():
        return configured
    return shutil.which("node")


def dependency_plan() -> dict[str, list[str]]:
    """Report missing tools without installing or changing the machine."""
    missing_required = []
    missing_optional = []
    if node_executable() is None:
        missing_required.append("node")
    if importlib.util.find_spec("playwright") is None:
        missing_optional.append("playwright")
    return {"missing_required": missing_required, "missing_optional": missing_optional}


def load_tkinter():
    """Import Tk lazily, allowing a reliable CLI fallback on minimal Python builds."""
    import tkinter as tk
    from tkinter import messagebox, scrolledtext
    return tk, messagebox, scrolledtext


def gui_available() -> bool:
    if os.environ.get("SYM_NO_GUI") == "1" or "--cli" in sys.argv:
        return False
    try:
        load_tkinter()
        return True
    except (ImportError, ModuleNotFoundError, RuntimeError):
        return False


def universe_snapshot_is_stale(path: Path = UNIVERSE_FILE, max_age_hours: int = 24) -> bool:
    if not path.exists():
        return True
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        value = str(payload["synced_at"]).replace("Z", "+00:00")
        synced = datetime.fromisoformat(value)
        if synced.tzinfo is None:
            synced = synced.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - synced).total_seconds() > max_age_hours * 3600
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return True


def check_relay_health() -> dict | None:
    try:
        req = urllib.request.Request(f"{BASE_URL}/serving", headers={"User-Agent": "AURALauncher/1.0.3"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    return None


def cleanup():
    global RELAY_PROC
    if RELAY_PROC and RELAY_PROC.poll() is None:
        try:
            RELAY_PROC.terminate()
            RELAY_PROC.wait(timeout=3)
        except Exception:
            RELAY_PROC.kill()
        RELAY_PROC = None


atexit.register(cleanup)


def start_relay(log: Callable[[str], None] = print) -> bool:
    global RELAY_PROC
    health = check_relay_health()
    if health and health.get("ok"):
        log(f"Relay läuft bereits auf {BASE_URL} (v{health.get('version', '1.0.3')}).")
        return True

    log(f"Starte Bitget Relay auf Port {PORT} …")
    child_env = dict(os.environ)
    child_env["PYTHONIOENCODING"] = "utf-8"
    child_env["PYTHONUTF8"] = "1"
    RELAY_PROC = subprocess.Popen(
        [sys.executable, str(ROOT / "bitget_relay.py")],
        cwd=str(ROOT), env=child_env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 8.0
    while time.time() < deadline:
        if RELAY_PROC.poll() is not None:
            log("FEHLER: Relay-Prozess wurde unerwartet beendet.")
            return False
        health = check_relay_health()
        if health and health.get("ok"):
            log(f"Relay bereit: {BASE_URL} (v{health.get('version', '1.0.3')}).")
            return True
        time.sleep(0.2)
    log("FEHLER: Timeout beim Relay-Health-Check.")
    cleanup()
    return False


def open_browser(url: str, log: Callable[[str], None] = print):
    log(f"Öffne Browser: {url}")
    if not webbrowser.open(url):
        log(f"Browser konnte nicht automatisch geöffnet werden. URL: {url}")


def open_dashboard(log: Callable[[str], None] = print):
    global DASHBOARD_OPENED
    if DASHBOARD_OPENED:
        return
    DASHBOARD_OPENED = True
    open_browser(f"{BASE_URL}/", log)


def run_command(cmd: list[str], log: Callable[[str], None] = print) -> int:
    log(f"> {' '.join(cmd)}")
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    proc = subprocess.Popen(
        cmd, cwd=str(ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        log(line.rstrip())
    return proc.wait()


def universe_text() -> str:
    if not UNIVERSE_FILE.exists():
        return "noch nicht synchronisiert"
    try:
        data = json.loads(UNIVERSE_FILE.read_text(encoding="utf-8"))
        return f"{data.get('total_contracts', '?')} aktive USDT-M Futures"
    except Exception:
        return "Snapshot nicht lesbar"


def run_gui() -> int:
    tk, _messagebox, scrolledtext = load_tkinter()
    root = tk.Tk()
    root.title("AURA Quant Terminal")
    root.geometry("900x680")
    root.minsize(760, 580)
    root.configure(bg="#0b1220")
    root.grid_columnconfigure(0, weight=1)
    root.grid_rowconfigure(3, weight=1)

    colors = {"bg": "#0b1220", "panel": "#0d1b2a", "fg": "#e6f1ff", "muted": "#8ea6bf", "cyan": "#22d3ee", "green": "#35e39a", "amber": "#ffca58"}
    font = ("Segoe UI", 10)
    title_font = ("Segoe UI Semibold", 24)

    header = tk.Frame(root, bg=colors["bg"], padx=28, pady=20)
    header.grid(row=0, column=0, sticky="ew")
    header.grid_columnconfigure(0, weight=1)
    tk.Label(header, text="AURA Quant Terminal", fg=colors["cyan"], bg=colors["bg"], font=title_font).grid(row=0, column=0, sticky="w")
    tk.Label(header, text="Read-only Research & Setup Discovery", fg=colors["muted"], bg=colors["bg"], font=font).grid(row=1, column=0, sticky="w")

    status_frame = tk.Frame(root, bg=colors["panel"], padx=20, pady=14)
    status_frame.grid(row=1, column=0, sticky="ew", padx=28, pady=(0, 14))
    status_frame.grid_columnconfigure(0, weight=1)
    relay_var = tk.StringVar(value="Relay: wird geprüft …")
    universe_var = tk.StringVar(value=f"Universum: {universe_text()}")
    mode_var = tk.StringVar(value="Modus: READ-ONLY RESEARCH")
    for row, (var, color) in enumerate(((relay_var, colors["green"]), (universe_var, colors["fg"]), (mode_var, colors["cyan"]))):
        tk.Label(status_frame, textvariable=var, fg=color, bg=colors["panel"], font=("Segoe UI Semibold", 10)).grid(row=row, column=0, sticky="w", pady=2)

    action_frame = tk.Frame(root, bg=colors["bg"])
    action_frame.grid(row=2, column=0, sticky="ew", padx=28, pady=(0, 8))
    for column in range(4):
        action_frame.grid_columnconfigure(column, weight=1, uniform="actions")

    log_box = scrolledtext.ScrolledText(root, height=18, bg="#050b12", fg="#c8d8e8", insertbackground="white", font=("Consolas", 9), relief="flat", padx=10, pady=10)
    log_box.grid(row=3, column=0, sticky="nsew", padx=28, pady=(8, 16))
    log_box.configure(state="disabled")

    def log(text: str):
        def append():
            log_box.configure(state="normal")
            log_box.insert("end", text + "\n")
            log_box.see("end")
            log_box.configure(state="disabled")
        root.after(0, append)

    buttons = []

    def set_busy(busy: bool):
        state = "disabled" if busy else "normal"
        for button in buttons:
            button.configure(state=state)

    def refresh_status():
        health = check_relay_health()
        relay_var.set(f"Relay: {'ONLINE · ' + BASE_URL if health else 'OFFLINE'}")
        universe_var.set(f"Universum: {universe_text()}")
        mode_var.set("Modus: READ-ONLY RESEARCH")

    def background_task(label: str, fn: Callable[[], int | None]):
        def worker():
            root.after(0, lambda: set_busy(True))
            log(f"\n--- {label} ---")
            try:
                rc = fn()
                log(f"--- {label}: {'OK' if rc in (None, 0) else 'FEHLER ' + str(rc)} ---")
            except Exception as exc:
                log(f"FEHLER: {exc}")
            finally:
                root.after(0, refresh_status)
                root.after(0, lambda: set_busy(False))
        threading.Thread(target=worker, daemon=True).start()

    def action_card(column: int, title: str, description: str, command, color: str):
        card = tk.Frame(action_frame, bg=colors["panel"], padx=10, pady=10)
        card.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 5, 0 if column == 3 else 5))
        card.grid_columnconfigure(0, weight=1)
        button = tk.Button(card, text=title, command=command, bg=color, fg="#031018", activebackground=color, font=("Segoe UI Semibold", 10), relief="flat", padx=12, pady=9, cursor="hand2")
        button.grid(row=0, column=0, sticky="ew")
        tk.Label(card, text=description, wraplength=180, justify="left", anchor="nw", fg=colors["muted"], bg=colors["panel"], font=("Segoe UI", 9)).grid(row=1, column=0, sticky="nw", pady=(7, 0))
        buttons.append(button)

    action_card(0, "Dashboard öffnen", "Öffnet das lokale AURA Research-Dashboard.", lambda: open_dashboard(log), colors["cyan"])
    action_card(1, "Tutorial öffnen", "Öffnet die lokale Anleitung zum Research-Workflow.", lambda: open_browser(f"{BASE_URL}/tutorial", log), "#9fb8ff")
    action_card(2, "Universum updaten", "Lädt die aktuellsten 700+ Coins von der Exchange herunter.", lambda: background_task("Marktdaten-Sync", lambda: run_command([sys.executable, "scripts/sync_market_data.py"], log)), colors["green"])
    action_card(3, "System prüfen", "Führt alle Sicherheits- und Mathematik-Tests (Release Check) aus.", lambda: background_task("Release-Check", lambda: run_command([sys.executable, "scripts/release_check.py"], log)), colors["amber"])

    tk.Label(root, text="Beim Schließen wird nur der von diesem Launcher gestartete Read-only-Relay beendet.", fg=colors["muted"], bg=colors["bg"], font=("Segoe UI", 9)).grid(row=4, column=0, pady=(0, 12))

    def on_close():
        cleanup()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    log("AURA Quant Terminal gestartet.")
    refresh_status()
    if universe_snapshot_is_stale():
        log("Marktuniversum ist älter als 24 Stunden — aktualisiere im Hintergrund …")
        background_task("Automatischer Universum-Sync", lambda: run_command([sys.executable, "scripts/sync_market_data.py", "--universe-only"], log))
    open_dashboard(log)
    root.mainloop()
    return 0


def print_banner():
    print("\n" + "=" * 60)
    print("       AURA Quant Terminal — Quant Research & Setup Discovery v1.0.3")
    print("=" * 60)
    print(f"  Dashboard: {BASE_URL}/")
    print(f"  Tutorial:  {BASE_URL}/tutorial")
    print(f"  Universum: {universe_text()}")
    print("  Modus:     READ-ONLY RESEARCH")
    print("  [b] Browser  [t] Tutorial  [s] Sync  [r] Check  [q] Ende")
    print("=" * 60)


def run_cli(open_dashboard_on_start: bool = True) -> int:
    if open_dashboard_on_start:
        open_dashboard()
    if universe_snapshot_is_stale():
        print("Marktuniversum ist älter als 24 Stunden — synchronisiere …")
        run_command([sys.executable, "scripts/sync_market_data.py", "--universe-only"])
    print_banner()
    while True:
        try:
            cmd = input("AURA Quant Terminal > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break
        if cmd in ("q", "quit", "exit"):
            break
        if cmd in ("b", "browser", "dashboard"):
            open_browser(f"{BASE_URL}/")
        elif cmd in ("t", "tutorial"):
            open_browser(f"{BASE_URL}/tutorial")
        elif cmd in ("s", "sync"):
            run_command([sys.executable, "scripts/sync_market_data.py"])
        elif cmd in ("r", "check", "test"):
            run_command([sys.executable, "scripts/release_check.py"])
        elif cmd:
            print("Erlaubt: b, t, s, r, q")
    return 0


def main() -> int:
    signal.signal(signal.SIGINT, lambda _s, _f: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda _s, _f: sys.exit(0))
    print("Initialisiere AURA Quant Terminal …")
    if not start_relay():
        return 1
    if gui_available():
        try:
            return run_gui()
        except Exception as exc:
            print(f"GUI konnte nicht gestartet werden ({exc}); nutze zuverlässigen CLI-Modus.")
    return run_cli(open_dashboard_on_start=not DASHBOARD_OPENED)


if __name__ == "__main__":
    sys.exit(main())
