"""Asistente de voz - dictado por hotkey, palabra clave y chat hablado.

Version: 0.2.0-beta

Modos:
  - F8: conversar (habla -> la IA responde con voz)
  - F9: dictar texto (se pega automaticamente en la ventana activa)
  - F10: activar/desactivar escucha por palabra clave "asistente"
  - F12: salir

Nota: en Windows puede requerir ejecutarse como administrador para
que la libreria 'keyboard' capture las teclas globalmente.
"""

VERSION = "0.3.0-beta"

import json
import os
import queue
import re
import subprocess
import threading
import time
import urllib.parse
import urllib.request

import keyboard
import numpy as np
import pyttsx3
import sounddevice as sd
from faster_whisper import WhisperModel

SAMPLE_RATE = 16000
MODEL_SIZE = "small"  # buen balance precision/velocidad en CPU
WAKE_WORDS = ("asistente", "asistencia")
CHUNK_SECONDS = 4  # largo de cada escucha en modo palabra clave
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "llama3.1:8b-instruct-q4_K_M"  # modelo mas capaz (más pesado)
# alternativa liviana si la PC se arrastra: "llama3.2:3b"
SYSTEM_PROMPT = (
    "Eres un asistente de voz amable. Responde SIEMPRE en espanol, "
    "de forma muy breve (maximo 3 oraciones) porque tus respuestas se leen en voz alta."
)

print("Cargando modelo Whisper (primera vez descarga el modelo)...")
model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
print("Modelo listo.")

recording = False
audio_frames = []
stream = None
wake_mode = False
lock = threading.Lock()
conversation = []  # historial del ida y vuelta hablado

# --- Voz (TTS) con Microsoft Sabina (espanol) -------------------
# pyttsx3/SAPI se cuelga si se usa desde varios hilos: se crea un hilo
# dedicado que es el UNICO dueño del motor, y speak() le manda trabajos.
tts_queue = queue.Queue()


def _tts_worker():
    voice_id = None
    try:
        probe = pyttsx3.init()
        for v in probe.getProperty("voices"):
            if "Sabina" in v.name or "es-MX" in v.id.upper():
                voice_id = v.id
                break
        del probe
    except Exception as e:
        print(f"[Error TTS init] {e}", flush=True)

    while True:
        text, done = tts_queue.get()
        if text is None:
            done.set()
            return
        # FIX: pyttsx3/SAPI solo reproduce la PRIMERA frase si se reusa
        # el motor. Se crea un motor nuevo por frase (robusto).
        try:
            engine = pyttsx3.init()
            if voice_id:
                engine.setProperty("voice", voice_id)
            engine.setProperty("rate", 165)
            engine.say(text)
            engine.runAndWait()
            engine.stop()
            del engine
        except Exception as e:
            print(f"[Error TTS] {e}", flush=True)
        finally:
            done.set()


threading.Thread(target=_tts_worker, daemon=True).start()


def speak(text: str) -> None:
    """Lee texto en voz alta con la voz en espanol (espera a que termine)."""
    if not text:
        return
    print(f"[Asistente dice] {text}", flush=True)
    done = threading.Event()
    tts_queue.put((text, done))
    done.wait(timeout=60)


def ask_ollama(prompt: str) -> str:
    """Envia el texto al modelo local y devuelve la respuesta."""
    conversation.append({"role": "user", "content": prompt})
    body = json.dumps({
        "model": OLLAMA_MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + conversation[-20:],
        "stream": False,
        "keep_alive": "30m",  # modelo cargado en RAM: respuestas instantaneas
        "options": {"num_predict": 200},  # respuestas cortas = mas rapido
    }).encode("utf-8")
    req = urllib.request.Request(OLLAMA_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    answer = data["message"]["content"].strip()
    conversation.append({"role": "assistant", "content": answer})
    return answer


VOICE_THRESHOLD = 0.006  # se recalibra solo al iniciar segun el ruido ambiente


def calibrate_noise() -> None:
    """Mide el ruido de la habitacion 2s y ajusta el umbral de voz por encima."""
    global VOICE_THRESHOLD
    try:
        a = sd.rec(int(2 * SAMPLE_RATE), samplerate=SAMPLE_RATE,
                   channels=1, dtype="float32")
        sd.wait()
        noise = float(np.sqrt(np.mean(a ** 2)))
        # umbral: 1.8x el ruido, pero nunca mas de 0.02 (si no corta la voz)
        VOICE_THRESHOLD = min(max(noise * 1.8, 0.006), 0.02)
        print(f"[Calibracion] ruido ambiente {noise:.5f} -> umbral voz {VOICE_THRESHOLD:.5f}",
              flush=True)
    except Exception as e:
        print(f"[Calibracion] fallo ({e}), usando umbral por defecto", flush=True)


def record_utterance(max_seconds: int = 20, silence_seconds: float = 1.2,
                     no_speech_seconds: float = 6.0) -> np.ndarray:
    """Graba hasta detectar silencio prolongado (detecta cuando terminas de hablar)."""
    frames = []
    done = threading.Event()

    def callback(indata, *_):
        frames.append(indata.copy())
        rms = float(np.sqrt(np.mean(indata ** 2)))
        now = time.time()
        frame_rms.append(rms)
        # umbral adaptativo: mide el ruido de ESTA conversacion
        # (piso = percentil 20 de los niveles recientes)
        if len(frame_rms) >= 5:
            piso = float(np.percentile(frame_rms[-100:], 20))
            umbral = min(max(piso * 3.0, 0.005), 0.025)
        else:
            umbral = VOICE_THRESHOLD
        if rms > umbral:  # hay voz
            state["last_voice"] = now
            state["spoke"] = True
        if state["spoke"] and now - state["last_voice"] > silence_seconds:
            done.set()
        if not state["spoke"] and now - state["start"] > no_speech_seconds:
            done.set()  # nadie hablo: cortar
        if now - state["start"] > max_seconds:
            done.set()

    frame_rms: list[float] = []
    state = {"start": time.time(), "last_voice": time.time(), "spoke": False}
    print("[Escuchando] habla ahora... (corta solo al detectar silencio)", flush=True)
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                        callback=callback):
        done.wait()
    if not frames:
        return np.array([], dtype="float32")
    dur = sum(len(f) for f in frames) / SAMPLE_RATE
    print(f"[Audio] {dur:.1f}s grabados, se hablo: {state['spoke']}", flush=True)
    return np.concatenate(frames, axis=0).flatten()


# --- Comandos de accion (hace cosas, no solo charlar) -----------
def _normalize(t: str) -> str:
    """Minusculas y sin tildes, para tolerar errores de transcripcion."""
    return (t.lower().strip()
             .replace("á", "a").replace("é", "e").replace("í", "i")
             .replace("ó", "o").replace("ú", "u").replace("ü", "u"))


def _open(url: str) -> None:
    subprocess.Popen(["cmd", "/c", "start", url],
                     creationflags=subprocess.CREATE_NO_WINDOW)


def _http_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={
        "User-Agent": "asistente-de-voz/0.2 (asistente personal local)",
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def wikipedia_summary(query: str) -> str | None:
    """Busca el tema en Wikipedia (es) y devuelve un resumen, o None."""
    try:
        s = _http_json(
            "https://es.wikipedia.org/w/api.php?action=opensearch&format=json"
            "&limit=1&search=" + urllib.parse.quote(query))
        if not s[1]:
            return None
        title = s[1][0]
        data = _http_json(
            "https://es.wikipedia.org/api/rest_v1/page/summary/"
            + urllib.parse.quote(title.replace(" ", "_")))
        extract = data.get("extract", "").strip()
        return extract if extract else None
    except Exception as e:
        print(f"[Wiki] {e}", flush=True)
        return None


SEARCH_DIRS = None  # se calcula una vez
SEARCH_SKIP = {"appdata", "$recycle.bin", "node_modules", ".git", "venv",
               "program files", "windows"}


def _search_dirs() -> list:
    global SEARCH_DIRS
    if SEARCH_DIRS is None:
        home = os.path.expanduser("~")
        dirs = [home,
                os.path.join(home, "Documents"),
                os.path.join(home, "Downloads"),
                os.path.join(home, "Pictures"),
                os.path.join(home, "Music"),
                os.path.join(home, "Videos"),
                os.path.join(home, "Desktop"),
                os.path.join(home, "OneDrive", "Escritorio"),
                os.path.join(home, "OneDrive", "Documentos"),
                os.path.join(home, "OneDrive")]
        SEARCH_DIRS = [d for d in dict.fromkeys(dirs) if os.path.isdir(d)]
    return SEARCH_DIRS


def find_files(query: str, max_hits: int = 10) -> list[str]:
    """Busca archivos/carpetas cuyo nombre contenga query (sin tildes)."""
    q = _normalize(query)
    hits = []
    seen = set()
    for base in _search_dirs():
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs
                       if _normalize(d) not in SEARCH_SKIP and not d.startswith(".")]
            for name in dirs + files:
                full = os.path.join(root, name)
                if q in _normalize(name) and full not in seen:
                    seen.add(full)
                    hits.append(full)
                    if len(hits) >= max_hits:
                        return hits
    return hits


def search_and_open(query: str) -> None:
    """Busca el archivo y abre el Explorador mostrandolo."""
    speak(f"Buscando {query} en tus carpetas. Dame un momento.")
    hits = find_files(query)
    if not hits:
        speak(f"No encontre nada llamado {query} en tus carpetas.")
        return
    n = min(len(hits), 3)
    nombres = ", ".join(os.path.basename(h) for h in hits[:n])
    speak(f"Encontre {len(hits)} resultado{'s' if len(hits) > 1 else ''}: {nombres}. "
          "Te muestro el primero en el explorador.")
    subprocess.Popen(["explorer", "/select,", os.path.normpath(hits[0])])


def research(query: str) -> None:
    """Investiga un tema: lo dice en voz alta y abre Google de referencia."""
    speak(f"Dame un segundo, investigo sobre {query}.")
    _open("https://www.google.com/search?q=" + urllib.parse.quote(query))
    extract = wikipedia_summary(query)
    if extract:
        try:
            resumen = ask_ollama(
                f"Con esta informacion: '{extract[:1500]}'.\n"
                f"Resumi en 2 oraciones simples la respuesta a: {query}")
            speak(resumen)
        except Exception:
            speak(extract[:600])  # sin IA, lee el resumen plano
    else:
        speak("No encontre un resumen claro, pero te deje la busqueda abierta "
              "en el navegador.")


def do_command(text: str) -> bool:
    """Ejecuta acciones segun lo pedido. Devuelve True si ejecuto algo.
    Coincidencia por palabras clave: Whisper puede distorsionar, no
    exigimos frases exactas."""
    t = _normalize(text)
    now = time.localtime()

    if "hora" in t:
        speak(f"Son las {now.tm_hour}:{now.tm_min:02d}.")
        return True

    if any(k in t for k in ("que dia", "que fecha", "fecha de hoy")):
        dias = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
        meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
                 "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        speak(f"Hoy es {dias[now.tm_wday]} {now.tm_mday} de {meses[now.tm_mon - 1]} "
              f"de {now.tm_year}.")
        return True

    # abrir apps/sitios: basta mencionar el destino (Whisper a veces
    # se come la palabra "abri" con el ruido)
    if "navegador" in t or "chrome" in t or "google crome" in t:
        speak("Abriendo el navegador.")
        _open("chrome")
        return True

    if "github" in t:
        speak("Abriendo GitHub.")
        _open("https://github.com")
        return True

    if any(k in t for k in ("gmail", "correo", "mail")):
        speak("Abriendo tu correo.")
        _open("https://mail.google.com")
        return True

    if "mapa" in t or "maps" in t:
        speak("Abriendo mapas.")
        _open("https://maps.google.com")
        return True

    if "clima" in t or "tiempo esta" in t:
        _open("https://www.google.com/search?q=clima")
        speak("Te muestro el clima en el navegador.")
        return True

    if "youtube" in t and not re.search(r"busc\w*", t):
        speak("Abriendo YouTube.")
        _open("https://www.youtube.com")
        return True

    if "whatsapp" in t:
        speak("Abriendo WhatsApp.")
        _open("https://web.whatsapp.com")
        return True

    if "telegram" in t:
        speak("Abriendo Telegram.")
        _open("https://web.telegram.org")
        return True

    # busqueda de archivos en la PC (tiene prioridad sobre buscar en Google)
    if any(k in t for k in ("archivo", "carpeta", "documento", "fichero")) and \
            any(k in t for k in ("busc", "busqu", "encontr", "encuentr", "donde esta", "ubica")):
        m = re.search(r"(?:llamad[oa]\w*\s+|que se llama\s+)?([\w\.\- ]{2,60})\s*$", t)
        # extraer termino: lo que sigue a archivo/carpeta/documento
        m = re.search(r"(?:archivo|carpeta|documento|fichero)s?\s+(?:llamad[oa]\w*\s+|que se llama\s+|que diga\s+)?(.+)$", t)
        q = m.group(1).strip(" .!?") if m else ""
        q = re.sub(r"^(un|una|el|la|mis|mi)\s+", "", q).strip()
        if not q:
            speak("Que archivo busco? Decime el nombre.")
            return True
        search_and_open(q)
        return True

    # buscar/investigar
    m = re.search(r"(?:busc\w*|busqu\w*|investig\w*)(?:me|me)?(?:\s+en\s+(youtube|google))?\s+(?:sobre\s+|de\s+)?(.+)", t)
    if m:
        destino = m.group(1)
        q = m.group(2).strip(" .!?")
        if not q:
            speak("Que queres que busque?")
            return True
        if destino == "youtube" or " youtube" in t:
            q = q.replace("en youtube", "").strip()
            _open("https://www.youtube.com/results?search_query=" + urllib.parse.quote(q))
            speak(f"Buscando {q} en YouTube.")
        else:
            research(q)
        return True

    return False  # no era un comando -> charla normal con la IA


busy = False  # evita superponer conversaciones


def talk_once():
    """Graba la voz del usuario, consulta a la IA y responde hablando."""
    global busy
    if busy:
        return
    busy = True
    try:
        speak("Te escucho.")
        audio = record_utterance()
        if len(audio) < SAMPLE_RATE * 0.4:
            speak("No te escuche, decilo de nuevo.")
            return
        text = transcribe(audio)
        print(f"[Debug] transcripcion: '{text}'", flush=True)
        if not text:
            speak("No entendi, repetilo por favor.")
            return
        print("[Vos dijiste] " + text, flush=True)
        if do_command(text):
            return  # era una orden, ya se ejecuto
        print("[Pensando...] consultando al modelo local", flush=True)
        try:
            speak(ask_ollama(text))
        except Exception as e:
            print(f"[Error Ollama] {e}")
            speak("No pude conectar con la inteligencia artificial.")
    finally:
        busy = False


def transcribe(audio: np.ndarray) -> str:
    # beam_size=1: ~2-3x mas rapido con casi la misma precision
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
            callback=lambda indata, *_: audio_frames.append(indata.copy()),
        )
        stream.start()
        recording = True
    print("[*] Grabando... (F9 para detener)")


def stop_recording(paste: bool = True):
    global recording, stream
    with lock:
        recording = False
        if stream:
            stream.stop()
            stream.close()
            stream = None
        frames = list(audio_frames)
    if not frames:
        return ""
    audio = np.concatenate(frames, axis=0).flatten()
    if len(audio) < SAMPLE_RATE * 0.4:
        return ""
    text = transcribe(audio)
    print(f"[Transcripcion] {text}")
    if text and paste:
        type_text(text)
    return text


def on_f9():
    if not recording:
        start_recording()
    else:
        stop_recording()


def on_f10():
    global wake_mode
    wake_mode = not wake_mode
    estado = "ACTIVADO" if wake_mode else "DESACTIVADO"
    print(f"[Modo palabra clave] {estado} (decir 'asistente' + comando)")


def wake_word_loop():
    """Escucha continua en chunks; detecta la palabra clave."""
    while True:
        if not wake_mode or recording:
            sd.sleep(300)
            continue
        audio = sd.rec(
            int(CHUNK_SECONDS * SAMPLE_RATE),
            samplerate=SAMPLE_RATE, channels=1, dtype="float32",
        )
        sd.wait()
        if not wake_mode:
            continue
        text = transcribe(audio.flatten()).lower()
        if any(w in text for w in WAKE_WORDS):
            print(f"[Palabra clave detectada] {text}")
            # extraer lo dicho despues de la palabra clave
            resto = text
            for w in WAKE_WORDS:
                if w in resto:
                    resto = resto.split(w, 1)[1].strip(" ,.!")
                    break
            if resto:
                type_text(resto)
            else:
                # no dijo nada mas: grabar el comando
                print("[*] Escuchando comando... (habla ahora)")
                start_recording()
                sd.sleep(5000)  # graba hasta 5s (o F9 para cortar antes)
                if recording:
                    stop_recording()


def main():
    print("Calibrando microfono con el ruido ambiente (2s, no hables)...", flush=True)
    calibrate_noise()
    # precargar el modelo de IA en RAM para respuestas veloces
    print("Precargando modelo de IA (para respuestas rapidas)...", flush=True)
    try:
        body = json.dumps({"model": OLLAMA_MODEL, "keep_alive": "30m"}).encode()
        req = urllib.request.Request(OLLAMA_URL.replace("/chat", "/generate"),
                                     data=body,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=120).read()
        print("IA lista.", flush=True)
    except Exception as e:
        print(f"[Aviso] no se pudo precargar la IA: {e}", flush=True)
    keyboard.on_press_key("F9", lambda _: on_f9())
    keyboard.on_press_key("F10", lambda _: on_f10())
    keyboard.on_press_key("F8", lambda _: threading.Thread(target=talk_once, daemon=True).start())
    threading.Thread(target=wake_word_loop, daemon=True).start()
    print("=" * 55)
    print(f"Asistente de voz ACTIVO  (v{VERSION})")
    print("  F8  -> CONVERSAR: habla y la IA te responde con voz")
    print("  F9  -> dictar texto (se pega en la ventana activa)")
    print("  F10 -> modo palabra clave 'asistente' on/off")
    print("  F12 -> salir")
    print("=" * 55)
    keyboard.wait("F12")
    print("Saliendo...")


if __name__ == "__main__":
    main()
