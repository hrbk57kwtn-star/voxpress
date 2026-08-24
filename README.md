# 🎙️ Asistente de Voz

> **Versión: `v0.3.0-beta`**
> Proyecto en desarrollo activo. Las versiones beta se van publicando
> (`v0.3.0-beta`, `v0.4.0-beta`, ...) hasta llegar a la versión final `v1.0.0`.

Asistente personal de voz para Windows, 100% local y en **español (rioplatense)**.
Habla con tu PC: te escucha, te entiende y **hace cosas** (no solo charla).

## Características

- 🎤 **Reconocimiento de voz en español** con [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- 🧠 **IA local** con [Ollama](https://ollama.com) (modelo `llama3.2:3b`) — privado, sin costo, sin nube
- 🔊 **Voz de respuesta** con Microsoft Sabina (TTS en español)
- 📊 **Calibración automática** del micrófono según el ruido ambiente de la habitación
- ✂️ **Detección automática de fin de habla** (corta la grabación cuando detecta silencio)
- 🤖 **Detección de comandos robusta**: tolera errores de transcripción de Whisper
- 🗃️ **Memoria de conversación**: recuerda el contexto para charlas de ida y vuelta
- ⌨️ **Hotkeys globales** — funciona desde cualquier ventana

## Teclas

| Tecla | Función |
|-------|---------|
| **F8** | Conversar: hablás → la IA responde **en voz alta** |
| **F9** | Dictar: el texto se pega donde esté el cursor |
| **F10** | Activa/desactiva el modo palabra clave ("asistente...") |
| **F12** | Salir |

## Comandos de voz

| Decís... | Hace... |
|----------|---------|
| *"Abrime el navegador"* | Abre Chrome |
| *"Abrime YouTube / WhatsApp / Telegram"* | Abre la web correspondiente |
| *"Buscame vuelos a Mendoza"* | Investiga: abre Google, busca en Wikipedia y te **lee un resumen** |
| *"Investigá qué es la CNRT"* | Idem |
| *"Buscame en YouTube ..."* | Abre YouTube con la búsqueda |
| *"Buscame el archivo autorización"* | Recorre tus carpetas, te dice dónde está y lo **abre en el Explorador** |
| *"¿Qué hora es?"* / *"¿Qué día es hoy?"* | Te responde al instante |
| Cualquier otra cosa | Charla con la IA y te responde hablando |

## Instalación

Requisitos: Python 3.11+, [Ollama](https://ollama.com) con el modelo:

```bash
ollama pull llama3.2:3b
```

```bash
python -m venv venv
venv\Scripts\pip install faster-whisper sounddevice numpy keyboard pyttsx3
python voice_assistant.py
```

> ⚠️ Si los hotkeys no responden, ejecutar como **administrador**.

## Pendientes por mejorar (TODO)

- [ ] Palabra clave con micrófono siempre encendido más eficiente
- [ ] Modelo Whisper "medium" opcional para ambientes ruidosos (más lento en CPU)
- [ ] Más comandos: volumen, abrir programas, cerrar pestañas del navegador
- [ ] Interfaz gráfica simple con estado (escuchando / pensando / hablando)
- [ ] Arranque automático con Windows sin ventana de consola visible
- [ ] Comandos por configuración externa (archivo YAML/JSON)
