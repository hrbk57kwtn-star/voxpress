"""Vigilante del asistente de transcripcion.

Permanece oculto en segundo plano escuchando la tecla F1:
  - Si el asistente NO esta corriendo, lo inicia.
  - Si ya esta corriendo, no hace nada.

Asi, despues de cerrar el asistente (F12), basta con presionar
F1 en cualquier momento para volver a levantarlo.

Para salir de este vigia: cerrar el proceso pythonw o quitar su
acceso directo de la carpeta de Inicio.
"""

import subprocess

import keyboard

PYW = r"C:\Users\nicoo\voice-assistant\venv\Scripts\pythonw.exe"
SCRIPT = r"C:\Users\nicoo\voice-assistant\voice_assistant.py"

CREATE_NO_WINDOW = 0x08000000


def assistant_running() -> bool:
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | "
             "Where-Object { $_.CommandLine -like '*voice_assistant*' } | "
             "Select-Object -ExpandProperty ProcessId"],
            capture_output=True, text=True, timeout=15).stdout
        return bool(out.strip())
    except Exception:
        return True  # si no se puede verificar, no duplicar


def start_assistant():
    if assistant_running():
        return
    subprocess.Popen([PYW, SCRIPT], creationflags=CREATE_NO_WINDOW)


keyboard.add_hotkey("F1", start_assistant)
# mantiene el proceso vivo escuchando F1 para siempre
keyboard.wait()