"""Hotkeys globales nativas de Windows (RegisterHotKey) con bomba de
mensajes que se vigila y se rearma sola.

EL ERROR QUE ESTE ARCHIVO ARREGLA (no lo repitas):

    La version anterior hacia esto:

        wc.lpszClassName = "AsistenteVozHotkeys"
        self._hwnd = user32.CreateWindowExW(...)      # ventana OCULTA
        user32.RegisterHotKey(self._hwnd, id, MOD_NOREPEAT, vk)
        ... y en otro hilo:
        while True: user32.GetMessageW(...)          # bombea

    Es decir: la tecla quedaba atada a una VENTANA, y esa ventana era
    propiedad del hilo de la bomba. Una ventana pertenece al hilo que
    la creo: si ese hilo muere, Windows destruye la ventana, y con ella
    se va la tecla. Queda entonces un hotkey HUERFANO, que es el peor
    estado posible:

      - el proceso sigue vivo, con su ventana y su cartel;
      - otra RegisterHotKey de esa tecla devuelve 1409, o sea que la
        tecla "parece" registrada... pero NO entrega nada;
      - y ya no se puede recuperar: UnregisterHotKey tambien falla
        porque la ventana ya no existe.

    Eso era exactamente "F9 deja de responder y se arregla solo": el
    proceso esta sano, el watchdog tranquilo, y la tecla muerta.

COMO ESTA HECHO AHORA:

    - RegisterHotKey(NULL, id, ...): la tecla se asocia al HILO, sin
      ventana de por medio. No hay nada que se pueda perder y al
      terminar el hilo Windows las libera solo, sin huerfanos.
    - El WM_HOTKEY se atiende directamente en el bucle (viene en la
      cola del hilo). No hay CreateWindowExW, ni RegisterClassW, ni
      WndProc de ctypes: menos piezas, menos formas de colgarse.
    - La bomba late en cada vuelta y alive() lo comprueba desde
      outside; si se queda muda, el supervisor la rearma.
    - PeekMessage en vez de GetMessage: no bloquea, asi que el latido
      es siempre fresco aunque no pase nada.

Uso:
    mgr = HotkeyManager(log=mi_log)
    mgr.start({VK_F9: f9, VK_F10: salir})     # no bloquea
    ...
    mgr.stop()
"""

import ctypes
import socket
import threading
import time
from ctypes import wintypes

MOD_NOREPEAT = 0x4000

# Instancia unica por script: dos vigilantes NOAA que F1 quede libre
# (error 1409) y se pisen al decidir cuando relanzar al asistente.
# Se toma un puerto UDP en 127.0.0.1; lo libera solo el SO al morir el
# proceso, asi que si el vigilante se cuelga no bloquea nada para siempre.
LOCK_PORT = 51235
_lock_sock = None


def claim_single_instance() -> bool:
    """Devuelve False si YA hay otro proceso de este script."""
    global _lock_sock
    if _lock_sock is not None:
        return True
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.bind(("127.0.0.1", LOCK_PORT))
    except OSError:
        s.close()
        return False
    _lock_sock = s  # se mantiene abierto de por vida
    return True


VK_F1 = 0x70
VK_F9 = 0x78
VK_F10 = 0x79
VK_F12 = 0x7B

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
PM_REMOVE = 0x0001


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", ctypes.c_size_t),
        ("lParam", ctypes.c_ssize_t),
        ("time", wintypes.DWORD),
        ("pt", POINT),
        ("lPrivate", wintypes.DWORD),
    ]


def _setup_prototypes():
    user32 = ctypes.windll.user32

    # hWnd = NULL: la tecla se asocia al hilo que la registra.
    user32.RegisterHotKey.argtypes = [
        wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.UnregisterHotKey.restype = wintypes.BOOL

    user32.PeekMessageW.argtypes = [
        ctypes.POINTER(MSG), wintypes.HWND,
        wintypes.UINT, wintypes.UINT, wintypes.UINT]
    user32.PeekMessageW.restype = wintypes.BOOL

    user32.PostThreadMessageW.argtypes = [
        wintypes.DWORD, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
    user32.PostThreadMessageW.restype = wintypes.BOOL

    ctypes.windll.kernel32.GetCurrentThreadId.restype = wintypes.DWORD


_setup_prototypes()


class HotkeyManager:
    """Hotkeys globales asociadas al hilo, con bomba supervisada.

    alive() es la pieza importante: es la que permite que el watchdog
    (o el propio programa) note que la bomba se quedo muda, en vez de
    fiarse de un heartbeat escrito por otro hilo.
    """

    def __init__(self, log=None):
        self._log = log if log is not None else (lambda m: None)
        self._callbacks = {}   # id -> callback
        self._ids = {}         # vk  -> id
        self._thread = None
        self._running = False
        self._beat = 0.0
        self._regs = {}
        self._tid = 0
        self._next_id = 0xBFFF  # ids altos: los bajos los usa el sistema

    # ---- estado -------------------------------------------------
    def beat(self) -> float:
        return self._beat

    def alive(self, max_age: float = 6.0) -> bool:
        """True si la bomba dio señales hace menos de max_age segundos."""
        b = self._beat
        return b > 0.0 and (time.perf_counter() - b) < max_age

    def registered(self):
        return dict(self._ids)

    # ---- registro -----------------------------------------------
    def _register(self, vk, callback) -> bool:
        i = self._next_id
        self._next_id -= 1
        ok = ctypes.windll.user32.RegisterHotKey(None, i, MOD_NOREPEAT, vk)
        if ok:
            self._callbacks[i] = callback
            self._ids[vk] = i
            return True
        return False

    def unregister_all(self):
        user32 = ctypes.windll.user32
        for i in list(self._callbacks):
            try:
                user32.UnregisterHotKey(None, i)
            except Exception:
                pass
        self._callbacks.clear()
        self._ids.clear()

    # ---- bomba --------------------------------------------------
    def start(self, registrations: dict) -> None:
        """registrations = {vk: callback}. No bloquea."""
        self._regs = dict(registrations)
        self._running = True
        self._thread = threading.Thread(
            target=self._thread_main, name="voxpress-hotkeys", daemon=True)
        self._thread.start()

    def _thread_main(self):
        # El registro tiene que ocurrir en ESTE hilo: WM_HOTKEY se
        # publica en la cola del hilo que llamo a RegisterHotKey.
        self._tid = ctypes.windll.kernel32.GetCurrentThreadId()
        for vk, cb in self._regs.items():
            if self._register(vk, cb):
                self._log(f"Tecla {vk:#04x} registrada OK.")
            else:
                self._log(f"AVISO: tecla {vk:#04x} ocupada por otro "
                          f"programa (error 1409).")
        self._pump()

    def _pump(self):
        user32 = ctypes.windll.user32
        msg = MSG()
        cbs = self._callbacks
        self._beat = time.perf_counter()
        while self._running:
            try:
                while user32.PeekMessageW(
                        ctypes.byref(msg), 0, 0, 0, PM_REMOVE):
                    if msg.message == WM_QUIT:
                        self._running = False
                        break
                    if msg.message == WM_HOTKEY:
                        cb = cbs.get(int(msg.wParam))
                        if cb is not None:
                            try:
                                cb()
                            except Exception as e:
                                self._log(f"ERROR en el manejador de "
                                          f"tecla: {e}")
                    self._beat = time.perf_counter()
            except Exception as e:
                self._log(f"ERROR en la bomba de hotkeys: {e}")
                time.sleep(0.5)
            self._beat = time.perf_counter()
            time.sleep(0.02)

        self._beat = 0.0
        # Las teclas de este hilo se liberan solas al terminar, pero
        # desregistrarlas aqui evita depender de ese detalle.
        self.unregister_all()
        self._log("Bomba de hotkeys detenida.")

    def stop(self):
        self._running = False
        if self._tid:
            ctypes.windll.user32.PostThreadMessageW(
                self._tid, WM_QUIT, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=3.0)
        self._tid = 0
        self._thread = None
        self.unregister_all()
        self._next_id = 0xBFFF

    def rearm(self, registrations: dict = None) -> None:
        """Reinicio completo: bomba nueva + teclas registradas de nuevo."""
        if registrations is not None:
            self._regs = dict(registrations)
        self.stop()
        self.start(self._regs)


def supervise_hotkeys(mgr: HotkeyManager, registrations: dict, log,
                      max_age: float = 6.0, check: float = 2.0):
    """Vigila la bomba y la rearma si se queda muda. Bloquea (hilo)."""
    backoff = 0.0
    while True:
        time.sleep(check + backoff)
        if mgr.alive(max_age):
            backoff = 0.0
            continue
        log("AVISO: la bomba de hotkeys no da latido; rearmando.")
        t0 = time.perf_counter()
        try:
            mgr.rearm(registrations)
        except Exception as e:
            log(f"ERROR rearmando los hotkeys: {e}")
            backoff = min(backoff + check, 55.0)
            continue
        time.sleep(0.4)
        ms = (time.perf_counter() - t0) * 1000
        if mgr.alive(3.0):
            log(f"Bomba de hotkeys rearmada OK en {ms:.0f} ms.")
            backoff = 0.0
        else:
            log("AVISO: rearmada pero sigue sin latido; reintentare.")
            backoff = min(backoff + check, 55.0)


# ---- Envio de Ctrl+V (para pegar el texto dictado) -------------
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
VK_CONTROL = 0x11
VK_V = 0x56


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD)]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT), ("hi", _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUT_UNION)]


def _key_event(vk: int, keyup: bool):
    inp = _INPUT()
    inp.type = INPUT_KEYBOARD
    inp.u.ki.wVk = vk
    inp.u.ki.dwFlags = KEYEVENTF_KEYUP if keyup else 0
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))


def send_ctrl_v():
    """Pega el contenido del portapapeles en la ventana activa."""
    _key_event(VK_CONTROL, False)
    _key_event(VK_V, False)
    _key_event(VK_V, True)
    _key_event(VK_CONTROL, True)
