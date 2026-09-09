"""Vigilante (watchdog) del asistente de transcripcion.

Corre oculto en segundo plano y hace DOS cosas:

1. Auto-respawn: controla la marca de vida (heartbeat.txt) que el
   asistente actualiza cada pocos segundos; si se cae o se cierra,
   lo vuelve a levantar automaticamente.
2. Tecla F1: arranca el asistente de inmediato si no esta corriendo.

Usa RegisterHotKey de Windows (estable en procesos ocultos, a diferencia
de la libreria 'keyboard').

Para deshabilitarlo: quitar su acceso directo de la carpeta de Inicio.
"""

import os
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hotkeys import HotkeyManager, VK_F1  # noqa: E402

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "watchdog.log")
HEARTBEAT_FILE = os.path.join(BASE_DIR, "heartbeat.txt")

PYW = os.path.join(BASE_DIR, "venv", "Scripts", "pythonw.exe")
SCRIPT = os.path.join(BASE_DIR, "voice_assistant.py")

CREATE_NO_WINDOW = 0x08000000
CHECK_SECONDS = 4
HEARTBEAT_TIMEOUT = 9  # si el heartbeat es mas viejo que esto, esta muerto
STARTUP_GRACE = 60  # no relanzar dentro de este lapso tras un lanzamiento
STALE_STREAK = 2  # chequeos seguidos en falta antes de relanzar

_last_start = 0.0
_stale_streak = 0


def log(msg: str):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass


def assistant_alive() -> bool:
    try:
        return (os.path.isfile(HEARTBEAT_FILE)
                and (time.time() - os.path.getmtime(HEARTBEAT_FILE)
                     < HEARTBEAT_TIMEOUT))
    except Exception:
        return False


def start_assistant(from_f1: bool = False):
    global _last_start
    if assistant_alive():
        return False
    # Gracia post-lanzamiento: el asistente tarda en cargar el modelo y
    # escribir su primer heartbeat; relanzar ahi duplicaba copias.
    if _last_start > 0 and (time.time() - _last_start) < STARTUP_GRACE:
        log("Lanzamiento reciente en curso; esperando.")
        return False
    try:
        args = [PYW, SCRIPT]
        if from_f1:
            args.append("--from-f1")
        proc = subprocess.Popen(args, creationflags=CREATE_NO_WINDOW)
        _last_start = time.time()
        log("Asistente iniciado (PID %d).%s" % (proc.pid, " (F1)" if from_f1 else ""))
        return True
    except Exception as e:
        log(f"ERROR iniciando asistente: {e}")
        return False


def respawn_loop():
    global _stale_streak
    time.sleep(5)  # dejar arrancar el sistema
    while True:
        try:
            if assistant_alive():
                _stale_streak = 0
            elif _last_start > 0 and (time.time() - _last_start) < STARTUP_GRACE:
                pass  # carga en curso, no molestar
            else:
                _stale_streak += 1
                if _stale_streak >= STALE_STREAK:
                    log("Asistente no detectado (2 chequeos); reiniciando.")
                    if start_assistant():
                        _stale_streak = 0
                else:
                    log("Posible caida (chequeo 1/2); confirmando.")
        except Exception as e:
            log(f"ERROR en respawn_loop: {e}")
        time.sleep(CHECK_SECONDS)


def main():
    log("--- Vigilante iniciado (RegisterHotKey + heartbeat) ---")

    mgr = HotkeyManager()
    def on_f1():
        log("F1 presionado → iniciando asistente")
        start_assistant(from_f1=True)
    mgr.register(VK_F1, on_f1)

    threading.Thread(target=respawn_loop, daemon=True).start()
    log("Escuchando F1 y vigilando el asistente.")

    try:
        mgr.run()
    except Exception as e:
        log(f"ERROR en run: {e}")


if __name__ == "__main__":
    main()