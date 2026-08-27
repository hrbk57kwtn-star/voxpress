# 🎙️ Asistente de Transcripción por Voz

> **Versión: `v1.1.0-beta`**
> Cambio de plan: se retiró el motor de conversación hablada (IA + voz de respuesta)
> y se dejó **solo transcripción por voz** (dictado).

Herramienta de **dictado por voz** para Windows, 100% local y en **español**.
Hablas y el texto aparece escrito automáticamente donde esté el cursor.

## Características

- 🎤 **Reconocimiento de voz en español** con [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- ✍️ **Dictado**: el texto se pega automáticamente en la ventana activa
- 🔴🟢 **Indicador en la barra de tareas**: verde = listo, rojo = grabando
- 🔁 **Vigilante (watchdog)**: con **F1** el asistente se vuelve a iniciar
  aunque lo hayas cerrado (el watchdog corre oculto desde el arranque)
- 🚀 **Arranque automático con Windows** (inicia oculto, sin ventana)
- ⌨️ **Hotkeys globales** — funciona desde cualquier ventana

## Teclas

| Tecla | Función |
|-------|---------|
| **F9** | Iniciar/detener grabación → pega el texto donde esté el cursor |
| **F12** | Salir |
| **F1** | Reiniciar el asistente (lo maneja el watchdog, corre en segundo plano) |

## Instalación

Requisitos: Python 3.11+

```bash
python -m venv venv
venv\Scripts\pip install faster-whisper sounddevice numpy keyboard pystray Pillow
venv\Scripts\python voice_assistant.py
```

## Arranque automático

- **Carpeta "Inicio"**: arranca el **watchdog** (`watchdog.pyw`) oculto → escucha F1
  y levanta el asistente cuando hace falta.
- **Escritorio**: acceso directo para iniciar el asistente manualmente.

> ⚠️ Si los hotkeys no responden, ejecutar como **administrador**.