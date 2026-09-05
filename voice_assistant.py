"""Asistente de transcripcion por voz (solo dictado).

Version: 1.2.0-beta

- F9:  iniciar/detener grabacion; el texto transcrito se pega
       automaticamente en la ventana activa.
- F10: salir (F12 queda como alternativa si esta libre;
       en este PC F12 esta ocupado por otro programa - error 1409).

SENALIZADOR VISUAL (ventana flotante semi-transparente):
  - VERDE  = listo
  - ROJO   = grabando (te estoy escuchando)
Se activa solo mientras el asistente esta corriendo y no estorba
(ni captura clics ni tapones).

Todo se registra en assistant.log para diagnostico.
"""

VERSION = "1.2.0-beta"

import os
import socket
import subprocess
import sys
import threading
import time
import traceback

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "assistant.log")
HEARTBEAT_FILE = os.path.join(BASE_DIR, "heartbeat.txt")

log_lock = threading.Lock()


def log(msg: str):
    try:
        with log_lock:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass


# ---- Instancia unica -------------------------------------------
_single = None


def ensure_single_instance() -> bool:
    global _single
    try:
        _single = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        _single.bind(("127.0.0.1", 51234))
        return True
    except OSError:
        return False


log(f"--- Iniciando asistente v{VERSION} ---")

# Chequeo temprano de instancia unica ANTES de cargar el modelo pesado.
# El modelo tarda ~20-30s en CPU; sin este chequeo, un doble-clic en ese
# lapso levantaba 2-5 copias cargando el modelo a la vez y colgaba el PC.
if not ensure_single_instance():
    log("Ya hay otra instancia corriendo (chequeo temprano). Saliendo sin cargar modelo.")
    sys.exit(0)

# Usar el modelo en cache sin chequear red (carga en ~6s en vez de
# colgarse con rate-limit de HuggingFace). Para descargar un modelo nuevo
# por primera vez, ejecutar una vez con HF_HUB_OFFLINE=0.
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

from hotkeys import HotkeyManager, VK_F9, VK_F10, VK_F12, send_ctrl_v

SAMPLE_RATE = 16000
MODEL_SIZE = "base"  # "base" = mas rapido que "small", suficiente para dictado

recording = False
audio_frames = []
stream = None
lock = threading.Lock()

log("Cargando modelo Whisper (puede tardar 20-30s en CPU, no tocar nada)...")
try:
    model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
    log("Modelo Whisper listo.")
except Exception as e:
    log(f"ERROR cargando Whisper: {e}")
    sys.exit(1)


# ---- Senalizador visual (ventana flotante) ---------------------
indicator = None  # objeto Indicator o None


class Indicator:
    """Ventana flotante semi-transparente, thread-safe."""

    FONT = ("Segoe UI", 14, "bold")

    def __init__(self):
        import tkinter as tk

        self.tk = tk
        self.win = tk.Tk()
        self.win.overrideredirect(True)  # sin bordes
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.9)
        self.win.configure(bg="#111111")

        self.label = tk.Label(
            self.win, text="● LISTO", font=self.FONT,
            fg="#00ff66", bg="#111111", padx=18, pady=8)
        self.label.pack()

        self.state = False  # False=lista, True=grabando
        self._flash_job = None
        self._recenter()

    def _recenter(self):
        """Ancla la ventana abajo a la DERECHA y ajusta el ancho al texto."""
        try:
            self.win.update_idletasks()
            w = self.win.winfo_reqwidth()
            h = self.win.winfo_reqheight()
            sw = self.win.winfo_screenwidth()
            sh = self.win.winfo_screenheight()
            x = sw - w - 20
            y = sh - h - 70
            self.win.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def _apply(self, text, fg, bg):
        try:
            self.label.config(text=text, fg=fg, bg=bg)
            self.win.configure(bg=bg)
            self._recenter()
        except Exception:
            pass

    def _apply_state(self):
        if self.state:
            self._apply("● GRABANDO...", "#ff3355", "#220000")
        else:
            self._apply("● LISTO", "#00ff66", "#111111")

    def set_state(self, recording: bool):
        # se llama desde cualquier hilo; programar en el hilo de tkinter
        self.state = recording
        try:
            self.win.after(0, self._apply_state)
        except Exception:
            pass

    def flash(self, text, fg, bg, ms):
        """Muestra un cartel temporal y vuelve al estado normal."""
        def _do():
            self._apply(text, fg, bg)
        def _restore():
            self._apply_state()
        try:
            self.win.after(0, _do)
            self.win.after(ms, _restore)
        except Exception:
            pass

    def run(self):
        self.win.mainloop()


def start_indicator():
    global indicator
    try:
        indicator = Indicator()
        log("Senalizador visual creado.")
    except Exception as e:
        log(f"ERROR creando senalizador: {e}\n{traceback.format_exc()}")
        indicator = None


def set_tray_idle(idle: bool):
    """Actualiza el senalizador (verde/rojo)."""
    global indicator
    if indicator is not None:
        indicator.set_state(not idle)


# ---- Logica de grabacion ---------------------------------------
def transcribe(audio: np.ndarray) -> str:
    segments, _ = model.transcribe(audio, language="es", beam_size=1,
                                   vad_filter=True)
    return " ".join(seg.text.strip() for seg in segments).strip()


def type_text(text: str) -> None:
    subprocess.run("clip", input=text.encode("utf-16le"), check=True)
    time.sleep(0.1)
    send_ctrl_v()


def start_recording():
    global recording, audio_frames, stream
    with lock:
        audio_frames = []
        stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32",
            callback=lambda indata, *_: audio_frames.append(indata.copy()))
        stream.start()
        recording = True
    log("Grabando...")
    set_tray_idle(False)  # rojo


def stop_recording():
    global recording, stream
    with lock:
        recording = False
        if stream:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
            stream = None
        frames = list(audio_frames)
    set_tray_idle(True)  # verde
    if not frames:
        return ""
    audio = np.concatenate(frames, axis=0).flatten()
    if len(audio) < SAMPLE_RATE * 0.4:
        return ""
    text = transcribe(audio)
    if text:
        log(f"Transcripcion: {text}")
        try:
            type_text(text)
        except Exception as e:
            log(f"ERROR pegando texto: {e}")
    return text


def on_f9():
    global recording, stream
    try:
        if not recording:
            start_recording()
        else:
            stop_recording()
    except Exception as e:
        log(f"ERROR en F9: {e}\n{traceback.format_exc()}")
        with lock:
            recording = False
            if stream:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
                stream = None
        set_tray_idle(True)


def on_exit():
    log("Salir solicitado (F10/F12).")
    # cartel amarillo "EXIT" y sale solo
    if indicator is not None:
        indicator.flash("EXIT", "#ffcc00", "#332200", 900)
        time.sleep(0.4)
    os._exit(0)


def heartbeat_loop():
    """Escribe la marca de vida para que el watchdog sepa que vivimos."""
    while True:
        try:
            with open(HEARTBEAT_FILE, "w") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
        except Exception:
            pass
        time.sleep(3)


def main():
    if not ensure_single_instance():
        log("Ya hay otra instancia corriendo. Saliendo.")
        return

    threading.Thread(target=heartbeat_loop, daemon=True).start()

    def f9_safe():
        # ejecutar en un hilo aparte para no congelar la interfaz
        threading.Thread(target=on_f9, daemon=True).start()

    # Los hotkeys se registran y atienden en un hilo dedicado (RegisterHotKey
    # necesita su propio bucle de mensajes en el mismo hilo que lo crea).
    # F12 suele estar ocupado por otro programa (error 1409), por eso
    # la salida principal es F10 y F12 queda como alternativa si esta libre.
    def hotkey_loop():
        mgr = HotkeyManager()
        if mgr.register(VK_F9, f9_safe) is None:
            log("ERROR: no se pudo registrar F9 (ya en uso?)")
        else:
            log("Hotkey F9 registrado OK.")
        ok_exit = False
        if mgr.register(VK_F10, on_exit) is None:
            log("ERROR: no se pudo registrar F10 (ya en uso?)")
        else:
            log("Hotkey F10 (salir) registrado OK.")
            ok_exit = True
        if mgr.register(VK_F12, on_exit) is None:
            log("AVISO: F12 ocupado por otro programa (error 1409); se usa F10 para salir.")
        else:
            log("Hotkey F12 (salir alternativo) registrado OK.")
            ok_exit = True
        if not ok_exit:
            log("ERROR CRITICO: ni F10 ni F12 pudieron registrarse; no hay tecla de salida.")
        mgr.run()

    threading.Thread(target=hotkey_loop, daemon=True).start()

    log("Asistente ACTIVO. F9 grabar, F10 salir (F12 alternativo).")

    start_indicator()
    if indicator is not None:
        indicator.set_state(False)
        # INICIADO: celeste si vino por F1, naranja si arranco normal
        if "--from-f1" in sys.argv:
            indicator.flash("INICIADO", "#55ccff", "#002233", 1200)
        else:
            indicator.flash("INICIADO", "#ff8800", "#332000", 1200)
    else:
        log("AVISO: sin senalizador visual; solo F9/F10.")

    if indicator is not None:
        # tkinter en el hilo principal
        try:
            indicator.run()
        except Exception as e:
            log(f"EXCEPCIÓN en indicator.run(): {e}\n{traceback.format_exc()}")
    else:
        # sin senalizador: mantenerse vivo
        while True:
            time.sleep(1)
    os._exit(0)


if __name__ == "__main__":
    main()