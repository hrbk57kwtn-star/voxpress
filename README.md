# 🎙️ Asistente de Transcripción por Voz

> **Versión: `v1.0.0-beta`**
> Cambio de plan: se retiró el motor de conversación hablada (IA + voz de respuesta)
> y se dejó **solo transcripción por voz** (dictado).

Herramienta de **dictado por voz** para Windows, 100% local y en **español**.
Hablas y el texto aparece escrito automáticamente donde esté el cursor.

## Características

- 🎤 **Reconocimiento de voz en español** con [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- ✍️ **Dictado**: el texto se pega automáticamente en la ventana activa
- 🔴🟢 **Indicador en la barra de tareas**: verde = listo, rojo = grabando
- 🚀 **Arranque automático con Windows** (inicia oculto, sin ventana)
- ⌨️ **Hotkeys globales** — funciona desde cualquier ventana

## Teclas

| Tecla | Función |
|-------|---------|
| **F9** | Iniciar/detener grabación → pega el texto donde esté el cursor |
| **F12** | Salir |

## Instalación

Requisitos: Python 3.11+

```bash
python -m venv venv
venv\Scripts\pip install faster-whisper sounddevice numpy keyboard pystray Pillow
venv\Scripts\python voice_assistant.py
```

## Arranque automático

Ya están creados dos accesos directos que apuntan a `start_assistant.vbs`
(inicia oculto con el ícono en la barra de tareas):

- **Arranque con Windows**: acceso en la carpeta "Inicio" del usuario
- **Inicio manual**: acceso en el **Escritorio**

> ⚠️ Si los hotkeys no responden, ejecutar como **administrador**.