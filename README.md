# 🎙️ Asistente de Transcripción por Voz

> **Versión: `v1.2.0-beta`**

Herramienta de **dictado por voz** para Windows, 100% local y en **español**.
Hablas y el texto aparece escrito automáticamente donde esté el cursor.

## Funciones

- 🎤 **Reconocimiento de voz en español** con [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (modelo `base`, CPU int8)
- ✍️ **Dictado**: el texto transcrito se pega automáticamente en la ventana
  activa (portapapeles + Ctrl+V)
- 🟢🔴 **Señalizador flotante**: ventana siempre visible abajo a la derecha
  que muestra el estado (ver tabla de colores abajo)
- 🔁 **Vigilante (watchdog)**: corre oculto en segundo plano; con **F1**
  levanta el asistente si está cerrado y lo reanima solo cada 4s
  (control por `heartbeat.txt`)
- 🚀 **Arranque automático con Windows** (inicia oculto, sin ventana)
- ⌨️ **Hotkeys nativos** (`RegisterHotKey` de Windows): funcionan desde
  cualquier ventana, incluso oculto (`pythonw`), sin administrador
- 🛡️ **Instancia única**: si ya hay una copia corriendo, la segunda sale
  al instante sin cargar el modelo
- 📝 **Diagnóstico**: todo queda en `assistant.log` (carga del modelo,
  hotkeys, transcripciones, errores)

## Teclas

| Tecla | Función |
|-------|---------|
| **F9** | Iniciar/detener grabación → pega el texto donde esté el cursor |
| **F10** | Salir del asistente |
| **F1** | Reiniciar el asistente (la atiende el watchdog en segundo plano) |

## Indicador en pantalla: colores y mensajes

Ventana flotante semi-transparente, siempre al frente, abajo a la derecha.

| Estado | Texto que muestra | Color del texto | Fondo | Cuándo aparece |
|--------|-------------------|-----------------|-------|----------------|
| Listo | ● LISTO | Verde `#00ff66` | Gris oscuro `#111111` | En espera, puedes dictar con F9 |
| Grabando | ● GRABANDO... | Rojo `#ff3355` | Rojo oscuro `#220000` | Te está escuchando (F9 para detener) |
| Iniciado | INICIADO | Naranja `#ff8800` | `#332000` | Al arrancar (1,2 s) |
| Iniciado por F1 | INICIADO | Celeste `#55ccff` | `#002233` | Al arrancar con F1 del watchdog (1,2 s) |
| Saliendo | EXIT | Amarillo `#ffcc00` | `#332200` | Al pulsar F10, antes de cerrarse |

## Lo que se corrigió en esta versión

1. **Hotkeys nativos** (archivo nuevo `hotkeys.py`): `RegisterHotKey` de
   Windows en vez de la librería `keyboard`. Funciona oculto con `pythonw`
   y sin administrador. Se eliminó el icono de bandeja `pystray` (colgaba
   el proceso en un hilo); ahora el estado se ve en la ventana flotante.
2. **Tecla de salida F10**: reemplaza a la anterior, que estaba ocupada
   por otro programa del sistema.
3. **Instancia única temprana**: el candado se comprueba antes de cargar
   el modelo pesado. Una segunda copia sale en ~1 s sin cargar nada, en
   vez de colgar el PC cargando otro modelo a la vez.
4. **Carga offline del modelo**: usa el modelo en cache (`HF_HUB_OFFLINE=1`,
   ≈3-6 s) y evita cuelgues de red por límite de HuggingFace sin token.
   Versiones fijadas: `huggingface-hub==1.28.0`, `ctranslate2==4.8.1`,
   `tokenizers==0.23.1`. Para descargar un modelo nuevo, correr una vez
   con `HF_HUB_OFFLINE=0`.
5. **Rutas relativas**: `watchdog.pyw`, `.bat` y `.vbs` usan la carpeta del
   script, así el repo funciona clonado en cualquier ubicación.
6. **Diagnóstico**: log con hora de cada evento y marca de vida para el
   auto-respawn del watchdog.

## Instalación

Requisitos: Python 3.11+

```bash
python -m venv venv
venv\Scripts\pip install faster-whisper sounddevice numpy onnxruntime
venv\Scripts\python voice_assistant.py
```

## Arranque automático

- **Carpeta "Inicio"**: arranca el **watchdog** (`watchdog.pyw`) oculto →
  escucha F1 y levanta el asistente cuando hace falta.
- **Escritorio**: acceso directo para iniciar el asistente manualmente.

## Si parece "iniciado pero trabado"

1. **Carga del modelo**: al arrancar tarda unos segundos en
   `WhisperModel(base)` (≈3-6 s con el modelo en cache). No tocar nada y
   mirar `assistant.log` → `Modelo Whisper listo` + `Asistente ACTIVO`.
2. **Doble-clic durante la carga**: si se abre dos veces seguidas, la
   segunda copia detecta a la primera y sale sola
   (`Ya hay otra instancia... Saliendo sin cargar modelo`).
