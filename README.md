# Zebamp

Reproductor estilo Winamp 2.x/5 para **MPD**, escrito en Python + Qt 6 (PySide6).
Usa skins **clásicos** (`.wsz`) y **modernos** (`.wal`, Winamp 3/5).

Zebamp no reproduce audio por su cuenta: es un cliente de MPD. Todo lo que hace
(reproducir, cola, volumen, listas guardadas, biblioteca) va contra tu servidor MPD.

## Instalación

Requisitos (nombres de paquetes de Arch Linux):

| Para | Paquetes |
|---|---|
| Funcionar | `python` (3.11+), `pyside6`, `python-mpd2`, `python-numpy`, `mpd` |
| Editar etiquetas | `python-mutagen` |
| Teclas multimedia (MPRIS) | `python-dbus` |
| Ecualizador y captura de audio | `pipewire` (`pw-record`, `pw-dump`) |
| MilkDrop | `projectm` y `gcc` (el puente C++ se compila solo la primera vez) |

Desde el código (el lanzador busca la carpeta en `~/proyectos/zebamp`, o en
`ZEBAMP_HOME`):

```sh
git clone https://github.com/1985a/zebamp.git ~/proyectos/zebamp
cd ~/proyectos/zebamp
install -Dm755 packaging/zebamp.sh ~/.local/bin/zebamp
install -Dm644 packaging/zebamp.desktop ~/.local/share/applications/zebamp.desktop
install -Dm644 packaging/zebamp.png ~/.local/share/icons/hicolor/256x256/apps/zebamp.png
install -Dm644 packaging/zebamp-mime.xml ~/.local/share/mime/packages/zebamp-skins.xml
update-mime-database ~/.local/share/mime
```

O como paquete de Python: `pip install zebamp-1.0.0rc1-py3-none-any.whl`
(crea la orden `zebamp`).

En sway conviene: `for_window [app_id="zebamp"] floating enable, border none`
y, para buscar desde cualquier sitio,
`bindsym $mod+Shift+s exec zebamp --buscar`.

Si usas **mako** para las notificaciones y salen recortadas, dale a Zebamp
su propio tamaño en `~/.config/mako/config` (y `makoctl reload`):

```ini
[app-name=Zebamp]
width=560
height=170
max-icon-size=128
```

## Uso

```sh
zebamp                      # abre con el último skin
zebamp --skin mi.wsz        # forzar un skin
zebamp archivo.flac URL...  # reproducir archivos/URLs (reemplaza la cola)
zebamp --host /run/user/1000/mpd/socket   # o host / --port
zebamp --buscar             # en la instancia abierta: buscar canciones
zebamp --siguiente | --anterior | --play-pausa | --detener | --saltar | --milkdrop
zebamp --letras | --radio | --ayuda
```

Si Zebamp ya está abierto, volver a lanzarlo le envía la orden (o los
archivos) en vez de abrir otra copia. Sirve para teclas globales del gestor
de ventanas, p. ej. en sway:
`bindsym $mod+Shift+f exec zebamp --buscar`.

Conexión a MPD automática, en este orden: `MPD_HOST`/`MPD_PORT`, socket de
systemd (`$XDG_RUNTIME_DIR/mpd/socket`), el `bind_to_address` de `mpd.conf`,
`~/.mpd/socket`, `localhost:6600`. Se comprueba que cada socket responda.

## Qué incluye

Las ventanas del skin clásico (principal, ecualizador y lista) también se
**mueven por separado y se pegan con imán**, como en Winamp; arrastrar la
principal se lleva las que tiene pegadas.

**Ventana principal**: transporte, posición, volumen, balance, aleatorio,
repetir (no / lista / pista), tiempo transcurrido/restante (clic), título
desplazable (arrastrable), kbps/kHz, mono/estéreo, barra «OAIDV», modo compacto
(windowshade), tamaño 1x/2x/3x.

**Visualizador**: analizador de espectro (barras gruesas/finas, estilos normal,
fuego y línea, picos, caídas configurables) y osciloscopio (puntos, líneas,
sólido), a 20–70 fps reales. Lee la salida `fifo` de MPD (se detecta en
`mpd.conf`; se prefiere una salida cuyo nombre contenga «zebamp»). Si ese fifo
lo está leyendo otro programa (ncmpcpp, cava…), Zebamp no se lo quita: captura
el audio del stream de MPD en PipeWire (`pw-record`). Usa la paleta
`viscolor.txt` del skin.

**MilkDrop** (Ctrl+Shift+K, o el botón de visualización de los skins
modernos): visualizaciones MilkDrop con **projectM** (paquete `projectm`, sus
~4200 presets). Espacio/N siguiente, H corte brusco, Retroceso anterior,
L elegir preset (con búsqueda), K bloquear, R aleatorio, Enter/doble clic
pantalla completa, clic derecho para calidad, fps y duración. Un pequeño
puente C++ (`zebamp/native/pmshim.cpp`) se compila solo la primera vez
(necesita `g++`).

**Integración con el escritorio**: MPRIS (teclas multimedia, `playerctl`,
waybar…), icono en la bandeja (clic: mostrar/ocultar, botón central:
reproducir/pausa, menú) y «Cerrar a la bandeja» opcional. Doble clic en un
`.wsz`/`.wal` lo instala y aplica; `.m3u`/`.pls` y canciones se abren con
Zebamp («Abrir con»).

**Valoraciones y estadísticas**: estrellas (Ctrl+Alt+0…5, menú, biblioteca,
estrellas de Bento) y veces escuchada / última vez, guardadas en los stickers
de MPD (escala 0–10 compatible con Cantata). La biblioteca añade «Más
escuchadas», «Mejor valoradas», «Escuchadas recientemente» y «Añadidas
recientemente».

**Radio por Internet** (Alt+R): directorio radio-browser.info por nombre,
género, país o idioma, lo más escuchado/votado y favoritas.

**Letras** (Ctrl+Shift+L): con un skin clásico, en una ventana con el aspecto
del skin que se pega con imán. Busca primero un `.lrc` junto a la canción,
luego la letra de las etiquetas y por último lrclib.net (la versión de
duración más parecida). Las letras sincronizadas siguen la canción; si son de
otra versión (acelerada, con otra intro) se ajusta la velocidad sola, y
Mayús+clic en una línea al oírla la sincroniza a mano (se guarda por canción).

**Marcadores** (Ctrl+Alt+B): guarda canción y punto exacto; menú Marcadores.

**Información del archivo editable** (Alt+3): título, artista, álbum, año,
género, pista, disco, compositor y carátula incrustada (MP3, FLAC, Ogg, Opus,
M4A), con confirmación antes de escribir; MPD relee el archivo al guardar.

**Audio de MPD** (Preferencias → Audio): fundido, MixRamp y ReplayGain.

**Notificaciones**: al cambiar de canción, notificación con la carátula
(incrustada, `cover.*` de MPD o la imagen de la carpeta del disco).
Opciones → «Notificar cambio de canción».

**Búsqueda** (Ctrl+F, F3 o /): instantánea sobre toda la biblioteca (probada
con 107 000 canciones: 0,1–30 ms por tecla). Zebamp guarda un índice en
memoria (se carga en segundo plano al arrancar, ~1 s, y queda en caché en
`~/.cache/zebamp`; se renueva cuando cambia la base de datos de MPD). Todas las
palabras, sin importar tildes, en etiquetas y nombre de archivo. Enter
reproduce, Ctrl+Enter a continuación, Insert/Shift+Enter añade a la lista.

**Ecualizador**: 10 bandas + preamp, curva, preajustes de Winamp, preajustes
propios, importar/exportar `.eqf`, «Auto» por género. El audio se ecualiza con
un filtro de PipeWire («Zebamp EQ») que se intercala entre MPD y la salida que
ya usaba; al apagarlo, MPD vuelve a su salida original. Al cerrar Zebamp el
filtro sigue activo, para que la música no se corte ni cambie de sonido.
El **balance** se aplica como volumen por canal al stream de MPD en PipeWire.

**Lista de reproducción** (la cola de MPD): redimensionable, selección múltiple
(Ctrl/Shift), arrastrar para reordenar, arrastrar archivos desde el gestor,
menús Añadir/Quitar/Seleccionar/Varios/Lista, ordenar, invertir, mezclar,
quitar duplicados y entradas muertas, guardar/cargar listas de MPD, importar
`.m3u/.pls`, mini-transporte y tiempo total, modo compacto.

**Biblioteca de medios** (Alt+L): artistas, artistas del álbum, álbumes,
géneros, carpetas y listas guardadas de MPD, búsqueda, reproducir/encolar,
arrastrar a la lista. Usa el marco `gen.bmp` y los colores `genex.bmp` del skin.

**Otros**: información del archivo con carátula (de MPD), saltar a archivo (J),
saltar a tiempo (Ctrl+J), explorador de skins con vista previa (Alt+S),
preferencias, salidas de audio de MPD, actualizar base de datos, fundido.

## Skins

Carpeta: `~/.local/share/zebamp/skins` (Alt+S → «Añadir skin…» los copia ahí).

* **Clásicos (.wsz/.zip/carpeta)**: todos los bitmaps estándar, `region.txt`
  (forma de la ventana), `viscolor.txt`, `pledit.txt`, `genex.bmp`, cursores
  `.cur`/`.ani`, `nums_ex.bmp`. Lo que falte se toma del skin interno.
* **Modernos (.wal)**: XML de Wasabi (contenedores, layouts, grupos, capas,
  botones, toggles, textos, sliders, vis, eqvis, estado, capas animadas,
  fuentes TTF y bitmap) y una máquina virtual **MAKI** que ejecuta los scripts
  compilados del skin.

El skin interno **«Zebamp»** es un diseño original (estilo Winamp 5) dibujado
en vectorial a la resolución de la pantalla: a 2x o 3x se ve nítido, sin
píxeles agrandados. Los skins de mapa de bits (.wsz) se amplían con
Scale2x/Scale3x supermuestreado (bordes curvos y diagonales suavizados, zonas
planas nítidas); se puede desactivar en
Opciones → Tamaño. No se incluye arte de Nullsoft.

Las ventanas de los skins modernos se **mueven libremente y se pegan con
imán** entre sí y a los bordes de la pantalla, como en Winamp: al arrastrar el
reproductor se lleva lo que tiene pegado; cualquier otra ventana se despega y
va sola. Las posiciones se guardan por skin. (En Wayland esto se hace con un
lienzo transparente del tamaño del escritorio que solo recibe clics sobre las
ventanas del skin.) Opciones → Tamaño permite también «todas pegadas en un
bloque» y «Reordenar ventanas del skin»; Opciones → «Tema de color del skin»
aplica los temas de Winamp 5 (Winamp Modern trae 44). La biblioteca de medios
aparece dentro de Bento/Big Bento y en la ventana «Media Library»; sus títulos
«WINAMP» aparecen como «ZEBAMP». Su tamaño va aparte
(1x–2x en pasos de 0,25, con suavizado): Opciones → Tamaño.

### Limitaciones conocidas

* Skins modernos: compatibilidad **parcial**. Los que dependen de componentes
  internos de Winamp (biblioteca embebida, vídeo, AVS, navegador) o de la
  librería «Freeform» de Winamp muestran esas partes vacías o simplificadas.
  Métodos MAKI no implementados devuelven valores neutros en vez de fallar.
* Wayland no permite que una aplicación coloque sus ventanas: Zebamp usa un
  lienzo transparente del tamaño del monitor (ver docs/ARQUITECTURA.md).
  Probado en sway; en otros compositores la colocación puede diferir.
  «Siempre visible» no tiene efecto en Wayland.

## Atajos (como Winamp)

| Tecla | Acción | Tecla | Acción |
|---|---|---|---|
| Z / X / C / V / B | anterior / play / pausa / stop / siguiente | Espacio | play/pausa |
| ← / → | −5 s / +5 s | ↑ / ↓ | volumen |
| L / Shift+L / Ctrl+L | abrir archivos / carpeta / URL | Insert | añadir archivos |
| J / Ctrl+J | saltar a archivo / a tiempo | R / S | repetir / aleatorio |
| Alt+E / Alt+G / Alt+L | lista / EQ / biblioteca | Alt+S | skins |
| Alt+3 | info del archivo | Ctrl+P | preferencias |
| Ctrl+F / F3 / / | buscar canciones | Ctrl+Shift+K | MilkDrop |
| Ctrl+D | tamaño doble | Ctrl+W | modo compacto |
| Ctrl+T | tiempo restante | Ctrl+Q | salir |
| Ctrl+Shift+L | letras | F1 | ayuda |

En la lista: flechas/RePág/AvPág/Inicio/Fin (Shift amplía), Enter reproduce,
Supr quita, Shift+Supr recorta, Ctrl+Supr vacía, Ctrl+A / Ctrl+I seleccionan,
Alt+↑/↓ mueven la selección.

## Pruebas

```sh
python -m unittest discover -s tests
```

Las pruebas arrancan un MPD privado (salida nula) en un directorio temporal:
nunca tocan tu MPD. Incluyen clics y teclas reales sobre la interfaz.

## Licencia

Zebamp es software libre bajo la **GNU General Public License v3.0 o
posterior** ([LICENSE](LICENSE)). Los datos derivados de Webamp mantienen su
licencia MIT ([THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)).

## Créditos

Las coordenadas del formato de skin clásico y la descripción del formato
binario MAKI se contrastaron con el proyecto [Webamp](https://github.com/captbaritone/webamp)
(MIT). `zebamp/data/eq_presets.json` y `zebamp/data/maki/objects.json` derivan de él;
su licencia está en [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
Winamp es una marca de sus propietarios; Zebamp no está afiliado.

Cambios de cada versión: [CHANGELOG.md](CHANGELOG.md). La ayuda completa está
dentro del programa (F1).

## Para desarrolladores

La organización del código, los hilos y las reglas de la casa (rendimiento,
legibilidad) están en [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md). Antes de
enviar un cambio:

```sh
uvx ruff check .
python -m unittest discover -s tests
```
