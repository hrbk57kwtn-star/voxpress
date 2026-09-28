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
from hotkeys import (HotkeyManager, VK_F1, supervise_hotkeys,
                     claim_single_instance)  # noqa: E402

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "watchdog.log")
HEARTBEAT_FILE = os.path.join(BASE_DIR, "heartbeat.txt")

PYW = os.path.join(BASE_DIR, "venv", "Scripts", "pythonw.exe")
SCRIPT = os.path.join(BASE_DIR, "voice_assistant.py")

CREATE_NO_WINDOW = 0x08000000
CHECK_SECONDS = 4
# Margen generoso: el asistente carga Whisper y registra las teclas en
# 2-6 s, y con la maquina ocupada puede tardar bastante mas. Con un
# umbral corto el vigilante lo mataba y lo relanzaba en bucle, y eso si
# es un bucle: el proceso nunca llegaba a terminar de arrancar.
HEARTBEAT_TIMEOUT = 30
STARTUP_GRACE = 45  # no relanzar dentro de este lapso tras un lanzamiento
STALE_STREAK = 2  # chequeos seguidos en falta antes de relanzar
MAX_GRACE = 600  # tope del historial de intentos: 10 min
MAX_LOG_BYTES = 2 * 1024 * 1024

_last_start = 0.0
_stale_streak = 0
_fallos = 0  # lanzamientos seguidos que no dejaron rastro de vida


def log(msg: str):
    try:
        # El log no puede crecer sin limite: un bucle de reintentos
        # llenaria el disco. Se rota al pasar de 2 MB.
        try:
            if os.path.getsize(LOG_FILE) > MAX_LOG_BYTES:
                os.replace(LOG_FILE, LOG_FILE + ".1")
        except OSError:
            pass
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass


def grace_actual() -> float:
    """Espera antes de reintentar: crece si el asistente no levanta.

    Sin esto, si el asistente no puede arrancar (memoria apurada, una
    dependencia rota), el vigilante lo relanzaba cada 60 s para siempre,
    y cada intento carga Whisper: ~200 MB y 5 s de CPU, en bucle.
    """
    return min(STARTUP_GRACE * (2 ** min(_fallos, 4)), MAX_GRACE)


def assistant_alive() -> bool:
    try:
        return (os.path.isfile(HEARTBEAT_FILE)
                and (time.time() - os.path.getmtime(HEARTBEAT_FILE)
                     < HEARTBEAT_TIMEOUT))
    except Exception:
        return False


def start_assistant(from_f1: bool = False):
    global _last_start, _fallos
    if assistant_alive():
        return False
    # Gracia post-lanzamiento: el asistente tarda en cargar el modelo y
    # escribir su primer heartbeat; relanzar ahi duplicaba copias.
    # Con reintentos fallidos la gracia crece (60s, 120s, 240s...).
    if _last_start > 0 and (time.time() - _last_start) < grace_actual():
        log("Lanzamiento reciente en curso; esperando.")
        return False
    try:
        args = [PYW, SCRIPT]
        if from_f1:
            args.append("--from-f1")
        proc = subprocess.Popen(args, creationflags=CREATE_NO_WINDOW)
        _last_start = time.time()
        _fallos += 1
        extra = "" if _fallos <= 1 else f" (intento {_fallos})"
        log("Asistente iniciado (PID %d)%s.%s" % (
            proc.pid, " (F1)" if from_f1 else "", extra))
        return True
    except Exception as e:
        log(f"ERROR iniciando asistente: {e}")
        return False


def respawn_loop():
    global _stale_streak, _fallos
    time.sleep(5)  # dejar arrancar el sistema
    while True:
        try:
            if assistant_alive():
                if _stale_streak == 0 and _fallos > 1:
                    log(f"Volvio a la normalidad tras {_fallos} intentos.")
                _stale_streak = 0
                _fallos = 0
            elif _last_start > 0 and (time.time() - _last_start) < grace_actual():
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


def supervise_respawn():
    """Si el hilo de respawn muere, relanzarlo.

    Ese hilo es el unico que revive al asistente, asi que si se muere en
    silencio el sistema entero se queda sin Junctionado: es el mismo
    bug que acabamos de arreglar en el asistente, aqui seria igual de
    molesto y mas dificil de notar (no hay cartel que se mueva).
    """
    while True:
        time.sleep(5)
        if not any(t.name == "watchdog-respawn"
                   for t in threading.enumerate()):
            log("AVISO: el hilo de respawn murio; relanzando.")
            threading.Thread(target=respawn_loop, name="watchdog-respawn",
                             daemon=True).start()


def main():
    # Un solo vigilante: si hay otro corriendo, este se retira en vez de
    # pelear por F1 y por la decision de relanzar al asistente.
    if not claim_single_instance():
        log("Ya hay otro vigilante corriendo; este se retira.")
        return

    log("--- Vigilante iniciado (RegisterHotKey + heartbeat) ---")

    mgr = HotkeyManager(log=log)

    def on_f1():
        log("F1 presionado -> iniciando asistente")
        # en un hilo aparte: la bomba de mensajes no debe hacer trabajo
        threading.Thread(target=start_assistant, args=(True,),
                         daemon=True).start()

    regs = {VK_F1: on_f1}
    mgr.start(regs)
    threading.Thread(
        target=supervise_hotkeys, args=(mgr, regs, log),
        name="watchdog-supervisor", daemon=True).start()

    threading.Thread(target=respawn_loop, name="watchdog-respawn",
                     daemon=True).start()
    threading.Thread(target=supervise_respawn, daemon=True).start()
    log("Escuchando F1 y vigilando el asistente.")

    try:
        # el vigilante vive mientras la bomba de hotkeys siga latiendo
        while mgr.alive(30.0):
            time.sleep(1)
    except Exception as e:
        log(f"ERROR en run: {e}")


if __name__ == "__main__":
    main()