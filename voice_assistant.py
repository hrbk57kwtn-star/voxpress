"""Asistente de transcripcion por voz (solo dictado).

Version: 1.0.0-beta

- F9:  iniciar/detener grabacion; el texto transcrito se pega
       automaticamente en la ventana activa.
- F12: salir.

Nota: en Windows puede requerir ejecutarse como administrador para
que la libreria 'keyboard' capture las teclas globalmente.
"""

VERSION = "1.1.0-beta"

import os as _os
import subprocess
import threading
import time

import keyboard
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

SAMPLE_RATE = 16000
MODEL_SIZE = "small"

print("Cargando modelo Whisper (primera vez descarga el modelo)...")
model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
print("Modelo listo.")

recording = False
audio_frames = []
stream = None
lock = threading.Lock()


def transcribe(audio: np.ndarray) -> str:
    # beam_size=1: rapido, precision casi igual
    segments, _ = model.transcribe(audio, language="es", beam_size=1,
                                   vad_filter=True)
    return " ".join(seg.text.strip() for seg in segments).strip()


def type_text(text: str) -> None:
    """Copia al portapapeles y pega en la ventana activa."""
    subprocess.run("clip", input=text.encode("utf-16le"), check=True)
    time.sleep(0.1)
    keyboard.press_and_release("ctrl+v")


def start_recording():
    global recording, audio_frames, stream
    with lock:
        audio_frames = []
        stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32",
            callback=lambda indata, *_: audio_frames.append(indata.copy()))
        stream.start()
        recording = True
    print("[*] Grabando... (F9 para detener)", flush=True)
    set_tray_idle(False)


def stop_recording():
    global recording, stream
    with lock:
        recording = False
        if stream:
            stream.stop()
            stream.close()
            stream = None
        frames = list(audio_frames)
    set_tray_idle(True)
    if not frames:
        return ""
    audio = np.concatenate(frames, axis=0).flatten()
    if len(audio) < SAMPLE_RATE * 0.4:
        return ""
    text = transcribe(audio)
    if text:
        print(f"[Transcripcion] {text}", flush=True)
        type_text(text)
    return text


def on_f9():
    if not recording:
        start_recording()
    else:
        stop_recording()


def on_f12():
    print("Saliendo...")
    os_exit(0)


# --- Indicador en la barra de tareas ----------------------------
try:
    import pystray
    from PIL import Image, ImageDraw

    def _make_icon(color: str):
        img = Image.new("RGB", (64, 64), color)
        d = ImageDraw.Draw(img)
        d.ellipse((16, 16, 48, 48), fill="white")
        return img

    tray_icon = None

    def set_tray_idle(idle: bool) -> None:
        try:
            if tray_icon is not None:
                icon = _make_icon("#00aa00" if idle else "#cc0000")
                tray_icon.icon = icon
                tray_icon.title = ("Dictado listo - F9 grabar / F12 salir"
                                   if idle else "Grabando...")
        except Exception:
            pass

    def _quit(_icon, _item):
        on_f12()

    def _run_tray():
        global tray_icon
        menu = pystray.Menu(
            pystray.MenuItem("F9 grabar  Â·  F12 salir  Â·  F1 reinicia", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Salir", _quit),
        )
        tray_icon = pystray.Icon(
            "asistente_voz", _make_icon("#00aa00"),
            "Dictado listo - F9 grabar / F12 salir", menu)
        tray_icon.run()

    threading.Thread(target=_run_tray, daemon=True).start()

    def os_exit(code):
        if tray_icon is not None:
            tray_icon.stop()
        _os._exit(code)

except ImportError:
    def set_tray_idle(idle: bool):
        pass

    def os_exit(code):
        _os._exit(code)


def main():
    keyboard.on_press_key("F9", lambda _: on_f9())
    keyboard.on_press_key("F12", lambda _: on_f12())
    print("=" * 50)
    print(f"Transcripcion de voz ACTIVA  (v{VERSION})")
    print("  F9  -> grabar/dictar (se pega en la ventana activa)")
    print("  F12 -> salir")
    print("  Indicador en la barra de tareas: verde=listo, rojo=grabando")
    print("=" * 50)
    set_tray_idle(True)
    keyboard.wait("F12")
    os_exit(0)


if __name__ == "__main__":
    main()