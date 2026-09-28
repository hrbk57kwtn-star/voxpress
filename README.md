# 🎙️ VoxPress

**Press F9, speak, done.** Dictado por voz offline en español para Windows.

> **Versión: `v2.1.2`**

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
  programa si está cerrado y lo reanima solo si se cae. Espera cada vez
  más entre reintentos para no entrar en bucle
- 🚀 **Arranque con Windows** (oculto, sin ventana)
- ⌨️ **Teclas globales**: funcionan desde cualquier ventana, sin
  administrador
- 🔒 **100% local y privado**: modelo y audio nunca salen de tu máquina
- 🛡️ **A prueba de cuelgues**: las teclas se rearman solas si se quedan
  mudas, y el programa se reinicia si algo deja de responder
- 🧹 **Instancia única** (programa y vigilante) + registro en `assistant.log`

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

## Novedades v2.1.2

El foco de esta versión: **F9 se quedaba muerto sin avisar**. El programa
seguía con la ventana en pantalla, el proceso vivo y el vigilante
tranquilo, pero la tecla no hacía nada. Y no había forma de recuperarlo
desde el programa.

### El fallo y su causa

1. **La causa raíz**: las teclas se registraban sobre una **ventana
   oculta** propiedad del hilo que las atendía. Una ventana pertenece al
   hilo que la creó, así que al morir ese hilo Windows la destruía y la
   tecla quedaba **huérfana**: ya no entregaba mensajes,
   `UnregisterHotKey` fallaba y otra `RegisterHotKey` devolvía *«1409 ya
   registrada»* — por eso parecía sana, y era irrecuperable.
   **Ahora** las teclas se asocian al **hilo**, sin ventana de por medio:
   no hay nada que se pueda perder.
2. **Las teclas se rearman solas**: si el hilo que las atiende se queda
   mudo, se detecta y se rearma (≤ 6 s). Si eso no alcanza, el heartbeat
   deja de refrescarse y el vigilante reinicia el programa.
3. **Heartbeat honesto**: antes lo escribía un hilo aparte que sobrevivía
   a todo, así que el vigilante veía «todo bien» con las teclas muertas.
   Ahora solo se refresca si las teclas **y** la ventana están vivas.
4. **El vigilante no reiniciaba en bucle**: con un umbral de 9 s mataba
   al asistente mientras aún cargaba el modelo y lo relanzaba, y ese
   tampoco alcanzaba a escribir su heartbeat. Resultado: 20 arranques en
   2 minutos, 200 MB de modelo cada uno, y el proceso **nunca llegaba a
   terminar de arrancar**. El umbral subió a 30 s.
5. **Un solo vigilante**: si abres dos, el segundo se retira solo. Antes
   peleaban por F1 y por la decisión de cuándo reiniciar el asistente.
6. **El vigilante espera cada vez más** entre reintentos (45 s, 90 s,
   180 s… hasta 10 min), para que si algo está realmente roto no se
   quede cargando el modelo en bucle.
7. **Vigilante y teclas supervisados**: si el hilo de teclas o el de
   reintentos mueren, se relanzan solos.
8. **Logs rotados a 2 MB**: un bucle de reintentos llenaba el disco.
9. **El cartel se actualiza por cola**, solo desde su propio hilo, y ya
   no roba la ventana de al frente cada 10 s (eso le fastidiaba a otras
   apps, como las terminales con TUI).
10. **Instancia única corregida**: el candado se reintentaba al arrancar
    y liberaba el socket del guardián, dejando inútil la protección.

## Velocidad

Medido en CPU modesto sin GPU, modelo en cache:

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

**¿F9 dejó de responder! ¿Qué hago?**
Desde v2.1.2 ya no debería pasar, y si pasara se arregla solo. Aun así:
espera unos segundos (el rearme tarda ≤ 6 s) y si sigue igual, mira la
última línea de `assistant.log`:
- `Bomba de hotkeys rearmada OK` → se recuperó sola, ya estás.
- `dejo de refrescar el heartbeat` → el vigilante lo reinicia en ~30 s.
Si no se recupera, pulsa **F1**.

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
