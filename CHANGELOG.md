# Registro de cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/);
versiones según [PEP 440](https://peps.python.org/pep-0440/).

## Sin publicar

### Nuevo
- **Listas inteligentes**: listas por reglas (género, valoración, veces
  escuchada, año, duración, días sin escucharla…) que se mantienen solas, con
  su editor en la biblioteca.
- **Scrobbling** a ListenBrainz y Last.fm (apagado por defecto); las escuchas
  se guardan sin conexión y se envían después.
- **Ventana de carátula** para los skins clásicos (Ctrl+Shift+A), acoplable y
  redimensionable.
- **Temporizador de apagado**: pausa en N minutos o al terminar el álbum.
- **Perfiles de servidor MPD** para cambiar de servidor desde el menú.
- **Interfaz y ayuda en inglés** (Opciones › Idioma, `--lang en`); el español
  sigue siendo el idioma por defecto.
- **MilkDrop en la pestaña de visualización** de los skins modernos (Bento,
  Big Bento).
- Soltar archivos sobre la ventana principal, el ecualizador o las letras los
  reproduce; un skin soltado se instala.
- Paquete para Arch Linux (`packaging/PKGBUILD`) y pruebas automáticas en
  GitHub con cada cambio.
- Soporte experimental de **Hyprland** (`hyprctl`) y modo genérico para otros
  compositores; el código que habla con el compositor vive ahora en
  `zebamp/compositor.py`.

- **Carátulas de Internet** para la música que no trae ninguna: identificador
  de MusicBrainz de las etiquetas, o artista + álbum (o artista + título +
  duración) en MusicBrainz, Deezer e iTunes, aceptando solo coincidencias
  estrictas. Se puede rechazar una carátula equivocada.
- **Canciones sin etiquetas**: se usa el nombre del archivo («Artista -
  Título») y, con una clave de AcoustID, se **reconocen por su sonido**
  (huella de audio con `fpcalc`): para la carátula y, desde la ventana de
  información, para proponer las etiquetas.
- Detector de atascos: si MPD está en «play» sin avanzar, guarda un
  diagnóstico del audio en `~/.cache/zebamp/atascos/`.

### Arreglado
- Al mover la ventana principal a 2x o 3x, una ventana pegada (letras, lista)
  podía quedar 1 px desfasada y dejar de moverse con el grupo.
- Ctrl+Shift+A ya no selecciona toda la lista.

### Interno
- Las ventanas de letras y carátula comparten el marco (`ui/genpanel.py`).
- El índice de la biblioteca guarda el año (se reconstruye una vez).
- 185 pruebas automáticas (eran 70).

## 1.0.0rc1 - 2026-11-08

Primer candidato a versión. Todo es nuevo; este resumen agrupa lo que incluye.

### Reproductor
- Cliente de MPD con el manejo de Winamp: transporte, posición, volumen,
  balance, aleatorio, repetir (no / lista / pista), consumir, parar tras la
  pista, fundido, MixRamp y ReplayGain.
- «A continuación» que funciona también con el aleatorio activado (prioridades
  de MPD).
- Búsqueda instantánea en toda la biblioteca (probada con 107 000 canciones);
  atajo global en sway (Super+Shift+S, `zebamp --buscar`).
- Biblioteca de medios con vistas inteligentes (más escuchadas, mejor
  valoradas, recientes), valoraciones y estadísticas en los stickers de MPD.
- Radio por Internet (radio-browser.info), marcadores, editor de etiquetas con
  confirmación, salidas de audio de MPD.

### Skins
- Skins clásicos `.wsz` con todos sus bitmaps, regiones, cursores y colores;
  ampliación Scale2x/Scale3x sin pixelado.
- Skin interno «Zebamp» original, vectorial y nítido a cualquier tamaño.
- Skins modernos `.wal` (Winamp 3/5) con su máquina virtual MAKI: Winamp
  Modern, Bento, Big Bento y otros; temas de color de Winamp 5.
- Ventanas sueltas con imán que recuerdan su posición, también entre dos
  monitores; un clic nunca las cambia de pantalla.
- kbps y kHz completos para audio de alta resolución (1411 kbps, 192 kHz) y
  tooltip con el formato.

### Letras
- Ventana de letras con el aspecto del skin clásico, acoplable con imán.
- Fuentes por orden: `.lrc` junto a la canción, etiquetas del archivo,
  LRCLIB eligiendo la versión de duración más parecida.
- Ajuste automático de velocidad para versiones aceleradas; Mayús+clic en una
  línea para sincronizar a mano (desfase y velocidad), guardado por canción.

### Visualización
- Espectro y osciloscopio a la velocidad configurada; convive con ncmpcpp
  (captura de PipeWire si el fifo está ocupado).
- MilkDrop con projectM y su ventana de configuración; presets al azar.

### Escritorio
- MPRIS (teclas multimedia, playerctl, waybar), bandeja del sistema,
  notificaciones con carátula, asociaciones de archivos.
- Ecualizador de 10 bandas como filtro de PipeWire; cerrar Zebamp no corta la
  música.
- Ayuda integrada completa (F1 en cada ventana abre su sección).

### Calidad
- 70 pruebas automáticas (con un MPD privado, nunca el del usuario) y pruebas
  de estrés con miles de acciones aleatorias.
- Normas de código en `pyproject.toml` (`uvx ruff check .`) y guía de
  arquitectura en `docs/ARQUITECTURA.md`.
- Consumo medido: 0,1–0,4 % de CPU en reposo u oculto; 3–3,5 % (clásico) y
  6,3 % (Big Bento) con visualización. Los visualizadores ocultos de los skins
  modernos ya no se repintan.

### Limitaciones conocidas
- Compatibilidad parcial con skins modernos que dependen de componentes
  internos de Winamp (vídeo, AVS, navegador, librería Freeform).
- «Siempre visible» no tiene efecto en Wayland.
- Probado en Arch Linux con sway; en otros escritorios Wayland o en X11 la
  colocación de ventanas puede diferir.

