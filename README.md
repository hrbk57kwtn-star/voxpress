# 🎙️ Asistente de Transcripción por Voz

> **Versión: `v1.2.0-beta`**
> Cambio de plan: se retiró el motor de conversación hablada (IA + voz de respuesta)
> y se dejó **solo transcripción por voz** (dictado).

Herramienta de **dictado por voz** para Windows, 100% local y en **español**.
Hablas y el texto aparece escrito automáticamente donde esté el cursor.

## Características

- 🎤 **Reconocimiento de voz en español** con [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (modelo `base`, CPU int8)
- ✍️ **Dictado**: el texto se pega automáticamente en la ventana activa
- 🟢🔴 **Señalizador flotante**: verde = listo, rojo = grabando (abajo a la derecha)
- 🔁 **Vigilante (watchdog)**: con **F1** el asistente se vuelve a iniciar
  aunque lo hayas cerrado + auto-respawn por heartbeat cada 4s
- 🚀 **Arranque automático con Windows** (inicia oculto, sin ventana)
- ⌨️ **Hotkeys nativos RegisterHotKey** — funciona desde cualquier ventana,
  incluso oculto (pythonw), sin necesidad de administrador
- 🛡️ **Instancia única + log `assistant.log`** para diagnóstico

## Teclas

| Tecla | Función |
|-------|---------|
| **F9** | Iniciar/detener grabación → pega el texto donde esté el cursor |
| **F10** | Salir (principal) |
| **F12** | Salir (alternativa, si está libre) |
| **F1** | Reiniciar el asistente (lo maneja el watchdog, corre en segundo plano) |

> ⚠️ En este PC **F12 está ocupado por otro programa** (error 1409 de
> `RegisterHotKey`). Por eso la salida es **F10**. El log lo avisa:
> `AVISO: F12 ocupado por otro programa... se usa F10 para salir.`

## Instalación

Requisitos: Python 3.11+

```bash
python -m venv venv
venv\Scripts\pip install faster-whisper sounddevice numpy onnxruntime
venv\Scripts\python voice_assistant.py
```

> Versiones probadas: `huggingface-hub==1.28.0`, `ctranslate2==4.8.1`,
> `tokenizers==0.23.1`. Con `huggingface-hub 1.30` la carga online se
> colgaba (+120s por rate-limit sin token).

> Ya no se usan `keyboard` ni `pystray` (daban cuelgues en `pythonw`).
> Los hotkeys van por `RegisterHotKey` nativo (`hotkeys.py`) y el
> indicador es una ventana tkinter flotante.

## Arranque automático

- **Carpeta "Inicio"**: arranca el **watchdog** (`watchdog.pyw`) oculto → escucha F1
  y levanta el asistente cuando hace falta.
- **Escritorio**: acceso directo para iniciar el asistente manualmente.
- Los lanzadores `.bat` / `.vbs` usan ruta relativa (`%~dp0`), funcionan
  en cualquier carpeta, no solo en `C:\Users\nicoo\voice-assistant`.

## Si parece "iniciado pero trabado"

Causas encontradas el 2026-09-05 (medido: ~27s de carga del modelo `base` en CPU):

1. **Carga del modelo sin aviso**: al arrancar tarda unos segundos en
   `WhisperModel(base)`. Desde v1.2.0 se usa el modelo en cache con
   `HF_HUB_OFFLINE=1` (≈3-6s en vez de 27s online o +120s colgado por
   rate-limit). Mirar `assistant.log` → `Modelo Whisper listo` +
   `Asistente ACTIVO`. Para descargar un modelo nuevo, correr una vez
   con `HF_HUB_OFFLINE=0`.
2. **Doble-clic durante la carga**: antes el candado de instancia única
   se activaba DESPUÉS de cargar el modelo, así que 2-5 copias cargaban
   el modelo a la vez y colgaban el PC. Desde v1.2.0 el chequeo es
   ANTES de cargar (`Ya hay otra instancia... Saliendo sin cargar modelo`).
3. **F12 ocupado (error 1409)**: otro programa ya registró F12, el
   asistente no puede usarlo para salir. Se usa **F10**.
4. **Versión vieja v1.1.0** (`keyboard` + `pystray` en hilo demonio) se
   colgaba en `pythonw` / sin admin. La v1.2.0 usa `RegisterHotKey`
   nativo, estable en oculto.

## Cambios en v1.2.0-beta (2026-09-05)

Corrige el "figura iniciado pero se traba y no funciona" de v1.1.0:

1. **Hotkeys nativos** (`hotkeys.py` nuevo): `RegisterHotKey` de Windows
   en vez de la librería `keyboard`. Funciona oculto con `pythonw` y sin
   administrador. Se eliminó `pystray` (su icono en hilo demonio colgaba
   el proceso); el indicador ahora es una ventana tkinter flotante
   (🟢 listo / 🔴 grabando).
2. **Tecla de salida F10**: F12 está ocupado por otro programa en este PC
   (error 1409). F10 es la salida principal y F12 queda como alternativa
   si está libre; el log avisa cuál se registró.
3. **Instancia única temprana**: el candado por socket se comprueba antes
   de cargar el modelo pesado. Una segunda copia sale en ~1s sin cargar
   nada en vez de colgar el PC cargando otro modelo.
4. **Carga offline del modelo**: `HF_HUB_OFFLINE=1` usa el modelo en cache
   (≈3-6s). Evita el cuelgue de +120s por rate-limit de HuggingFace sin
   token (`huggingface-hub 1.30`). Versiones fijadas:
   `huggingface-hub==1.28.0`, `ctranslate2==4.8.1`, `tokenizers==0.23.1`.
5. **Rutas relativas**: `watchdog.pyw`, `.bat` y `.vbs` ya no apuntan a
   `C:\Users\nicoo\voice-assistant`; usan la carpeta del script, así el
   repo funciona clonado en cualquier ubicación.
6. **Diagnóstico**: todo queda en `assistant.log` (carga del modelo,
   hotkeys registradas, transcripciones, errores) + `heartbeat.txt` para
   el auto-respawn del watchdog cada 4s.