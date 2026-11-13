# Arquitectura de Zebamp

Guía para quien vaya a leer o cambiar el código. Para usar el programa está la
ayuda integrada (F1).

## La idea en una frase

Zebamp **no reproduce audio**: es un mando a distancia de **MPD** con el
aspecto de Winamp. MPD tiene el estado (cola, posición, volumen…); Zebamp lo
refleja y le envía órdenes.

```
            órdenes (play, add, seek…)
  Zebamp  ───────────────────────────────▶  MPD  ──▶ PipeWire ──▶ altavoces
   ▲  ▲         estado + eventos "idle"      │          ▲
   │  └──────────────────────────────────────┘          │ filtro "Zebamp EQ"
   │            audio del fifo / captura PipeWire       │ (ecualizador)
   └──────────────── visualización ◀────────────────────┘
```

## Capas

| Capa | Módulos | Qué hace |
|---|---|---|
| Conexión | `mpdconn.py` | Conexión principal, reconexión automática, hilo `idle` (eventos de MPD) y trabajos en segundo plano con su propia conexión. |
| Modelo | `player.py`, `stats.py`, `libindex.py`, `config.py` | `Player` refleja el estado de MPD y emite señales Qt (`statusChanged`, `songChanged`, `queueChanged`…). El resto del programa cambia el estado de MPD a través de `Player`. |
| Controlador | `app.py` | `ZebampApp`: crea todo, elige el skin, menús, atajos de teclado, ventanas sueltas con imán. |
| Interfaz clásica | `ui/base.py`, `ui/mainwin.py`, `ui/eqwin.py`, `ui/plwin.py`, `ui/lyricspanel.py`, `skin/` | Paneles dibujados píxel a píxel con los bitmaps del skin `.wsz`. |
| Interfaz moderna | `modern/` | Motor de skins de Winamp 3/5 (`.wal`): XML (`xmlparse`, `skin`), objetos gráficos (`gui`), intérprete de scripts MAKI (`maki`) y ventanas (`engine`). |
| Ventanas comunes | `ui/dialogs.py`, `ui/library.py`, `ui/radio.py`, `ui/lyrics.py`, `ui/help.py`… | Diálogos Qt normales con la paleta del skin. |
| Letras | `lyricsync.py` (lógica pura: LRC, versión, sincronización), `lyricsfind.py` (fuentes: `.lrc`, etiquetas, caché, LRCLIB), `ui/lyrics.py`, `ui/lyricspanel.py` | Las dos vistas comparten `LyricsState`; la lógica se prueba sin interfaz (`tests/test_lyrics.py`). |
| Audio y vídeo | `vis.py`, `milkdrop.py`, `audio/` | Visualización (FFT del audio de MPD), MilkDrop (projectM vía `native/pmshim.cpp`), ecualizador en PipeWire. |
| Escritorio | `mpris.py`, `tray.py`, `notify.py`, `ipc.py`, `compositor.py` | Teclas multimedia, bandeja, notificaciones, una sola instancia y órdenes `zebamp --…`. `compositor.py` reúne lo que hay que pedirle a cada compositor (sway, Hyprland): dónde están los monitores, mover el lienzo, dar el foco. |
| Calidad del audio | `audioquality.py`, `ui/quality.py` | Decodifica con ffmpeg en flujo (nunca la canción entera en memoria), calcula el espectrograma y el espectro medio con numpy, busca el corte de un formato con pérdida y redacta el veredicto. |
| Qué canción es | `songid.py` | Nombres para buscar cuando faltan las etiquetas: el nombre del archivo o, con la clave del usuario, la huella de audio (`fpcalc`) consultada en AcoustID. Se recuerda por archivo. |
| Carátulas | `notify.py` (`fetch_cover_job`: lo local), `localcover.py` (qué imagen de la carpeta es la portada), `coverfind.py` (Internet) | Primero la imagen incrustada, la de MPD y la carpeta; si no hay y el usuario lo permite, `coverfind` busca con coincidencia estricta y guarda una carátula por álbum. |
| Extras | `smartlist.py`, `scrobble.py`, `sleeptimer.py`, `profiles.py` | Lógica pura con sus pruebas (listas por reglas, peticiones de scrobbling, fin de álbum, perfiles de servidor); sus ventanas están en `ui/`. |
| Idiomas | `i18n.py`, `data/i18n/en.json`, `ui/help_en.py` | El texto del código es español; `tr("…")` lo devuelve en el idioma elegido al arrancar. |

## Cómo fluye un cambio

1. El usuario pulsa «siguiente» → el panel llama a `app.player.next()`.
2. `Player` envía `next` a MPD por `MpdConnection.call()`.
3. MPD avisa por el hilo `IdleThread` (subsistemas `player`, `playlist`…).
4. `Player` relee el estado y emite `songChanged` / `statusChanged`.
5. Cada ventana, MPRIS, la bandeja, las estadísticas… escuchan esas señales y
   se actualizan. **La interfaz no supone el resultado**: espera a MPD. Así lo
   que haga otro cliente (ncmpcpp, el móvil) se ve igual.

## Ventanas sueltas con imán (Wayland)

En Wayland una aplicación no puede colocar sus propias ventanas. Por eso los
skins usan un **lienzo**: una ventana transparente del tamaño del monitor; las
ventanas del skin son hijas dentro de él y la máscara de entrada deja pasar los
clics al escritorio (`canvas.py`, `ModernDock`, `ZebampApp._relayout_free`).

- Las posiciones se guardan relativas al origen del lienzo (`_origin`).
- El lienzo cubre **solo el monitor donde están las ventanas**, así Zebamp vive
  en un solo escritorio. Se abre al otro monitor únicamente cuando el usuario
  arrastra una ventana hasta tocarlo (`reaches_other_monitor`).
- `DragFrame` distingue un clic de un arrastre y traduce los eventos que llegan
  con coordenadas viejas cuando el lienzo se mueve.

## Hilos

La interfaz corre en un único hilo (el de Qt). Lo que puede tardar va fuera:

| Qué | Dónde |
|---|---|
| Esperar eventos de MPD | `IdleThread` (`mpdconn.py`) |
| Consultas largas a MPD (carátulas, índice de la biblioteca, stickers) | `MpdConnection.run_async` (conexión propia por trabajo) |
| HTTP (letras, radio), `pw-dump`, escaneos de `/proc` | `threads.run_bg` |
| Ecualizador en PipeWire | hilo `zebamp-pw` (`audio/pipewire.py`) |

Los resultados vuelven al hilo de la interfaz con señales Qt; ningún hilo toca
widgets.

## Reglas de la casa (buenas prácticas del proyecto)

Salen de medir el programa; respétalas al cambiar el código.

**Recursos**

- **Nada se despierta sin motivo.** Los temporizadores solo corren mientras
  hacen falta: el reloj de los paneles mientras están visibles, las
  estadísticas mientras suena algo, el texto desplazable baja a 1 Hz cuando no
  hay nada que mover, la visualización se para con Zebamp oculto.
- **Repintar solo lo que cambia**: `update(rect)` del objeto, nunca la ventana
  entera; el motor moderno pinta solo la región dañada (`ev.region()`).
- **No recorrer árboles grandes en cada fotograma**: el motor moderno usa un
  índice por tipo (`ModernEngine._each`) que se invalida con `tree_changed()`.
- **Nada bloqueante en el hilo de la interfaz** (red, disco, procesos): usa
  `run_bg` / `run_async`. Con MPD caído no se reintenta en cada llamada (lo
  hace el temporizador de reconexión).
- **Cerrar lo que se abre**: sockets, procesos hijos (`QProcess.startDetached`
  o `wait()`), archivos con `with`. Las pruebas no deben mostrar
  `ResourceWarning`.

**Legibilidad**

- Una función, una tarea; nombres que se expliquen solos (nada de `l`, `I`).
- Comentarios para el **porqué**, no para el qué.
- Cada módulo empieza con una descripción de lo que contiene.
- Las tablas (atajos, sprites, acciones) se mantienen alineadas como tablas.

**Fiabilidad**

- **Los datos de fuera no se dan por buenos** (Internet, etiquetas, archivos
  del usuario): se comprueban tipos y formatos y, si algo no encaja, se trata
  como «no encontrado», nunca como un fallo.
- La lógica va separada de la interfaz y con pruebas propias (ejemplo: las
  letras).

- La configuración del usuario es sagrada: las pruebas usan un
  `XDG_CONFIG_HOME` temporal y `Config.save()` se niega a escribir la real con
  `ZEBAMP_TESTING`.
- Un objeto de skin roto no debe dejar la ventana en blanco: los errores de
  pintado y de scripts se registran y se sigue.

## Idiomas

- Todo texto que ve el usuario va dentro de `tr("…")`, **con el texto literal**
  (no una variable): una prueba recoge esos textos del código y falla si a
  alguno le falta su traducción en `data/i18n/en.json`, o si sobra alguna.
- Con datos dentro, se usa una plantilla: `tr("Quedan {0}").format(tiempo)`;
  la traducción debe conservar los mismos `{0}`, `{1}`…
- El idioma se fija al arrancar (`i18n.setup()` en `__main__.py`, antes de
  importar las ventanas). Por eso las tablas de etiquetas se pueden traducir
  donde se definen, y por eso cambiar de idioma pide reiniciar.
- Las pruebas corren en español (nadie llama a `setup()`); el inglés se prueba
  en un proceso aparte, igual que arranca `zebamp --lang en`.
- La ayuda tiene un módulo por idioma (`ui/help.py`, `ui/help_en.py`) con las
  mismas secciones y enlaces; otra prueba vigila que no se separen.

## Comprobar el código

```sh
uvx ruff check .                       # normas (pyproject.toml): estilo y patrones de error
python -m unittest discover -s tests   # pruebas (usan un MPD privado, no el tuyo)
uvx radon cc zebamp -a                 # complejidad (media actual: A)
```

## Números de referencia (8-11-2026, 1.0.0rc1)

CPU de Zebamp medida durante 8 s con un MPD de pruebas (`s_cpu`: sonando,
pausa, parado, oculto):

| Situación | Skin clásico | Big Bento |
|---|---|---|
| Sonando con visualización | 3–3,5 % | 6,3 % |
| Sonando sin visualización | 0,4 % | 2,5 % |
| En pausa / parado | 0,3–0,4 % | 1,4 % |
| Oculto en la bandeja | 0,1 % | 0,2 % |

Las cifras absolutas cambian con el estado de la máquina (frecuencia de la
CPU, otros programas): **compara siempre dos versiones en la misma sesión**.
Para saber qué commit empeoró algo, mide cada uno en un `git worktree` aparte
(bisección). Si un cambio empeora mucho estos números, algo se está
despertando o repintando de más; los repintados se pueden contar envolviendo
`ModernEngine.request_repaint`.
