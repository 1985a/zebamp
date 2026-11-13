"""Built-in user guide (F1 / Menú › Ayuda)."""
from __future__ import annotations

import html
import re

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QKeySequence, QPalette, QShortcut
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QSplitter,
                               QTextBrowser, QVBoxLayout, QWidget)

from .. import __version__, i18n
from ..i18n import tr


def _keys(rows, either="o"):
    """Table of shortcuts; `either` is the word between alternative keys."""
    out = ["<table class='k'>"]
    for k, v in rows:
        if k.startswith(("zebamp", "--")):
            keys = " ".join(f"<code>{html.escape(x)}</code>" for x in k.split(" "))
        else:
            keys = f" <span class='o'>{either}</span> ".join(f"<kbd>{html.escape(x)}</kbd>" for x in k.split(" "))
        out.append(f"<tr><td class='kc'>{keys}</td><td>{v}</td></tr>")
    out.append("</table>")
    return "".join(out)


# (key, title, html).  Links between sections: <a href="#key">.
SECTIONS: list[tuple[str, str, str]] = [
    ("inicio", "Bienvenida", f"""
<h1>Zebamp {__version__}</h1>
<p>Zebamp es un reproductor con el aspecto y el manejo de <b>Winamp</b> que controla
<b>MPD</b> (Music Player Daemon). La música la reproduce MPD; Zebamp es el «mando a
distancia»: por eso, al cerrar Zebamp la música sigue sonando, y lo que hagas en otros
clientes (ncmpcpp, el móvil…) se ve aquí al instante.</p>
<p>Usa el índice de la izquierda o el buscador de arriba. Pulsa <kbd>F1</kbd> en cualquier
ventana de Zebamp para abrir la ayuda de esa ventana.</p>
<h3>Lo más usado</h3>
<ul>
<li><a href="#primeros">Primeros pasos</a>: conectar con MPD y poner música.</li>
<li><a href="#buscar">Búsqueda instantánea</a>: <kbd>Ctrl+F</kbd> dentro de Zebamp,
<kbd>Super+Shift+S</kbd> desde cualquier parte del escritorio.</li>
<li><a href="#atajos">Todos los atajos de teclado</a>.</li>
<li><a href="#skins">Cambiar de skin</a>: <kbd>Alt+S</kbd>.</li>
<li><a href="#problemas">Solución de problemas</a>.</li>
</ul>
"""),

    ("primeros", "Primeros pasos", """
<h2>Primeros pasos</h2>
<h3>1. Conectar con MPD</h3>
<p>Zebamp se conecta solo al MPD local (variables <code>MPD_HOST</code>/<code>MPD_PORT</code>,
o <code>localhost:6600</code>). Para otro servidor: <b>Menú › Opciones › Preferencias…</b>
(<kbd>Ctrl+P</kbd>), pestaña <b>MPD</b>: servidor o ruta del socket, puerto y contraseña.
Si MPD se cae o se reinicia, Zebamp se reconecta solo.</p>
<h3>2. Poner música</h3>
<ul>
<li><kbd>L</kbd> reproducir archivos, <kbd>Shift+L</kbd> una carpeta, <kbd>Ctrl+L</kbd> una URL.</li>
<li>Arrastra archivos o carpetas sobre cualquier ventana de Zebamp.</li>
<li><kbd>Ctrl+F</kbd> busca en toda tu biblioteca al instante (<a href="#buscar">más</a>).</li>
<li><kbd>Alt+L</kbd> abre la <a href="#biblioteca">biblioteca de medios</a> para explorar por
artista, álbum, género o carpeta.</li>
<li><kbd>Alt+R</kbd> abre la <a href="#radio">radio por Internet</a>.</li>
</ul>
<p>Los archivos deben estar dentro de la carpeta de música de MPD (o MPD debe poder leerlos
por socket local).</p>
<h3>3. Controlar</h3>
<p>Botones de la ventana principal, o las teclas de Winamp: <kbd>Z</kbd> anterior,
<kbd>X</kbd> reproducir, <kbd>C</kbd> pausa, <kbd>V</kbd> detener, <kbd>B</kbd> siguiente,
<kbd>Espacio</kbd> reproducir/pausa. Las teclas multimedia del teclado también funcionan
(<a href="#escritorio">más</a>).</p>
<h3>El menú principal</h3>
<p>Casi todo está en el <b>menú principal</b>: botón de la esquina superior izquierda de la
ventana principal, o clic derecho sobre ella. En los skins modernos, en el menú del skin o con
clic derecho.</p>
"""),

    ("principal", "Ventana principal", """
<h2>Ventana principal</h2>
<ul>
<li><b>Barra de título</b>: arrástrala para mover; doble clic = modo compacto
(<kbd>Ctrl+W</kbd>). Botones: menú, minimizar, compactar y cerrar.</li>
<li><b>Tiempo</b>: clic para alternar transcurrido / restante (<kbd>Ctrl+T</kbd>). Las
canciones de más de 99 minutos muestran horas.</li>
<li><b>Visualización</b>: clic para cambiar de modo (espectro, osciloscopio, nada); clic
derecho para su menú (<a href="#vis">más</a>).</li>
<li><b>Título</b>: se desplaza solo; puedes arrastrarlo con el ratón para leerlo. Doble clic
abre la <a href="#info">información del archivo</a>.</li>
<li><b>kbps / kHz / mono / estéreo</b>: datos del audio. Con audio de alta resolución
(1411 kbps, 192 kHz…) el recuadro se estira para mostrar todas las cifras. Pasa el ratón por
encima para ver el formato completo (códec, bits, canales). Con música de consolas
(.spc, .nsf, .vgm…) o MIDI se muestra el bitrate del audio generado.</li>
<li><b>Volumen y balance</b>: deslizadores. La rueda del ratón sobre la ventana también
cambia el volumen.</li>
<li><b>Barra de posición</b>: arrástrala para ir a cualquier punto.</li>
<li><b>EQ / PL</b>: muestran u ocultan el <a href="#ecualizador">ecualizador</a> y la
<a href="#lista">lista</a>.</li>
<li><b>Aleatorio / Repetir</b>: <kbd>S</kbd> y <kbd>R</kbd>. Repetir alterna entre no, toda la
lista y pista actual.</li>
</ul>
<h3>Barra lateral O · A · I · D · V</h3>
<table class='k'>
<tr><td class='kc'><b>O</b></td><td>Menú de opciones.</td></tr>
<tr><td class='kc'><b>A</b></td><td>Siempre visible (encima de las demás ventanas).</td></tr>
<tr><td class='kc'><b>I</b></td><td>Información del archivo.</td></tr>
<tr><td class='kc'><b>D</b></td><td>Tamaño doble (<kbd>Ctrl+D</kbd>).</td></tr>
<tr><td class='kc'><b>V</b></td><td>Menú de visualización.</td></tr>
</table>
"""),

    ("lista", "Lista de reproducción", """
<h2>Lista de reproducción</h2>
<p>Es la cola de MPD: si otro cliente la cambia, se actualiza aquí. Mostrar/ocultar:
<kbd>Alt+E</kbd> o el botón <b>PL</b>.</p>
<ul>
<li>Doble clic o <kbd>Enter</kbd>: reproducir la canción.</li>
<li>Clic, <kbd>Shift</kbd>+clic y <kbd>Ctrl</kbd>+clic para seleccionar; arrastra para
reordenar; arrastra archivos desde fuera para añadirlos.</li>
<li><kbd>Alt+↑</kbd> / <kbd>Alt+↓</kbd> mueven la selección.</li>
<li><kbd>Supr</kbd> quita lo seleccionado, <kbd>Shift+Supr</kbd> recorta (deja solo lo
seleccionado), <kbd>Ctrl+Supr</kbd> vacía la lista.</li>
<li><kbd>Ctrl+A</kbd> seleccionar todo, <kbd>Ctrl+I</kbd> invertir selección.</li>
<li><kbd>J</kbd> saltar a una canción de la lista escribiendo parte del nombre.</li>
<li>Arrastra la esquina inferior derecha para cambiar el tamaño.</li>
</ul>
<h3>Botones de abajo</h3>
<table class='k'>
<tr><td class='kc'><b>ADD</b></td><td>Añadir URL, carpeta o archivos.</td></tr>
<tr><td class='kc'><b>REM</b></td><td>Quitar seleccionados, recortar, vaciar y otras
opciones (duplicados, entradas que ya no existen).</td></tr>
<tr><td class='kc'><b>SEL</b></td><td>Seleccionar todo, nada o invertir.</td></tr>
<tr><td class='kc'><b>MISC</b></td><td>Ordenar (título, archivo, ruta, artista/álbum/pista,
invertir, mezclar), información del archivo y opciones (números de pista, seguir la
canción actual).</td></tr>
<tr><td class='kc'><b>LIST</b></td><td>Nueva lista, guardar y cargar listas (se guardan en
MPD como listas almacenadas).</td></tr>
</table>
<p>Clic derecho sobre las canciones: reproducir, información, quitar, enviar a una lista
guardada, valorar…</p>
"""),

    ("ecualizador", "Ecualizador", """
<h2>Ecualizador</h2>
<p>Mostrar/ocultar: <kbd>Alt+G</kbd> o el botón <b>EQ</b>. Diez bandas de 60 Hz a 16 kHz
más el preamplificador.</p>
<ul>
<li><b>ON</b>: activa o desactiva el ecualizador.</li>
<li><b>AUTO</b>: carga automáticamente el preajuste guardado para cada canción.</li>
<li><b>PRESETS</b>: cargar preajustes (incluidos los clásicos de Winamp y archivos
<code>.eqf</code>), guardar los tuyos o exportarlos a <code>.eqf</code>; «Restablecer» deja
todo plano.</li>
</ul>
<p><b>Cómo funciona:</b> el ecualizador es un filtro de PipeWire («Zebamp EQ») colocado entre
MPD y tu salida de audio. Sigue activo aunque cierres Zebamp, para que la música no se corte
ni cambie de sonido. Se configura en <b>Preferencias › Ecualizador</b>; ahí también puedes
hacer que el balance se aplique al audio de MPD.</p>
"""),

    ("biblioteca", "Biblioteca de medios", """
<h2>Biblioteca de medios</h2>
<p><kbd>Alt+L</kbd>. Explora la base de datos de MPD.</p>
<ul>
<li>A la izquierda: <b>Artistas, Artistas del álbum, Álbumes, Géneros, Carpetas</b> y
<b>Listas guardadas</b>.</li>
<li>Vistas inteligentes: <b>Más escuchadas, Mejor valoradas, Escuchadas recientemente</b> y
<b>Añadidas recientemente</b> (ver <a href="#valoraciones">valoraciones</a>).</li>
<li><b>Listas inteligentes</b>: tus propias listas por reglas (ver más abajo).</li>
<li>La casilla de búsqueda filtra por artista, título, álbum…</li>
<li>Doble clic reproduce; clic derecho para añadir, poner a continuación, reemplazar la
lista o editar etiquetas. También puedes arrastrar canciones a la lista.</li>
<li><b>Menú › MPD › Actualizar base de datos</b> cuando añadas música nueva al disco.</li>
</ul>
<p>Los skins modernos Bento y Big Bento llevan la biblioteca integrada en su propia
ventana.</p>
<h3>Listas inteligentes</h3>
<p>Una lista inteligente no se llena a mano: eliges unas reglas y Zebamp reúne las canciones
que las cumplen, siempre al día. Por ejemplo: <i>género contiene «rock», valoración al menos
4 y días sin escucharla al menos 30</i>.</p>
<ul>
<li>Abre <b>Listas inteligentes</b> en el árbol y haz doble clic en <b>＋ Nueva lista
inteligente…</b> (o clic derecho).</li>
<li>Reglas sobre: título, artista, álbum, artista del álbum, género, carpeta o archivo,
valoración, veces escuchada, año, duración y días sin escucharla. Una canción que nunca has
escuchado cuenta como «muchos días sin escucharla».</li>
<li>Elige si deben cumplirse <b>todas</b> las reglas o <b>alguna</b>, el orden (por artista,
al azar, más escuchadas, mejor valoradas…) y un máximo de canciones.</li>
<li>Clic derecho sobre una lista para <b>editarla</b> o <b>borrarla</b>; doble clic la
reproduce.</li>
</ul>
"""),

    ("buscar", "Búsqueda instantánea", """
<h2>Búsqueda instantánea</h2>
<p>Busca en <b>toda</b> la biblioteca mientras escribes, aunque tenga cientos de miles de
canciones (el índice está en memoria; la primera vez tarda unos segundos en cargarse).</p>
<h3>Cómo abrirla</h3>
<ul>
<li>Dentro de Zebamp: <kbd>Ctrl+F</kbd>, <kbd>F3</kbd> o <kbd>/</kbd>.</li>
<li><b>Desde cualquier parte del escritorio</b>: <kbd>Super+Shift+S</kbd>. Funciona aunque
Zebamp esté minimizado, en otro escritorio o en la bandeja; si no está abierto, lo abre.</li>
<li>Desde un terminal o un atajo propio: <code>zebamp --buscar</code>.</li>
</ul>
<h3>Uso</h3>
<ul>
<li>Escribe varias palabras: deben aparecer todas (en título, artista, álbum o nombre de
archivo); no importan mayúsculas ni tildes.</li>
<li><kbd>↑</kbd>/<kbd>↓</kbd> para elegir.</li>
<li><kbd>Enter</kbd>: reproducir ahora.</li>
<li><kbd>Ctrl+Enter</kbd>: reproducir a continuación.</li>
<li><kbd>Insert</kbd> o <kbd>Shift+Enter</kbd>: añadir al final de la lista.</li>
<li><kbd>Esc</kbd>: cerrar.</li>
</ul>
<p>Para buscar solo dentro de la lista actual usa <kbd>J</kbd>
(<a href="#lista">saltar a archivo</a>).</p>
"""),

    ("skins", "Skins", """
<h2>Skins</h2>
<p>Zebamp usa skins de Winamp tal cual, sin convertirlos:</p>
<ul>
<li><b>Clásicos</b> (<code>.wsz</code>): los de Winamp 2. El skin <b>Zebamp</b>
predeterminado está dibujado en vectores y se ve nítido a cualquier tamaño.</li>
<li><b>Modernos</b> (<code>.wal</code>): los de Winamp 3/5, como <b>Winamp Modern</b>,
<b>Bento</b> y <b>Big Bento</b>, con sus scripts.</li>
</ul>
<h3>Cambiar de skin</h3>
<ul>
<li><kbd>Alt+S</kbd>: explorador de skins con vista previa.</li>
<li><b>Menú › Skins</b>: lista rápida, cargar desde archivo, abrir la carpeta de skins y
el <i>Winamp Skin Museum</i> para descargar miles más.</li>
<li>Doble clic en un <code>.wsz</code> o <code>.wal</code> desde el gestor de archivos lo
instala y lo aplica.</li>
</ul>
<h3>Tamaño y aspecto</h3>
<ul>
<li><b>Menú › Opciones › Tamaño</b>: 1x, 2x, 3x en los clásicos (<kbd>Ctrl+D</kbd> = doble);
de 1x a 2x en los modernos.</li>
<li>«Suavizar skins de mapa de bits (Scale2x/3x)»: agranda los skins clásicos sin que se vean
pixelados.</li>
<li>Algunos skins modernos traen <b>temas de color</b> (Menú › Opciones › Tema de color del
skin).</li>
</ul>
<h3>Ventanas sueltas con imán</h3>
<p>Como en Winamp, la ventana principal, el ecualizador y la lista se mueven por separado y
se pegan entre sí y a los bordes de la pantalla al acercarlas. Si mueves la ventana
principal, se lleva consigo las que estén pegadas; para despegar una, arrástrala a ella
sola. Zebamp recuerda dónde las dejaste y las abre así la próxima vez, ya unidas.</p>
<h3>Varios monitores</h3>
<ul>
<li>Las ventanas se quedan en el monitor donde tú las pongas: un clic sobre ellas o un
movimiento pequeño nunca las cambia de pantalla.</li>
<li>Para pasarlas al otro monitor, <b>arrástralas hasta el borde que da a ese monitor</b> y
sigue arrastrando: en ese momento se abre el paso y cruzan. Al soltar, quedan en el monitor
donde las dejaste.</li>
<li>Zebamp pertenece a un solo escritorio (el del monitor donde está); no aparece en los demás
escritorios. Para buscar una canción desde cualquier otro sitio usa <kbd>Super+Shift+S</kbd>
(<a href="#buscar">búsqueda instantánea</a>).</li>
<li>Si sueltas una ventana en una zona que no existe (por ejemplo, debajo de un monitor más
pequeño), el grupo entero vuelve a la pantalla sin despegarse.</li>
</ul>
<p>En los skins modernos puedes elegir «Todas pegadas en un bloque» y, si se desordenan,
«Reordenar ventanas del skin» (Menú › Opciones › Tamaño).</p>
"""),

    ("vis", "Visualización y MilkDrop", """
<h2>Visualización</h2>
<p>El visualizador de la ventana principal muestra el espectro o el osciloscopio. Clic para
cambiar de modo; clic derecho (o la <b>V</b> de la barra lateral) para su menú: barras gruesas
o finas, picos, velocidad, fotogramas por segundo…</p>
<p>Zebamp toma el audio de la salida <i>fifo</i> de MPD, o lo captura de PipeWire si otro
programa (por ejemplo, el visualizador de ncmpcpp) ya está leyendo ese fifo; así ambos
funcionan a la vez. Se configura en <b>Preferencias › Visualización</b>.</p>
<h2>MilkDrop</h2>
<p><kbd>Ctrl+Shift+K</kbd> (o <kbd>Ctrl+K</kbd>, o Menú › Visualización › MilkDrop) abre los
efectos psicodélicos de MilkDrop (motor projectM) en su propia ventana.</p>
<p>Con un skin moderno que tenga pestaña de visualización (Bento, Big Bento), <b>Menú ›
Visualización › Pestaña de visualización del skin</b> elige qué se ve en ella: el analizador
de espectro o MilkDrop. Doble clic sobre MilkDrop en la pestaña lo abre en su ventana.</p>
""" + _keys([
        ("Espacio N", "siguiente preset, con transición suave"),
        ("H", "corte brusco a otro preset"),
        ("Retroceso P", "preset anterior"),
        ("L", "elegir preset de una lista con búsqueda"),
        ("K BloqDespl", "bloquear el preset actual"),
        ("R", "orden aleatorio sí/no"),
        ("T", "mostrar el título de la canción"),
        ("C", "configuración de MilkDrop"),
        ("Enter F F11", "pantalla completa (o doble clic)"),
        ("Esc", "salir de pantalla completa / cerrar"),
    ]) + """
<p><b>Configurar MilkDrop…</b> (Menú › Visualización): carpeta de presets, cada cuánto
cambiar, duración de la transición, cortes bruscos con los golpes de la música, calidad,
malla, textura, fotogramas por segundo y sensibilidad al ritmo. Con «Siguiente preset al azar»
el siguiente preset se elige aleatoriamente.</p>
"""),

    ("radio", "Radio por Internet", """
<h2>Radio por Internet</h2>
<p><kbd>Alt+R</kbd>. Busca entre las emisoras del directorio público <i>radio-browser</i>
por nombre, país, idioma o género. Doble clic o <kbd>Enter</kbd> reproduce la emisora en
MPD. Marca tus favoritas para tenerlas siempre a mano. El título de lo que suena se muestra
como en cualquier canción.</p>
"""),

    ("letras", "Letras", """
<h2>Letras</h2>
<p><kbd>Ctrl+Shift+L</kbd> (o Menú › Letras). Zebamp busca la letra en este orden:</p>
<ol>
<li>Un archivo <code>.lrc</code> junto a la canción, con el mismo nombre
(<code>canción.flac</code> → <code>canción.lrc</code>): tus propias letras mandan.</li>
<li>La letra guardada en las etiquetas del archivo (LYRICS, SYNCEDLYRICS…).</li>
<li><i>LRCLIB</i> en Internet, eligiendo la versión cuya duración se parece más a tu
canción. Si la canción no tiene etiquetas, se busca por el nombre del archivo
(«Artista - Título»).</li>
</ol>
<p>Lo encontrado se guarda en caché. Si no hay letra, se dice «No se encontró la letra de esta
canción» y no se vuelve a preguntar a Internet durante tres días («Volver a buscar» lo fuerza).</p>
<h3>Letras desfasadas o aceleradas</h3>
<p>A veces la letra es de otra versión: una más rápida, o una con la intro más corta.</p>
<ul>
<li><b>Automático</b>: si la letra es de una versión claramente más larga o más corta, Zebamp
ajusta la velocidad y lo indica.</li>
<li><b>Mayús+clic en una línea en el momento en que la oyes</b>: la letra se coloca en su
sitio. Si lo haces con otra línea más adelante (al menos 20 segundos después), Zebamp calcula
también la velocidad. Es la forma más fiable.</li>
<li>Clic derecho: «Letra más tarde / antes» (medio segundo cada vez) o «Restablecer
sincronización».</li>
<li>La corrección se guarda para esa canción y se aplica la próxima vez.</li>
<li>Las letras <code>.lrc</code> con la etiqueta <code>[offset:]</code> se respetan.</li>
</ul>
<h3>Con un skin clásico</h3>
<p>Las letras aparecen en una <b>ventana con el aspecto del skin</b> (el marco de las ventanas
genéricas de Winamp y los colores y la fuente de la lista de reproducción). Funciona como el
ecualizador o la lista: se pega con imán a las demás ventanas, se mueve con el grupo y Zebamp
recuerda dónde estaba y si estaba abierta.</p>
<ul>
<li>Si la letra está <b>sincronizada</b>, la línea que se canta se resalta y la ventana se
desplaza sola; las líneas ya cantadas se atenúan.</li>
<li><b>Doble clic</b> en una línea: salta a ese momento de la canción.
<b>Mayús+clic</b>: «esta línea suena ahora» (sincroniza).</li>
<li><b>Rueda del ratón</b>: recorrer la letra; a los 5 segundos vuelve a seguir la canción.</li>
<li>Arrastra la <b>esquina inferior derecha</b> para cambiar el tamaño.</li>
<li><b>Clic derecho</b>: volver a buscar la letra, letra más grande o más pequeña, abrirla en
una ventana aparte o cerrar.</li>
</ul>
<h3>Con un skin moderno</h3>
<p>Se abre una ventana normal con la letra, con las mismas funciones: línea actual resaltada,
doble clic para saltar, Mayús+clic para sincronizar y clic derecho para ajustar.</p>
"""),

    ("info", "Información y etiquetas", """
<h2>Información del archivo y edición de etiquetas</h2>
<p><kbd>Alt+3</kbd>, la <b>I</b> de la barra lateral o doble clic en el título. Muestra las
etiquetas, el formato del audio, la carátula y la ruta.</p>
<p>Puedes <b>editar</b> título, artista, álbum, año, género, número de pista, etc. Antes de
escribir en el archivo, Zebamp te enseña los cambios y te pide <b>confirmación</b>. Después
avisa a MPD para que actualice su base de datos. Solo funciona con archivos locales que
puedas modificar.</p>
<h3>Calidad del audio</h3>
<p><kbd>Alt+Q</kbd> (o Menú › Reproducción › Calidad del audio…, o clic derecho sobre una
canción de la lista) abre el <b>espectrograma</b> de la canción: una imagen de su sonido, con
el tiempo de izquierda a derecha y los tonos de graves (abajo) a agudos (arriba); cuanto más
claro, más fuerte.</p>
<p>El formato de un archivo no garantiza su calidad: un FLAC creado a partir de un MP3 ocupa
como uno auténtico y suena como el MP3. La imagen lo delata, porque los formatos con pérdida
eliminan todo lo que hay por encima de cierta frecuencia y dejan un borde recto con todo
negro encima. Zebamp busca ese borde y te da un veredicto:</p>
<ul>
<li><b>Sin pérdida auténtico</b>: el sonido llega hasta arriba (unos 22 kHz en calidad de
CD).</li>
<li><b>Alta resolución auténtica</b>: archivos de 88,2 kHz o más con sonido por encima de lo
que cabe en un CD.</li>
<li><b>Sospechoso</b>: un formato sin pérdida que se corta en seco (probablemente viene de un
MP3), un archivo de alta resolución sin nada por encima de 22 kHz, o un MP3 de muchos kbps que
suena como uno de pocos.</li>
<li><b>Con pérdida</b>, con su nivel: el corte ronda los 16 kHz a 128 kbps, 19 kHz a 192 y
20 kHz a 256–320.</li>
</ul>
<p>Es una estimación: algunas grabaciones antiguas tienen pocos agudos de origen. Hace falta
el programa <code>ffmpeg</code> y que el archivo esté en este equipo. En las pistas de un
<code>.cue</code> se analiza solo el tramo de esa pista.</p>
<h3>Reconocer una canción por su sonido</h3>
<p>Para los archivos sin etiquetas ni nombre útil, Zebamp puede averiguar qué canción es
escuchándola: calcula una <i>huella de audio</i> del archivo y la consulta en la base de datos
pública <b>AcoustID</b>, que responde con el artista, el título y el álbum.</p>
<ul>
<li>Se activa poniendo tu clave en <b>Preferencias › Internet</b>. La clave es gratuita: se
crea en acoustid.org/new-application. Hace falta también el programa <code>fpcalc</code>
(paquete <code>chromaprint</code>).</li>
<li>En la ventana de información, <b>Reconocer por el sonido…</b> propone artista, título y
álbum en las casillas; no se escribe nada en el archivo hasta que pulses «Guardar
cambios».</li>
<li>La búsqueda de carátulas lo usa sola cuando al archivo le faltan las etiquetas y no
encontró nada por su nombre.</li>
<li>Cada archivo se escucha una sola vez; el resultado se recuerda.</li>
</ul>
<p>Necesita Internet. Los programas del teléfono que reconocen música sin conexión llevan
dentro su propia base de datos de canciones; un reproductor no puede llevarla. Solo se
envía la huella de audio y la duración, nunca el archivo.</p>
"""),

    ("valoraciones", "Valoraciones y estadísticas", """
<h2>Valoraciones y estadísticas</h2>
<ul>
<li>Valora la canción actual de 0 a 5 estrellas con <kbd>Ctrl+Alt+0</kbd> …
<kbd>Ctrl+Alt+5</kbd>, desde Menú › Reproducción › Valorar, o desde el icono de la
bandeja.</li>
<li>Zebamp cuenta cuántas veces escuchas cada canción (cuenta cuando pasa la mitad, o 4
minutos) y cuándo fue la última vez.</li>
</ul>
<p>Todo se guarda en la base de <i>stickers</i> de MPD, así que lo conservas aunque
reinstales Zebamp, y otros clientes pueden leerlo. Si tu MPD no tiene stickers, se guarda en
un archivo local. Las vistas «Más escuchadas», «Mejor valoradas», etc. están en la
<a href="#biblioteca">biblioteca</a>, y puedes usarlas en tus
<a href="#biblioteca">listas inteligentes</a>.</p>
<h3>Scrobbling (ListenBrainz y Last.fm)</h3>
<p>Zebamp puede enviar lo que escuchas a tu perfil de <b>ListenBrainz</b> o de
<b>Last.fm</b>. Está apagado hasta que lo actives en <b>Preferencias › Scrobbling</b>.</p>
<ul>
<li><b>ListenBrainz</b>: copia tu token de usuario (listenbrainz.org/settings), pégalo y
pulsa <b>Comprobar</b>. También vale un servidor compatible propio.</li>
<li><b>Last.fm</b>: crea una clave de API gratuita (last.fm/api/account/create), escribe la
clave y el secreto y pulsa <b>Conectar…</b>; se abre el navegador para que autorices a
Zebamp, y al volver pulsas <b>Ya lo autoricé</b>.</li>
<li>Una canción se envía cuando suena más de la mitad (o 4 minutos). No se envían la radio
ni los archivos sin etiquetas de artista y título, ni las pistas de menos de 30 s.</li>
<li>Sin Internet no se pierde nada: se guardan y se envían cuando vuelve la conexión.</li>
</ul>
<p>El token y las claves se guardan en tu archivo de configuración, sin cifrar.</p>
"""),

    ("marcadores", "Marcadores", """
<h2>Marcadores</h2>
<p><kbd>Ctrl+Alt+B</kbd> guarda la canción actual <b>en el punto exacto</b> en que va
(útil en mezclas largas, audiolibros o podcasts). Menú › Marcadores para volver a ella o
«Editar marcadores…» para renombrarlos o borrarlos.</p>
"""),

    ("reproduccion", "Opciones de reproducción", """
<h2>Opciones de reproducción</h2>
<ul>
<li><b>Aleatorio</b> (<kbd>S</kbd>) y <b>Repetir</b> (<kbd>R</kbd>: no / toda la lista / pista
actual).</li>
<li><b>Consumir</b>: quita cada canción de la lista al terminar de sonar.</li>
<li><b>Parar tras la pista actual</b>.</li>
<li><b>Fundido entre pistas</b> (crossfade) de 2 a 10 s.</li>
<li><b>Temporizador de apagado</b> (Menú › Opciones): pausa la música dentro de 15, 30, 45,
60, 90 o 120 minutos, o de los que tú digas, o <b>al terminar el álbum</b> (deja acabar su
última canción). El mismo menú muestra cuánto queda y permite cancelarlo.</li>
<li><kbd>←</kbd>/<kbd>→</kbd> retroceden o avanzan 5 s; <kbd>Ctrl+J</kbd> salta a un tiempo
exacto.</li>
<li><kbd>↑</kbd>/<kbd>↓</kbd> suben o bajan el volumen.</li>
</ul>
<p>En <b>Preferencias › Audio (MPD)</b>: fundido, MixRamp y ReplayGain (igualar el volumen
entre canciones). Estas opciones se guardan en MPD y afectan a todos sus clientes.
<b>Menú › MPD › Salidas</b> activa o desactiva las salidas de audio de MPD.</p>
<h3>Varios servidores MPD</h3>
<p>Si tienes más de un MPD (el de este equipo, un servidor en casa…), guarda cada conexión
como un perfil: conéctate en <b>Preferencias › MPD</b> y elige <b>Menú › MPD › Servidor ›
Guardar la conexión actual como perfil…</b>. Después cambias de uno a otro desde ese mismo
menú; <b>Automático</b> vuelve al MPD de este equipo. Las valoraciones y el índice de
búsqueda son de cada servidor.</p>
"""),

    ("escritorio", "Integración con el escritorio", """
<h2>Integración con el escritorio</h2>
<ul>
<li><b>Teclas multimedia</b> (reproducir, siguiente, anterior, detener) y
<code>playerctl</code>: Zebamp se anuncia por MPRIS, así que también lo controlan las barras
como waybar y los widgets del escritorio, que muestran título y carátula.</li>
<li><b>Bandeja del sistema</b>: clic para mostrar/ocultar; clic derecho para controlar la
reproducción, valorar, buscar, radio y letras. Con <i>Cerrar a la bandeja</i> (Menú ›
Opciones), cerrar la ventana solo la oculta.</li>
<li><b>Notificaciones</b> con carátula al cambiar de canción (Menú › Opciones › Notificar
cambio de canción).</li>
<li><b>Siempre visible</b>: Menú › Opciones o la <b>A</b> de la barra lateral.</li>
<li><b>Asociaciones</b>: los skins <code>.wsz</code>/<code>.wal</code> se abren con Zebamp.</li>
<li><b>Búsqueda global</b>: <kbd>Super+Shift+S</kbd> (atajo de sway).</li>
<li><b>Arrastrar y soltar</b>: suelta archivos o carpetas sobre la ventana principal para
reproducirlos, o sobre la lista para añadirlos en ese punto. Un skin soltado se instala.</li>
<li><b>Carátula</b>: <kbd>Ctrl+Shift+A</kbd> abre la carátula del álbum en una ventana del
skin clásico, que se pega y se redimensiona como las demás.</li>
</ul>
<h3>Carátulas de Internet</h3>
<p>La carátula de tu música manda siempre: la imagen incrustada en el archivo, la que da MPD
(<code>cover.jpg</code>…) o cualquier imagen de la carpeta del álbum. Solo si no hay ninguna,
Zebamp la busca en Internet, y prefiere no mostrar nada antes que mostrar la de otro disco:</p>
<ol>
<li>Si el archivo lleva el identificador de MusicBrainz del álbum en sus etiquetas (los pone
MusicBrainz Picard), se usa ese: es exacto.</li>
<li>Si no, busca por <b>artista y álbum</b> en MusicBrainz (Cover Art Archive), Deezer e
iTunes, en ese orden. Solo acepta un resultado si el título y el artista coinciden de
verdad: «Grandes éxitos 2» no vale para «Grandes éxitos», ni el mismo título de otro
artista.</li>
<li>Las canciones sin etiqueta de álbum se buscan por <b>artista, título y duración</b>, para
no confundir la versión de estudio con una en directo.</li>
<li>Si al archivo le faltan las etiquetas, se usa lo que diga su <b>nombre</b>
(«Artista - Título.mp3»).</li>
<li>Si aun así no aparece, y lo has activado, Zebamp <b>reconoce la canción por su sonido</b>
(<a href="#info">más</a>) y usa la carátula exacta de su álbum.</li>
</ol>
<p>Lo encontrado se guarda (una vez por álbum) y si no aparece nada no se vuelve a preguntar
en una semana. Clic derecho sobre la ventana de carátula:</p>
<ul>
<li><b>No es esta carátula: buscar otra</b>: la descarta para siempre y prueba con la
siguiente coincidencia.</li>
<li><b>Dejar este álbum sin carátula</b>: no busca más para ese álbum.</li>
<li><b>Buscar la carátula en Internet</b>: busca ahora, aunque hace poco no se encontrara.</li>
<li><b>Buscar carátulas en Internet</b> (también en Menú › Opciones): activa o desactiva
toda la función. Al buscar se envían a esos servicios el artista y el álbum (o el título);
nada más.</li>
</ul>
<p>Las carátulas descargadas se usan también en las notificaciones y en los widgets del
escritorio. No se escriben en tus archivos de música.</p>
<h3>Compositores</h3>
<p>Las ventanas sueltas con imán necesitan que el compositor diga dónde están los monitores
y deje colocar la ventana de Zebamp. Está hecho y probado en <b>sway</b>. En <b>Hyprland</b>
se usa <code>hyprctl</code> (experimental: aún no se ha probado en un equipo real). En
los demás (KDE, GNOME…) Zebamp funciona con lo que le dice Qt, y la colocación puede variar;
con los skins modernos, <b>Opciones › Tamaño › Todas pegadas en un bloque</b> no depende del
compositor.</p>
<p>Cerrar Zebamp no detiene la música ni produce cortes: MPD sigue reproduciendo y el
ecualizador sigue activo.</p>
"""),

    ("terminal", "Línea de órdenes", """
<h2>Línea de órdenes</h2>
<p>Si Zebamp ya está abierto, estas órdenes se envían a la ventana abierta (útil para atajos
del gestor de ventanas):</p>
""" + _keys([
        ("zebamp", "abrir Zebamp"),
        ("zebamp archivo.flac carpeta/ URL", "reproducir archivos, carpetas o emisoras"),
        ("--buscar", "abrir la búsqueda de canciones"),
        ("--saltar", "abrir «saltar a archivo»"),
        ("--reproducir --pausa --play-pausa --detener", "controlar la reproducción"),
        ("--siguiente --anterior", "cambiar de canción"),
        ("--letras --radio --milkdrop", "abrir esas ventanas"),
        ("--ayuda", "abrir esta ayuda"),
        ("--host --port", "usar otro servidor MPD"),
        ("--skin archivo", "cargar un skin"),
        ("--lang en", "usar otro idioma (es, en) solo esta vez"),
        ("--debug", "mostrar mensajes de diagnóstico"),
    ]) + """
<p>Ejemplo de atajo en sway: <code>bindsym $mod+Shift+s exec zebamp --buscar</code></p>
"""),

    ("preferencias", "Preferencias", """
<h2>Preferencias</h2>
<p><kbd>Ctrl+P</kbd> o <kbd>Alt+K</kbd>.</p>
<ul>
<li><b>MPD</b>: servidor, puerto, contraseña y estado de la conexión.</li>
<li><b>Pantalla</b>: tamaño, usar la fuente del skin para el título (desactívala para ver
tildes y eñes con fuente del sistema), desplazamiento y velocidad del título, tamaño de letra
de la lista.</li>
<li><b>Visualización</b>: fifo de MPD y su formato.</li>
<li><b>Ecualizador</b>: motor del ecualizador y balance en PipeWire.</li>
<li><b>Audio (MPD)</b>: fundido, MixRamp y ReplayGain.</li>
<li><b>Scrobbling</b>: cuentas de ListenBrainz y Last.fm
(<a href="#valoraciones">más</a>).</li>
<li><b>Internet</b>: buscar carátulas y reconocer canciones por su sonido
(<a href="#info">más</a>).</li>
</ul>
<p><b>Idioma</b>: Menú › Opciones › Idioma (español o inglés); se aplica al reiniciar
Zebamp.</p>
<p>La configuración se guarda en <code>~/.config/zebamp/config.json</code>, junto con la
posición de las ventanas.</p>
"""),

    ("atajos", "Atajos de teclado", """
<h2>Atajos de teclado</h2>
<p>Funcionan con cualquier ventana de Zebamp activa (salvo el global).</p>
<h3>Reproducción</h3>
""" + _keys([
        ("Z", "anterior"), ("X", "reproducir"), ("C", "pausa"), ("V", "detener"),
        ("B", "siguiente"), ("Espacio", "reproducir / pausa"),
        ("←/→", "retroceder / avanzar 5 s"), ("↑/↓", "subir / bajar volumen"),
        ("Ctrl+J", "saltar a un tiempo"), ("S", "aleatorio"), ("R", "repetir"),
        ("Ctrl+Alt+0…5", "valorar la canción actual"),
        ("Ctrl+Alt+B", "añadir marcador"),
    ]) + "<h3>Abrir y buscar</h3>" + _keys([
        ("L", "reproducir archivos"), ("Shift+L", "reproducir carpeta"), ("Ctrl+L", "reproducir URL"),
        ("Insert", "añadir archivos a la lista"),
        ("Ctrl+F F3 /", "búsqueda instantánea en la biblioteca"),
        ("Super+Shift+S", "búsqueda desde cualquier parte del escritorio"),
        ("J", "saltar a una canción de la lista"),
    ]) + "<h3>Ventanas</h3>" + _keys([
        ("F1", "esta ayuda"),
        ("Alt+E", "lista de reproducción"), ("Alt+G", "ecualizador"),
        ("Alt+L", "biblioteca de medios"), ("Alt+R", "radio por Internet"),
        ("Ctrl+Shift+L", "letras"), ("Ctrl+Shift+A", "carátula"), ("Ctrl+K Ctrl+Shift+K", "MilkDrop"),
        ("Alt+3", "información del archivo"), ("Alt+Q", "calidad del audio (espectrograma)"),
        ("Alt+S", "explorador de skins"),
        ("Ctrl+P Alt+K", "preferencias"), ("Ctrl+W Alt+W", "modo compacto"),
        ("Ctrl+D", "tamaño doble"), ("Ctrl+T", "tiempo restante / transcurrido"),
        ("Ctrl+Q", "salir"),
    ]) + "<h3>Lista de reproducción</h3>" + _keys([
        ("Enter", "reproducir la seleccionada"), ("Supr", "quitar"),
        ("Shift+Supr", "recortar"), ("Ctrl+Supr", "vaciar"),
        ("Ctrl+A", "seleccionar todo"), ("Ctrl+I", "invertir selección"),
        ("Alt+↑ Alt+↓", "mover la selección"), ("Inicio Fin RePág AvPág", "moverse"),
    ]) + "<h3>Búsqueda</h3>" + _keys([
        ("Enter", "reproducir ahora"), ("Ctrl+Enter", "reproducir a continuación"),
        ("Insert Shift+Enter", "añadir al final"), ("Esc", "cerrar"),
    ]) + "<p>Los atajos de MilkDrop están en <a href='#vis'>su sección</a>.</p>"),

    ("problemas", "Solución de problemas", """
<h2>Solución de problemas</h2>
<h3>«Sin conexión con MPD»</h3>
<p>Comprueba que MPD está en marcha (<code>systemctl --user status mpd</code> o
<code>mpc status</code>) y los datos de <b>Preferencias › MPD</b>. Zebamp reintenta solo cada
pocos segundos.</p>
<h3>No se ven las carátulas</h3>
<p>Zebamp las pide a MPD (imagen incrustada o <code>cover.jpg</code> en la carpeta). MPD debe
poder leer los archivos; tras reiniciar MPD a mano con otro usuario puede no tener permisos o
la misma configuración. Si la música no trae carátula, se busca en Internet
(<a href="#escritorio">más</a>): hacen falta las etiquetas de artista y álbum (o título) bien
escritas.</p>
<h3>La visualización no se mueve</h3>
<p>MPD necesita una salida <i>fifo</i> (ver <b>Preferencias › Visualización</b>, que indica
si llegan datos). Si no hay fifo, Zebamp intenta capturar el audio de PipeWire.</p>
<h3>El ecualizador no hace nada</h3>
<p>Necesita PipeWire y que MPD suene a través de él. En <b>Preferencias › Ecualizador</b> se
indica si PipeWire está disponible.</p>
<h3>Las ventanas del skin están descolocadas o fuera de la pantalla</h3>
<p>Menú › Opciones › Tamaño › «Reordenar ventanas del skin» (modernos), o arrástralas; si
una queda fuera de la pantalla, Zebamp la devuelve al soltarla.</p>
<h3>Zebamp aparece en todos los escritorios de un monitor</h3>
<p>Ocurre si una ventana del skin quedó a caballo entre los dos monitores: el reproductor
tiene que cubrir ambos para mostrarla. Arrastra el grupo para que quede entero en un
monitor.</p>
<h3>El título sale sin tildes</h3>
<p>Es la fuente de mapa de bits del skin, que (como en Winamp) no tiene tildes. Desactiva
«Usar la fuente del skin para el título» en <b>Preferencias › Pantalla</b>.</p>
<h3>Más información</h3>
<p>Ejecuta <code>zebamp --debug</code> en un terminal para ver mensajes de diagnóstico.</p>
"""),

    ("acerca", "Acerca de Zebamp", f"""
<h2>Acerca de Zebamp</h2>
<p>Zebamp {__version__}: clon de Winamp para MPD, escrito en Python con Qt (PySide6).</p>
<p>Usa MPD para reproducir, PipeWire para el ecualizador y la captura de audio, projectM para
MilkDrop, LRCLIB para las letras y radio-browser para las emisoras. Los skins pertenecen a sus
autores.</p>
"""),
]

def sections() -> list[tuple[str, str, str]]:
    """The guide in the language in use (same keys and links in every language)."""
    if i18n.language() == "en":
        from .help_en import SECTIONS as english
        return english
    return SECTIONS


def _plain(h: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", h)).lower()


def _fold(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


class HelpWindow(QWidget):
    def __init__(self, app):
        super().__init__(None, Qt.WindowType.Window)
        self.app = app
        self.sections = sections()
        self.titles = {key: title for key, title, _body in self.sections}
        self.setWindowTitle(tr("Ayuda de Zebamp"))
        self.resize(940, 640)
        pal = getattr(app, "dialog_palette", None)
        if pal is not None:
            self.setPalette(pal)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Buscar en la ayuda (por ejemplo: ecualizador, atajo, letras)…"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        self.search.returnPressed.connect(self._find_next)
        top.addWidget(self.search, 1)
        for text, fn in (("◀", self._back), (tr("Inicio"), lambda: self.show_section("inicio"))):
            b = QPushButton(text)
            b.clicked.connect(fn)
            top.addWidget(b)
        lay.addLayout(top)
        split = QSplitter()
        self.toc = QListWidget()
        for key, title, _h in self.sections:
            it = QListWidgetItem(title)
            it.setData(Qt.ItemDataRole.UserRole, key)
            self.toc.addItem(it)
        self.toc.currentItemChanged.connect(self._toc_changed)
        split.addWidget(self.toc)
        self.view = QTextBrowser()
        self.view.setOpenLinks(False)
        self.view.anchorClicked.connect(self._link)
        split.addWidget(self.view)
        split.setStretchFactor(1, 4)
        split.setSizes([210, 730])
        lay.addWidget(split, 1)
        self.status = QLabel(tr("F1: ayuda de la ventana activa · Enter en la búsqueda: siguiente coincidencia"))
        lay.addWidget(self.status)
        self._history: list[str] = []
        self._current = None
        self._css = self._style()
        QShortcut(QKeySequence("Esc"), self, self.close)
        QShortcut(QKeySequence("Ctrl+F"), self, lambda: (self.search.setFocus(), self.search.selectAll()))
        QShortcut(QKeySequence("Alt+Left"), self, self._back)

    def _style(self) -> str:
        p = self.palette()
        text = p.color(QPalette.ColorRole.Text).name()
        hl = p.color(QPalette.ColorRole.Highlight)
        base = p.color(QPalette.ColorRole.Base)
        from ..colors import readable
        accent = readable(hl, base, p.color(QPalette.ColorRole.Text)).name()
        kbd_bg = base.lighter(160).name() if base.lightness() < 128 else base.darker(115).name()
        muted = p.color(QPalette.ColorRole.PlaceholderText).name()
        return f"""
        body {{ color: {text}; }}
        h1, h2 {{ color: {accent}; }}
        h3 {{ color: {accent}; margin-top: 14px; }}
        a {{ color: {accent}; }}
        kbd {{ background: {kbd_bg}; font-family: monospace; font-weight: bold; }}
        code {{ font-family: monospace; }}
        table.k td {{ padding: 2px 10px 2px 0; }}
        td.kc {{ white-space: nowrap; width: 210px; }}
        span.o {{ color: {muted}; }}
        """

    # ---------------------------------------------------------- navigation
    def show_section(self, key: str | None, push=True):
        key = key if key in self.titles else "inicio"
        if push and self._current and self._current != key:
            self._history.append(self._current)
        self._current = key
        body = next(h for k, _t, h in self.sections if k == key)
        doc = self.view.document()
        doc.setDefaultStyleSheet(self._css)
        self.view.setHtml(f"<html><body>{body}</body></html>")
        for i in range(self.toc.count()):
            it = self.toc.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == key:
                self.toc.blockSignals(True)
                self.toc.setCurrentItem(it)
                self.toc.blockSignals(False)
                break
        q = self.search.text().strip()
        if q:
            self._highlight(q)

    def _toc_changed(self, cur, _prev):
        if cur is not None:
            self.show_section(cur.data(Qt.ItemDataRole.UserRole))

    def _link(self, url: QUrl):
        frag = url.fragment() or url.toString().lstrip("#")
        if frag in self.titles:
            self.show_section(frag)
        elif url.scheme() in ("http", "https"):
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(url)

    def _back(self):
        if self._history:
            self.show_section(self._history.pop(), push=False)

    # -------------------------------------------------------------- search
    def _filter(self, text: str):
        words = _fold(text).split()
        first = None
        for i in range(self.toc.count()):
            it = self.toc.item(i)
            key = it.data(Qt.ItemDataRole.UserRole)
            body = next(h for k, _t, h in self.sections if k == key)
            hay = _fold(self.titles[key] + " " + _plain(body))
            ok = all(w in hay for w in words)
            it.setHidden(not ok)
            if ok and first is None:
                first = key
        if not words:
            self.status.setText(tr("F1: ayuda de la ventana activa · Enter en la búsqueda: siguiente coincidencia"))
            self.show_section(self._current or "inicio", push=False)
            return
        n = sum(not self.toc.item(i).isHidden() for i in range(self.toc.count()))
        self.status.setText(tr("{0} secciones contienen «{1}»").format(n, text.strip()) if n
                            else tr("Sin resultados"))
        if first is not None:
            cur_ok = self._current and not self._item(self._current).isHidden()
            self.show_section(self._current if cur_ok else first, push=False)

    def _item(self, key):
        for i in range(self.toc.count()):
            it = self.toc.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == key:
                return it
        return None

    def _highlight(self, q: str):
        from PySide6.QtGui import QTextCharFormat, QTextCursor
        from PySide6.QtWidgets import QTextEdit
        sels = []
        fmt = QTextCharFormat()
        fmt.setBackground(self.palette().color(QPalette.ColorRole.Highlight))
        fmt.setForeground(self.palette().color(QPalette.ColorRole.HighlightedText))
        doc = self.view.document()
        for w in q.split():
            c = QTextCursor(doc)
            while True:
                c = doc.find(w, c)
                if c.isNull():
                    break
                s = QTextEdit.ExtraSelection()
                s.cursor = c
                s.format = fmt
                sels.append(s)
        self.view.setExtraSelections(sels)
        if sels:
            self.view.setTextCursor(QTextCursor(sels[0].cursor.block()))
            self.view.ensureCursorVisible()

    def _find_next(self):
        q = self.search.text().strip().split()
        if not q:
            return
        if not self.view.find(q[0]):
            # next section with matches
            keys = [self.toc.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.toc.count())
                    if not self.toc.item(i).isHidden()]
            if keys:
                i = (keys.index(self._current) + 1) % len(keys) if self._current in keys else 0
                self.show_section(keys[i])
                self.view.moveCursor(self.view.textCursor().MoveOperation.Start)
                self.view.find(q[0])


# window class name -> help section (F1 opens the help for the active window)
CONTEXT = {
    "SearchLibraryDialog": "buscar", "LibraryWindow": "biblioteca", "RadioDialog": "radio",
    "LyricsWindow": "letras", "MilkdropWindow": "vis", "MilkdropConfig": "vis",
    "PresetPicker": "vis", "PreferencesDialog": "preferencias", "FileInfoDialog": "info",
    "SkinBrowser": "skins", "BookmarksDialog": "marcadores", "JumpToFileDialog": "lista",
    "PlaylistsDialog": "lista", "SmartListDialog": "biblioteca", "QualityWindow": "info",
}


def context_section(app, w) -> str:
    if w is None:
        return "inicio"
    name = type(w).__name__
    if name in CONTEXT:
        return CONTEXT[name]
    fp = getattr(app, "focused_panel", None)
    if fp is not None and fp is getattr(app, "pl_panel", None):
        return "lista"
    if fp is not None and fp is getattr(app, "eq_panel", None):
        return "ecualizador"
    if fp is not None and fp is getattr(app, "ly_panel", None):
        return "letras"
    if fp is not None and fp is getattr(app, "art_panel", None):
        return "escritorio"
    if getattr(app, "modern", None) is not None:
        return "skins"
    return "principal"


__all__ = ["SECTIONS", "HelpWindow", "context_section", "sections"]
