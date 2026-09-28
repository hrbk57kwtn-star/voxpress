"""VoxPress: dictado por voz en espanol (offline, Windows).

Version: 2.1.2

- F9:  iniciar/detener grabacion; el texto transcrito se pega
       automaticamente en la ventana activa.
- F10: salir (F12 queda como alternativa si esta libre).

SENALIZADOR VISUAL (ventana flotante semi-transparente):
  - VERDE    = listo
  - ROJO     = grabando (te estoy escuchando)
  - AMARILLO = transcribiendo (ya cortaste, pegando en seguida)
Se activa solo mientras el asistente esta corriendo y no estorba
(ni captura clics ni tapones).

QUE SE ARREGLO HASTA 2.1.2 (F9 dejaba de responder sin avisar):

  El sintoma era "F9 muerto" con la ventana en pantalla, el proceso
  vivo y el watchdog tranquilo. Motivo: la bomba de mensajes de las
  hotkeys podia quedarse muda sin que NADIE se enterara, porque

    1. el heartbeat lo escribia un hilo aparte, que sobrevive aunque
       las hotkeys esten muertas -> el watchdog nunca lo notaba;
    2. la bomba no tenia supervision ni registro de su propia muerte;
    3. el cartel de tkinter se actualizaba desde otros hilos llamando
       win.after() (no es thread-safe).

  La causa de fondo estaba en hotkeys.py: la tecla se registraba sobre
  una VENTANA oculta propiedad del hilo que la atendia. Al morir ese
  hilo, Windows destruia la ventana y la tecla quedaba huerfana: no
  entregaba nada, UnregisterHotKey fallaba y otra RegisterHotKey
  devolvia 1409 "ya registrada" (por eso parecia sana, y era
  irrecuperable).

  Ahora:
    - las teclas se asocian al HILO, sin ventana: no hay nada que
      se pueda perder (ver hotkeys.HotkeyManager);
    - la bomba late y se rearma sola si se quedo muda
      (ver hotkeys.supervise_hotkeys);
    - el heartbeat SOLO se refresca si la bomba de hotkeys y el cartel
      estan vivos, asi que un proceso medio muerto se delata y el
      watchdog lo levanta;
    - el cartel se actualiza por una cola, desde su propio hilo.

Todo se registra en assistant.log para diagnostico (con tiempos
de cada etapa para medir la velocidad).
"""

VERSION = "2.1.2"

import math
import os
import queue
import socket
import sys
import threading
import time
import traceback

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "assistant.log")
HEARTBEAT_FILE = os.path.join(BASE_DIR, "heartbeat.txt")
MAX_LOG_BYTES = 2 * 1024 * 1024  # el log no crece sin limite

log_lock = threading.Lock()


def log(msg: str):
    try:
        with log_lock:
            # Si el log pasa de 2 MB se rota a .1. Sin esto, un bucle
            # de reintentos podria llenar el disco.
            try:
                if os.path.getsize(LOG_FILE) > MAX_LOG_BYTES:
                    os.replace(LOG_FILE, LOG_FILE + ".1")
            except OSError:
                pass
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
log(f"PID {os.getpid()} exe={sys.executable}")

# Chequeo temprano de instancia unica ANTES de cargar el modelo pesado.
# Doble barrera instantanea (sin powershell: tardaba ~4s y eso parecia
# "no inicia"): socket UDP + lock de archivo (msvcrt, atomico, se libera
# solo si el proceso muere). Si esta ocupado, se reintenta unos segundos:
# el dueno puede ser una copia fallida que muere sola (ej. lanzada con
# otro Python sin dependencias); si hay heartbeat fresco, se sale.
_lock_file = None


def another_copy_running() -> bool:
    global _lock_file
    for intento in range(9):
        if ensure_single_instance():
            break
        time.sleep(1)
    else:
        return True
    try:
        import msvcrt
        _lock_file = open(os.path.join(BASE_DIR, "asistente.lock"), "a+b")
        try:
            msvcrt.locking(_lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            log("Otra copia activa detectada (lock). "
                "Saliendo sin cargar modelo.")
            return True
    except Exception as e:
        log(f"Aviso: no se pudo verificar duplicados: {e}")
    return False


if another_copy_running():
    log("Ya hay otra instancia corriendo (chequeo temprano). Saliendo sin cargar modelo.")
    sys.exit(0)

# La instancia unica ya quedo TOMADA arriba (socket + lock de archivo).
# Antes main() volvia a llamar ensure_single_instance(), que reintentaba
# enlazar el mismo puerto: o bien fallaba y el programa se moria en
# silencio, o bien liberaba el socket original y dejaba el guardian
# inutil. Ahora se decide una sola vez.
_instance_ok = True

# Usar el modelo en cache sin chequear red (carga en ~6s en vez de
# colgarse con rate-limit de HuggingFace). Para descargar un modelo nuevo
# por primera vez, ejecutar una vez con HF_HUB_OFFLINE=0.
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

from hotkeys import (HotkeyManager, VK_F9, VK_F10, VK_F12, send_ctrl_v,
                     supervise_hotkeys)

SAMPLE_RATE = 16000
MODEL_SIZE = "base"  # "base" = mas rapido que "small", suficiente para dictado

recording = False
audio_frames = []
stream = None
lock = threading.Lock()
_f9_busy = threading.Lock()  # evita hilos F9 apilados si uno se demora

log("Cargando modelo Whisper (en cache, unos segundos)...")
try:
    # cpu_threads=2: medido ~15% mas rapido que el default (4) en CPU
    # de pocos nucleos, con texto identico. No tocar sin medir de nuevo.
    _t_model = time.perf_counter()
    model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8",
                         cpu_threads=2)
    log(f"Modelo Whisper listo ({(time.perf_counter() - _t_model) * 1000:.0f} ms).")
except Exception as e:
    log(f"ERROR cargando Whisper: {e}")
    sys.exit(1)


# ---- Senalizador visual (ventana flotante) ---------------------
indicator = None  # objeto Indicator o None

# Cola de pedidos para el cartel. Regla: NADIE toca tkinter desde otro
# hilo; solo encolan. win.after() llamado desde un hilo distinto al del
# mainloop no es thread-safe y era la otra fuente de cuelgues mudos.
_ui_q = queue.Queue()
_tk_beat = 0.0  # ultima vez que el hilo de tkinter dio señales


class Indicator:
    """Ventana flotante semi-transparente, movida solo desde su hilo."""

    FONT = ("Segoe UI", 14, "bold")

    def __init__(self):
        import tkinter as tk

        self.tk = tk
        self.win = tk.Tk()
        self.win.title("VoxPress")  # titulo unico: ubicable para diagnostico
        self.win.overrideredirect(True)  # sin bordes
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.9)
        self.win.configure(bg="#111111")

        self.label = tk.Label(
            self.win, text="● LISTO", font=self.FONT,
            fg="#00ff66", bg="#111111", padx=18, pady=8)
        self.label.pack()

        self.state = False  # False=lista, True=grabando
        self._recenter()  # mismo hilo; coloca la ventana antes de mostrarla

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

    # --- lado del hilo de tkinter ---------------------------------
    def _drain(self):
        """Vacia la cola. Se reprograma sola; es el latido de la UI."""
        global _tk_beat
        _tk_beat = time.perf_counter()
        try:
            while True:
                kind, a, b, c, ms = _ui_q.get_nowait()
                if kind == "state":
                    self.state = a
                    self._apply_state()
                elif kind == "flash":
                    self._apply(a, b, c)
                elif kind == "flash_ms":
                    # cartel temporal: se restaura al estado normal luego
                    self._apply(a, b, c)
                    self.win.after(ms, self._apply_state)
                elif kind == "raise":
                    self.win.deiconify()
                    self.win.lift()
                    self.win.attributes("-topmost", True)
        except queue.Empty:
            pass
        except Exception as e:
            log(f"ERROR en el cartel: {e}")
        finally:
            try:
                self.win.after(100, self._drain)
            except Exception:
                pass

    def _supervise(self):
        """Si la ventana murio, salir para que el vigilante nos levante.

        NOTA: ya NO se llama lift()/deiconify() cada 10 s. Forzar el
        z-order de una ventana topmost mientras otra app esta al frente
        (una TUI en consola, por ejemplo) le roba la activacion cada
        pocos segundos y la deja con la entrada a medias. Ademas no
        aportaba nada: si la ventana esta bien, no hay que tocarla.
        """
        try:
            viva = bool(self.win.winfo_exists())
        except Exception:
            viva = False
        if not viva:
            log("CRITICO: ventana del senalizador destruida; "
                "saliendo para que el vigilante reviva.")
            os._exit(2)

    # --- lado de cualquier hilo (solo encola) ---------------------
    def set_state(self, recording: bool):
        _ui_q.put(("state", recording, None, None, None))

    def flash(self, text, fg, bg):
        _ui_q.put(("flash", text, fg, bg, None))

    def flash_ms(self, text, fg, bg, ms):
        _ui_q.put(("flash_ms", text, fg, bg, ms))

    def raise_window(self):
        _ui_q.put(("raise", None, None, None, None))

    def run(self):
        self.win.after(100, self._drain)
        self.win.after(3000, self._supervise)
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
def trim_silence(audio: np.ndarray, threshold: float = 0.01,
                 margin: float = 0.15) -> np.ndarray:
    """Recorta silencio inicial/final por energia (cuesta milisegundos).

    Cada segundo recortado es ~1s menos de inferencia en CPU.
    """
    if len(audio) == 0:
        return audio
    try:
        w = max(1, SAMPLE_RATE // 50)  # ventana ~20ms
        energy = np.convolve(np.abs(audio), np.ones(w) / w, mode="same")
        voiced = np.where(energy > threshold)[0]
        if len(voiced) == 0:
            return audio
        m = int(SAMPLE_RATE * margin)
        return audio[max(0, voiced[0] - m):min(len(audio), voiced[-1] + m)]
    except Exception:
        return audio


def transcribe(audio: np.ndarray) -> str:
    t0 = time.perf_counter()
    # beam_size=1: rapido, precision casi igual.
    # condition_on_previous_text=False: evita repeticiones en bucle.
    # temperatures=[0.0, 0.2]: falla rapido en vez de 6 reintentos que
    #   inventan palabras (medido: -10/-16% tiempo, texto identico).
    # VAD: corta silencios de mas de 0,5s (el pad de 400ms deja el texto
    # identico al de los parametros originales).
    segments, _ = model.transcribe(
        audio, language="es", beam_size=1, vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500, speech_pad_ms=400),
        condition_on_previous_text=False, temperature=(0.0, 0.2))
    segs = list(segments)
    text = " ".join(seg.text.strip() for seg in segs).strip()
    ms = (time.perf_counter() - t0) * 1000
    log(f"Inferencia: {ms:.0f} ms ({len(audio) / SAMPLE_RATE:.1f}s audio)")
    if segs:
        # Confianza: probabilidad media del modelo (no es exactitud
        # palabra por palabra, es un termometro: 85-99% normal,
        # <60% conviene revisar el texto).
        avg_lp = sum(s.avg_logprob for s in segs) / len(segs)
        conf = min(99.0, max(1.0, math.exp(avg_lp) * 100))
        tmax = max((s.temperature or 0) for s in segs)
        log(f"Confianza: {conf:.0f}% "
            f"(logprob {avg_lp:.2f}, temp max {tmax})")
        if conf < 60:
            log("AVISO: confianza baja, revisar el texto pegado")
    else:
        log("Sin segmentos de voz")
    return text


def set_clipboard(text: str) -> None:
    """Pone texto en el portapapeles en-proceso (sin lanzar `clip`)."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    data = text.encode("utf-16-le") + b"\x00\x00"
    user32.OpenClipboard(None)
    try:
        user32.EmptyClipboard()
        h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not h:
            raise ctypes.WinError(ctypes.get_last_error())
        p = kernel32.GlobalLock(h)
        ctypes.memmove(p, data, len(data))
        kernel32.GlobalUnlock(h)
        # el sistema toma posesion del handle: no liberarlo
        if not user32.SetClipboardData(CF_UNICODETEXT, h):
            kernel32.GlobalFree(h)
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        user32.CloseClipboard()


def type_text(text: str) -> None:
    """Copia al portapapeles y pega en la ventana activa (rapido)."""
    t0 = time.perf_counter()
    set_clipboard(text)
    time.sleep(0.02)
    send_ctrl_v()
    ms = (time.perf_counter() - t0) * 1000
    log(f"Pegado: {ms:.0f} ms")


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


def _close_stream_timeout(s, timeout: float = 2.0) -> None:
    """Detiene el stream con timeout: si el driver se cuelga en stop(),
    se abandona ese stream (log) en vez de trabar F9 para siempre."""
    if s is None:
        return
    done = threading.Event()

    def _do():
        try:
            s.stop()
        except Exception:
            pass
        try:
            s.close()
        except Exception:
            pass
        finally:
            done.set()

    t = threading.Thread(target=_do, daemon=True)
    t.start()
    if done.wait(timeout):
        log("stream detenido")
    else:
        log("CRITICO: stream.stop() colgado 2s; se abandona el stream")


def stop_recording():
    global recording, stream, _dictados
    t_all = time.perf_counter()
    log("F9: cortando grabacion...")
    with lock:
        recording = False
        s = stream
        stream = None
        frames = list(audio_frames)
    log(f"F9: audio capturado ({len(frames)} bloques)")
    _close_stream_timeout(s)
    set_tray_idle(True)  # verde
    if indicator is not None:
        # cartel amarillo mientras transcribe: feedback instantaneo
        indicator.flash_ms("TRANSCRIBIENDO...", "#ffcc00", "#332200", 8000)
    if not frames:
        return ""
    t0 = time.perf_counter()
    audio = np.concatenate(frames, axis=0).flatten()
    ms_concat = (time.perf_counter() - t0) * 1000
    if len(audio) < SAMPLE_RATE * 0.4:
        return ""
    t0 = time.perf_counter()
    before = len(audio) / SAMPLE_RATE
    audio = trim_silence(audio)
    after = len(audio) / SAMPLE_RATE
    ms_trim = (time.perf_counter() - t0) * 1000
    log(f"Corte: {before:.1f}s -> {after:.1f}s audio "
        f"(concat {ms_concat:.0f} ms, trim {ms_trim:.0f} ms)")
    text = transcribe(audio)
    if text:
        _dictados += 1
        log(f"Transcripcion #{_dictados}: {text}")
        try:
            type_text(text)
        except Exception as e:
            log(f"ERROR pegando texto: {e}")
    ms_total = (time.perf_counter() - t_all) * 1000
    log(f"Total F9->pegado: {ms_total:.0f} ms")
    set_tray_idle(True)  # restaura verde por si el cartel seguia visible
    return text


def on_f9():
    global recording, stream
    if not _f9_busy.acquire(blocking=False):
        log("F9 ignorado: hay una operacion anterior en curso")
        return
    try:
        if not recording:
            start_recording()
        else:
            stop_recording()
    except Exception as e:
        log(f"ERROR en F9: {e}\n{traceback.format_exc()}")
        with lock:
            recording = False
            stream = None
        set_tray_idle(True)
    finally:
        _f9_busy.release()


def on_exit():
    log("Salir solicitado (F10/F12).")
    # cartel amarillo "EXIT" y sale solo
    if indicator is not None:
        indicator.flash_ms("EXIT", "#ffcc00", "#332200", 900)
        time.sleep(0.4)
    os._exit(0)


_t0_boot = time.perf_counter()
_dictados = 0

# gestor de hotkeys, para que el heartbeat pueda preguntarle si late
_hk = None


def todo_sano(max_age: float = 8.0) -> bool:
    """¿Estamos vivos de verdad?

    Antes esta pregunta no existia: el watchdog solo miraba un archivo
    que escribia un hilo aparte, y ese hilo sobrevive aunque las teclas
    esten muertas. Por eso un proceso con F9 muerto parecia sano.

    Ahora el heartbeat solo se refresca si:
      - la bomba de hotkeys late, y
      - el cartel (hilo de tkinter) responde.
    Si cualquiera de los dos se mude, el watchdog ve el heartbeat
    viejo y nos levanta de verdad.
    """
    # Durante el arranque hay una ventana en la que todavia no hay
    # latido que medir (se esta creando la ventana, el modelo, etc.).
    if (time.perf_counter() - _t0_boot) < 25.0:
        return True
    if _hk is not None and not _hk.alive(max_age):
        return False
    if indicator is not None:
        b = _tk_beat
        if b <= 0.0 or (time.perf_counter() - b) > max_age:
            return False
    return True


def heartbeat_loop():
    """Marca de vida HONESTA: solo se refresca si todo esta sano."""
    n = 0
    avisado = False
    while True:
        try:
            if todo_sano():
                with open(HEARTBEAT_FILE, "w") as f:
                    f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
                if avisado:
                    log("Todo vuelve a estar sano; reanudo el heartbeat.")
                    avisado = False
            else:
                if not avisado:
                    log("AVISO: alguna parte esta muda (hotkeys o cartel); "
                        "dejo de refrescar el heartbeat para que el "
                        "vigilante me levante.")
                    avisado = True
        except Exception:
            pass
        n += 1
        if n % 100 == 0:  # ~cada 5 min: acota la hora de una muerte subita
            up = (time.perf_counter() - _t0_boot) / 60
            log(f"Vivo ({up:.0f} min, {_dictados} dictados).")
        time.sleep(3)


def main():
    global _hk

    if not _instance_ok:
        log("Ya hay otra instancia corriendo. Saliendo.")
        return

    def f9_safe():
        # ejecutar en un hilo aparte para no congelar la interfaz
        threading.Thread(target=on_f9, daemon=True).start()

    # F12 suele estar ocupado por otro programa (error 1409), por eso
    # la salida principal es F10 y F12 queda como alternativa si esta libre.
    regs = {VK_F9: f9_safe, VK_F10: on_exit, VK_F12: on_exit}

    # El registro y el bombeo ocurren en el MISMO hilo (WM_HOTKEY se
    # publica en la cola del hilo que registro la tecla), y ese hilo
    # esta vigilado: si deja de latir, se rearma solo.
    _hk = HotkeyManager(log=log)
    _hk.start(regs)
    threading.Thread(
        target=supervise_hotkeys, args=(_hk, regs, log),
        name="voxpress-supervisor", daemon=True).start()

    threading.Thread(target=heartbeat_loop, daemon=True).start()

    log("Asistente ACTIVO. F9 grabar, F10 salir (F12 alternativo).")

    start_indicator()
    if indicator is not None:
        indicator.set_state(False)
        # INICIADO: celeste si vino por F1, naranja si arranco normal
        if "--from-f1" in sys.argv:
            indicator.flash_ms("INICIADO", "#55ccff", "#002233", 1200)
        else:
            indicator.flash_ms("INICIADO", "#ff8800", "#332200", 1200)
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
    log("Fin de main (salida esperada).")
    os._exit(0)


if __name__ == "__main__":
    main()