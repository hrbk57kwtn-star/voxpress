# 🎙️ Asistente de Transcripción por Voz

> **Versión: `v1.2.2-beta`**

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
| Transcribiendo | TRANSCRIBIENDO... | Amarillo `#ffcc00` | `#332200` | Entre que cortas con F9 y se pega el texto |

## Lo que se aceleró en esta versión (v1.2.1)

Al cortar con F9, el texto se pega casi de inmediato:

1. **Pegado en-proceso**: el portapapeles se escribe directo con Windows
   (antes se lanzaba el programa `clip` + espera fija de 100 ms).
   Medido: ~150 ms → ~2 ms.
2. **Recorte de silencio**: se quita el silencio inicial/final antes de
   transcribir. Cada segundo recortado es ~1 s menos de espera
   (medido: 4,0 s → 1,3 s en ~6 ms de recorte).
3. **VAD más agresivo + inferencia afinada**: corta silencios largos y
   evita repeticiones (`condition_on_previous_text=False`), mismo modelo.
4. **Cartel TRANSCRIBIENDO...**: feedback instantáneo mientras convierte
   tu voz en texto.
5. **Tiempos en el log**: cada dictado registra `Corte`, `Inferencia`,
   `Pegado` y `Total F9->pegado` en ms para medir la velocidad real.
6. **Doble instancia**: al probar se encontró que corrían 2 copias a la
   vez; el candado de instancia única ya las detecta y la segunda sale
   en ~1 s.

El flujo no cambió: **F9** graba, **F9** corta y el texto se pega solo.

## Lo que se aceleró en v1.2.2 (medido, sin perder precisión)

Se compararon los parámetros cara a cara sobre la misma voz en español
(11,2 s, modelo `base` int8, i3-7020U). Texto resultado **idéntico** en
todos los casos:

| Configuración | Tiempo |
|---|---|
| v1.2.0 (VAD original) | 3163 ms |
| v1.2.0 + recorte de silencio | 2558 ms |
| v1.2.1 | 2526 ms |
| **v1.2.2 (`cpu_threads=2`)** | **2126 ms** |

Conclusiones honestas:

1. **v1.2.1 no aceleró la inferencia** (2526 vs 2558 ms, igual). Sus
   ganancias reales fueron el pegado (~150 → ~2 ms) y el recorte de
   silencio (~600 ms en 11 s de audio).
2. **El hilo ganador es `cpu_threads=2`** (= núcleos físicos del i3):
   ~15% más rápido que el default (4) con texto idéntico. Es el cambio
   de v1.2.2, junto a VAD en 500 ms con pad de 400 ms (salida idéntica
   a la original).
3. Límite real: en este CPU cada dictado cuesta ~2 s fijos de inferencia
   (3 s u 11 s de audio tardan casi lo mismo). Sin GPU no se puede
   bajar de ahí con el modelo `base`.

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
