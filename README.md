# 🎙️ VoxPress

**Press F9, speak, done.** Dictado por voz offline en español para Windows.

> **Versión: `v2.0.1`**

VoxPress escucha tu voz y escribe el texto donde esté el cursor, en
cualquier programa: chat, documentos, correo, formularios. Todo ocurre
en tu PC — nada se sube a internet.

## Funciones

- 🎤 **Español preciso**: reconocimiento con Whisper (`base`, CPU int8),
  afinado para dictado en español con tildes y ñ
- ✍️ **Pega solo**: al cortar la grabación el texto aparece donde esté
  el cursor (portapapeles + Ctrl+V)
- 🟢🔴 **Señalizador flotante**: ventana siempre visible abajo a la
  derecha con el estado actual (ver colores abajo)
- 🔁 **Vigilante automático**: corre oculto; con **F1** levanta el
  programa si está cerrado y lo reanima solo si se cae
- 🚀 **Arranque con Windows** (oculto, sin ventana)
- ⌨️ **Teclas globales**: funcionan desde cualquier ventana, sin
  administrador
- 🔒 **100% local y privado**: modelo y audio nunca salen de tu máquina
- 🛡️ **Instancia única** + registro de eventos en `assistant.log`

## Teclas

| Tecla | Función |
|-------|---------|
| **F9** | Grabar / cortar y pegar lo dictado |
| **F10** | Salir |
| **F1** | Reiniciar (la atiende el vigilante en segundo plano) |

## Colores del indicador

| Estado | Texto | Color | Cuándo |
|--------|-------|-------|--------|
| Listo | ● LISTO | Verde | En espera, pulsa F9 para dictar |
| Grabando | ● GRABANDO... | Rojo | Te está escuchando (F9 para cortar) |
| Transcribiendo | TRANSCRIBIENDO... | Amarillo | Convirtiendo tu voz en texto |
| Iniciado | INICIADO | Naranja (celeste si viene de F1) | Al arrancar |
| Saliendo | EXIT | Amarillo | Al pulsar F10 |

## Novedades v2.0.1

1. **Confianza % por dictado**: el log muestra la confianza del modelo
   (`Confianza: 88%`). Guía: 85-99% normal; bajo 60% conviene revisar
   el texto. No es exactitud palabra por palabra, es el termómetro del
   modelo en ese dictado.
2. **Guardia doble anti-duplicados**: si ya hay una copia activa, la
   segunda se cierra sola sin cargar el modelo (socket + verificación
   de proceso con heartbeat fresco).

## Velocidad

Medido en un i3-7020U (CPU modesto, sin GPU), modelo en cache:

- Pegado: ~2 ms · Recorte de silencio: ~6 ms
- Transcripción: ~2 s por dictado (3 s u 11 s de audio tardan parecido)
- Arranque: modelo listo en ~3-6 s

## Precisión honesta

VoxPress puede cometer **pequeños errores al transcribir (un porcentaje
bajo, típico de un dígito en audio claro)**. La precisión depende del
micrófono, la distancia a la boca y el ruido del ambiente:

- ✔ Habitación tranquila + micrófono a 10-15 cm: errores mínimos.
- ✔ Ruidos suaves de fondo: el programa los ignora solo.
- ⚠ Ruido fuerte (tele alta, gente hablando al lado): puede confundir
  palabras — ningún programa gratuito con un solo micrófono lo evita.
- 👉 Revisa siempre textos importantes antes de enviarlos.

## Preguntas frecuentes

**¿Qué necesito?**
Windows 10/11, Python 3.11+ y micrófono. Sin placa de video.

**¿Funciona sin internet?**
Sí. El modelo se descarga una sola vez (≈150 MB); después todo es
offline. Para descargarlo, corre una vez con `HF_HUB_OFFLINE=0`.

**¿Cómo dicto?**
Pulsa **F9**, habla, pulsa **F9** de nuevo. El texto se pega solo.

**¿Por qué tarda ~2 segundos al cortar?**
Es la transcripción local en CPU. El cartel amarillo TRANSCRIBIENDO...
te avisa mientras trabaja.

**¿Mi voz sale de mi PC?**
No. Audio y modelo quedan en tu máquina. Sin cuentas ni nube.

**¿Cómo salgo? ¿Y si se traba?**
**F10** sale. **F1** lo vuelve a levantar (vigilante en segundo plano).
Si abres dos copias, la segunda se cierra sola.

**¿En qué idioma transcribe?**
Español (fijado, sin detección automática para ir más rápido).

## Instalación

```bash
python -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\python voice_assistant.py
```

## Arranque automático

- **Carpeta Inicio de Windows**: pone el **watchdog** (`watchdog.pyw`)
  oculto → escucha F1 y levanta el programa cuando hace falta.
- **Escritorio**: acceso directo con `start_assistant.bat` / `.vbs`.

## Licencia

MIT — © 2026 hrbk57kwtn-star. Puedes usar, modificar y compartir este
programa libremente, manteniendo el aviso de autoría (ver `LICENSE`).
