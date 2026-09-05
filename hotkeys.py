"""Hotkeys globales nativas de Windows (RegisterHotKey).

A diferencia de la libreria 'keyboard', RegisterHotKey es estable en
procesos ocultos (pythonw) y no requiere una consola visible.

Uso:
    mgr = HotkeyManager()
    mgr.register(0x70, lambda: print("F1"))   # 0x70 = F1
    mgr.register(0x73, salir)                 # 0x73 = F12
    mgr.run()  # bloquea atendiendo las teclas
"""

import ctypes
import threading
from ctypes import wintypes

MOD_NOREPEAT = 0x4000

VK_F1 = 0x70
VK_F8 = 0x77
VK_F9 = 0x78
VK_F10 = 0x79
VK_F11 = 0x7A
VK_F12 = 0x7B

LRESULT = ctypes.c_ssize_t
WPARAM = ctypes.c_size_t
LPARAM = ctypes.c_ssize_t

WNDPROC = ctypes.WINFUNCTYPE(
    LRESULT, wintypes.HWND, wintypes.UINT, WPARAM, LPARAM)


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", WPARAM),
        ("lParam", LPARAM),
        ("time", wintypes.DWORD),
        ("pt", POINT),
        ("lPrivate", wintypes.DWORD),
    ]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


_id = 0
_callbacks = {}


def _setup_prototypes():
    user32 = ctypes.windll.user32

    user32.DefWindowProcW.restype = LRESULT
    user32.DefWindowProcW.argtypes = [
        wintypes.HWND, wintypes.UINT, WPARAM, LPARAM]

    user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]

    user32.CreateWindowExW.restype = wintypes.HWND
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p]

    user32.RegisterHotKey.argtypes = [
        wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]

    user32.GetMessageW.argtypes = [
        ctypes.POINTER(MSG), wintypes.HWND,
        wintypes.UINT, wintypes.UINT]
    user32.GetMessageW.restype = ctypes.c_int

    user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
    user32.DispatchMessageW.restype = LRESULT


_setup_prototypes()


def _wnd_proc(hwnd, msg, wparam, lparam):
    # WM_HOTKEY = 0x0312
    if msg == 0x0312:
        cb = _callbacks.get(int(wparam))
        if cb:
            try:
                cb()
            except Exception:
                pass
        return 0
    # Para WM_NCCREATE y demas el WndProc DEBE devolver lo que diga
    # DefWindowProcW; si devuelve 0 en WM_NCCREATE, CreateWindowExW falla.
    return ctypes.windll.user32.DefWindowProcW(hwnd, msg, wparam, lparam)


class HotkeyManager:
    def __init__(self):
        self._hwnd = None
        self._running = False
        self._wndproc = WNDPROC(_wnd_proc)

    def _ensure_window(self):
        if self._hwnd is not None:
            return
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        wc = WNDCLASSW()
        wc.lpfnWndProc = self._wndproc
        wc.hInstance = kernel32.GetModuleHandleW(None)
        wc.lpszClassName = "AsistenteVozHotkeys"
        try:
            user32.RegisterClassW(ctypes.byref(wc))
        except Exception:
            pass
        self._hwnd = user32.CreateWindowExW(
            0, "AsistenteVozHotkeys", "", 0, 0, 0, 0, 0,
            0, 0, wc.hInstance, None)

    def register(self, vk: int, callback):
        global _id
        self._ensure_window()
        _id += 1
        ok = ctypes.windll.user32.RegisterHotKey(
            self._hwnd, _id, MOD_NOREPEAT, vk)
        if ok:
            _callbacks[_id] = callback
            return _id
        return None

    def run(self):
        self._ensure_window()
        user32 = ctypes.windll.user32
        msg = MSG()
        self._running = True
        while self._running:
            ret = user32.GetMessageW(ctypes.byref(msg), 0, 0, 0)
            if ret <= 0:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))


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