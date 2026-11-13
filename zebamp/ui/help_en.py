"""English text of the built-in user guide (see help.py for the window).

Same section keys and the same links as the Spanish guide in help.py; a test
checks that the two stay in step.  Key names shown in <kbd> follow an English
keyboard (Del, Backspace, Home…).
"""
from __future__ import annotations

from .. import __version__
from .help import _keys


def _k(rows):
    return _keys(rows, either="or")


SECTIONS: list[tuple[str, str, str]] = [
    ("inicio", "Welcome", f"""
<h1>Zebamp {__version__}</h1>
<p>Zebamp is a player with the look and feel of <b>Winamp</b> that controls
<b>MPD</b> (Music Player Daemon). MPD plays the music; Zebamp is the “remote control”:
that is why the music keeps playing when you close Zebamp, and whatever you do in other
clients (ncmpcpp, your phone…) shows up here at once.</p>
<p>Use the index on the left or the search box above. Press <kbd>F1</kbd> in any Zebamp
window to open the help for that window.</p>
<h3>Most used</h3>
<ul>
<li><a href="#primeros">Getting started</a>: connect to MPD and play music.</li>
<li><a href="#buscar">Instant search</a>: <kbd>Ctrl+F</kbd> inside Zebamp,
<kbd>Super+Shift+S</kbd> from anywhere on the desktop.</li>
<li><a href="#atajos">All keyboard shortcuts</a>.</li>
<li><a href="#skins">Change the skin</a>: <kbd>Alt+S</kbd>.</li>
<li><a href="#problemas">Troubleshooting</a>.</li>
</ul>
"""),

    ("primeros", "Getting started", """
<h2>Getting started</h2>
<h3>1. Connect to MPD</h3>
<p>Zebamp connects to the local MPD by itself (<code>MPD_HOST</code>/<code>MPD_PORT</code>
variables, or <code>localhost:6600</code>). For another server: <b>Menu › Options ›
Preferences…</b> (<kbd>Ctrl+P</kbd>), <b>MPD</b> tab: server or socket path, port and
password. If MPD goes down or restarts, Zebamp reconnects by itself.</p>
<h3>2. Play music</h3>
<ul>
<li><kbd>L</kbd> play files, <kbd>Shift+L</kbd> a folder, <kbd>Ctrl+L</kbd> a URL.</li>
<li>Drag files or folders onto any Zebamp window.</li>
<li><kbd>Ctrl+F</kbd> searches your whole library instantly (<a href="#buscar">more</a>).</li>
<li><kbd>Alt+L</kbd> opens the <a href="#biblioteca">media library</a> to browse by
artist, album, genre or folder.</li>
<li><kbd>Alt+R</kbd> opens the <a href="#radio">Internet radio</a>.</li>
</ul>
<p>The files must be inside MPD's music folder (or MPD must be able to read them through
its local socket).</p>
<h3>3. Control</h3>
<p>The buttons of the main window, or Winamp's keys: <kbd>Z</kbd> previous,
<kbd>X</kbd> play, <kbd>C</kbd> pause, <kbd>V</kbd> stop, <kbd>B</kbd> next,
<kbd>Space</kbd> play/pause. The media keys of the keyboard work too
(<a href="#escritorio">more</a>).</p>
<h3>The main menu</h3>
<p>Nearly everything is in the <b>main menu</b>: the button in the top left corner of the
main window, or a right-click on it. In modern skins, in the skin's own menu or with a
right-click.</p>
"""),

    ("principal", "Main window", """
<h2>Main window</h2>
<ul>
<li><b>Title bar</b>: drag it to move; double-click = compact mode
(<kbd>Ctrl+W</kbd>). Buttons: menu, minimize, compact and close.</li>
<li><b>Time</b>: click to switch between elapsed / remaining (<kbd>Ctrl+T</kbd>). Songs
longer than 99 minutes show hours.</li>
<li><b>Visualization</b>: click to change the mode (spectrum, oscilloscope, nothing);
right-click for its menu (<a href="#vis">more</a>).</li>
<li><b>Title</b>: it scrolls by itself; you can drag it with the mouse to read it. A
double-click opens the <a href="#info">file info</a>.</li>
<li><b>kbps / kHz / mono / stereo</b>: audio data. With high resolution audio
(1411 kbps, 192 kHz…) the box stretches to show every digit. Hover over it to see the full
format (codec, bits, channels). With console music (.spc, .nsf, .vgm…) or MIDI the bitrate
of the generated audio is shown.</li>
<li><b>Volume and balance</b>: sliders. The mouse wheel over the window also changes the
volume.</li>
<li><b>Position bar</b>: drag it to go to any point.</li>
<li><b>EQ / PL</b>: show or hide the <a href="#ecualizador">equalizer</a> and the
<a href="#lista">playlist</a>.</li>
<li><b>Shuffle / Repeat</b>: <kbd>S</kbd> and <kbd>R</kbd>. Repeat cycles through off, the
whole playlist and the current track.</li>
</ul>
<h3>Side bar O · A · I · D · V</h3>
<table class='k'>
<tr><td class='kc'><b>O</b></td><td>Options menu.</td></tr>
<tr><td class='kc'><b>A</b></td><td>Always on top (above the other windows).</td></tr>
<tr><td class='kc'><b>I</b></td><td>File info.</td></tr>
<tr><td class='kc'><b>D</b></td><td>Double size (<kbd>Ctrl+D</kbd>).</td></tr>
<tr><td class='kc'><b>V</b></td><td>Visualization menu.</td></tr>
</table>
"""),

    ("lista", "Playlist", """
<h2>Playlist</h2>
<p>It is MPD's queue: if another client changes it, it updates here. Show/hide:
<kbd>Alt+E</kbd> or the <b>PL</b> button.</p>
<ul>
<li>Double-click or <kbd>Enter</kbd>: play the song.</li>
<li>Click, <kbd>Shift</kbd>+click and <kbd>Ctrl</kbd>+click to select; drag to reorder;
drag files in from outside to add them.</li>
<li><kbd>Alt+↑</kbd> / <kbd>Alt+↓</kbd> move the selection.</li>
<li><kbd>Del</kbd> removes the selection, <kbd>Shift+Del</kbd> crops (keeps only the
selection), <kbd>Ctrl+Del</kbd> clears the playlist.</li>
<li><kbd>Ctrl+A</kbd> select all, <kbd>Ctrl+I</kbd> invert the selection.</li>
<li><kbd>J</kbd> jump to a song in the playlist by typing part of its name.</li>
<li>Drag the bottom right corner to resize.</li>
</ul>
<h3>Bottom buttons</h3>
<table class='k'>
<tr><td class='kc'><b>ADD</b></td><td>Add a URL, a folder or files.</td></tr>
<tr><td class='kc'><b>REM</b></td><td>Remove selected, crop, clear and other options
(duplicates, entries that no longer exist).</td></tr>
<tr><td class='kc'><b>SEL</b></td><td>Select all, none or invert.</td></tr>
<tr><td class='kc'><b>MISC</b></td><td>Sort (title, file, path, artist/album/track,
reverse, shuffle), file info and options (track numbers, follow the current
song).</td></tr>
<tr><td class='kc'><b>LIST</b></td><td>New playlist, save and load playlists (they are kept
in MPD as stored playlists).</td></tr>
</table>
<p>Right-click on the songs: play, info, remove, send to a saved playlist, rate…</p>
"""),

    ("ecualizador", "Equalizer", """
<h2>Equalizer</h2>
<p>Show/hide: <kbd>Alt+G</kbd> or the <b>EQ</b> button. Ten bands from 60 Hz to 16 kHz
plus the preamp.</p>
<ul>
<li><b>ON</b>: turns the equalizer on or off.</li>
<li><b>AUTO</b>: loads the preset saved for each song automatically.</li>
<li><b>PRESETS</b>: load presets (including Winamp's classics and <code>.eqf</code>
files), save your own or export them to <code>.eqf</code>; “Reset” makes everything
flat.</li>
</ul>
<p><b>How it works:</b> the equalizer is a PipeWire filter (“Zebamp EQ”) placed between
MPD and your audio output. It stays active even if you close Zebamp, so the music is not
cut and its sound does not change. It is set up in <b>Preferences › Equalizer</b>; there
you can also make the balance apply to MPD's audio.</p>
"""),

    ("biblioteca", "Media library", """
<h2>Media library</h2>
<p><kbd>Alt+L</kbd>. Browse MPD's database.</p>
<ul>
<li>On the left: <b>Artists, Album artists, Albums, Genres, Folders</b> and
<b>Saved playlists</b>.</li>
<li>Smart views: <b>Most played, Best rated, Recently played</b> and
<b>Recently added</b> (see <a href="#valoraciones">ratings</a>).</li>
<li><b>Smart lists</b>: your own lists made of rules (see below).</li>
<li>The search box filters by artist, title, album…</li>
<li>Double-click plays; right-click to add, play next, replace the playlist or edit the
tags. You can also drag songs to the playlist.</li>
<li><b>Menu › MPD › Update database</b> when you add new music to the disk.</li>
</ul>
<p>The modern skins Bento and Big Bento carry the library inside their own window.</p>
<h3>Smart lists</h3>
<p>A smart list is not filled by hand: you choose some rules and Zebamp gathers the songs
that match them, always up to date. For example: <i>genre contains “rock”, rating at least
4 and days since last played at least 30</i>.</p>
<ul>
<li>Open <b>Smart lists</b> in the tree and double-click <b>＋ New smart list…</b> (or
right-click).</li>
<li>Rules about: title, artist, album, album artist, genre, folder or file, rating, times
played, year, length and days since last played. A song you have never played counts as
“many days since last played”.</li>
<li>Choose whether <b>all</b> the rules must match or <b>any</b> of them, the order (by
artist, random, most played, best rated…) and a maximum number of songs.</li>
<li>Right-click a list to <b>edit</b> or <b>delete</b> it; a double-click plays it.</li>
</ul>
"""),

    ("buscar", "Instant search", """
<h2>Instant search</h2>
<p>Searches the <b>whole</b> library as you type, even with hundreds of thousands of songs
(the index is kept in memory; the first time it takes a few seconds to load).</p>
<h3>How to open it</h3>
<ul>
<li>Inside Zebamp: <kbd>Ctrl+F</kbd>, <kbd>F3</kbd> or <kbd>/</kbd>.</li>
<li><b>From anywhere on the desktop</b>: <kbd>Super+Shift+S</kbd>. It works even if Zebamp
is minimized, on another workspace or in the tray; if it is not open, it opens it.</li>
<li>From a terminal or a shortcut of your own: <code>zebamp --buscar</code>.</li>
</ul>
<h3>Use</h3>
<ul>
<li>Type several words: all of them must appear (in the title, artist, album or file
name); upper case and accents do not matter.</li>
<li><kbd>↑</kbd>/<kbd>↓</kbd> to choose.</li>
<li><kbd>Enter</kbd>: play now.</li>
<li><kbd>Ctrl+Enter</kbd>: play next.</li>
<li><kbd>Insert</kbd> or <kbd>Shift+Enter</kbd>: add to the end of the playlist.</li>
<li><kbd>Esc</kbd>: close.</li>
</ul>
<p>To search only inside the current playlist use <kbd>J</kbd>
(<a href="#lista">jump to file</a>).</p>
"""),

    ("skins", "Skins", """
<h2>Skins</h2>
<p>Zebamp uses Winamp skins as they are, without converting them:</p>
<ul>
<li><b>Classic</b> (<code>.wsz</code>): those of Winamp 2. The default <b>Zebamp</b> skin
is drawn with vectors and looks sharp at any size.</li>
<li><b>Modern</b> (<code>.wal</code>): those of Winamp 3/5, such as <b>Winamp Modern</b>,
<b>Bento</b> and <b>Big Bento</b>, with their scripts.</li>
</ul>
<h3>Change the skin</h3>
<ul>
<li><kbd>Alt+S</kbd>: skin browser with preview.</li>
<li><b>Menu › Skins</b>: quick list, load from a file, open the skins folder and the
<i>Winamp Skin Museum</i> to download thousands more.</li>
<li>A double-click on a <code>.wsz</code> or <code>.wal</code> in the file manager
installs it and applies it.</li>
</ul>
<h3>Size and look</h3>
<ul>
<li><b>Menu › Options › Size</b>: 1x, 2x, 3x for classic skins (<kbd>Ctrl+D</kbd> =
double); from 1x to 2x for modern ones.</li>
<li>“Smooth bitmap skins (Scale2x/3x)”: enlarges classic skins without making them look
pixelated.</li>
<li>Some modern skins bring <b>color themes</b> (Menu › Options › Skin color theme).</li>
</ul>
<h3>Free windows that snap together</h3>
<p>As in Winamp, the main window, the equalizer and the playlist move separately and stick
to each other and to the screen edges when brought close. If you move the main window, it
takes the ones docked to it along; to undock one, drag that one alone. Zebamp remembers
where you left them and opens them like that next time, already joined.</p>
<h3>Several monitors</h3>
<ul>
<li>The windows stay on the monitor where you put them: a click on them or a small
movement never sends them to another screen.</li>
<li>To take them to the other monitor, <b>drag them to the edge facing that monitor</b> and
keep dragging: at that moment the way opens and they cross. When you let go, they stay on
the monitor where you left them.</li>
<li>Zebamp belongs to a single workspace (that of the monitor it is on); it does not show
on the other workspaces. To look for a song from anywhere else use
<kbd>Super+Shift+S</kbd> (<a href="#buscar">instant search</a>).</li>
<li>If you drop a window in an area that does not exist (for example, below a smaller
monitor), the whole group comes back onto the screen without coming apart.</li>
</ul>
<p>With modern skins you can choose “All docked in one block” and, if they get out of
place, “Rearrange the skin's windows” (Menu › Options › Size).</p>
"""),

    ("vis", "Visualization and MilkDrop", """
<h2>Visualization</h2>
<p>The visualizer of the main window shows the spectrum or the oscilloscope. Click to
change the mode; right-click (or the <b>V</b> of the side bar) for its menu: thick or thin
bars, peaks, speed, frames per second…</p>
<p>Zebamp takes the audio from MPD's <i>fifo</i> output, or captures it from PipeWire if
another program (for example, ncmpcpp's visualizer) is already reading that fifo; that way
both work at the same time. It is set up in <b>Preferences › Visualization</b>.</p>
<h2>MilkDrop</h2>
<p><kbd>Ctrl+Shift+K</kbd> (or <kbd>Ctrl+K</kbd>, or Menu › Visualization › MilkDrop) opens
MilkDrop's psychedelic effects (projectM engine) in their own window.</p>
<p>With a modern skin that has a visualization tab (Bento, Big Bento), <b>Menu ›
Visualization › Skin's visualization tab</b> chooses what is shown in it: the spectrum
analyzer or MilkDrop. A double-click on MilkDrop in the tab opens it in its window.</p>
""" + _k([
        ("Space N", "next preset, with a soft transition"),
        ("H", "hard cut to another preset"),
        ("Backspace P", "previous preset"),
        ("L", "choose a preset from a list with search"),
        ("K ScrollLock", "lock the current preset"),
        ("R", "shuffle on/off"),
        ("T", "show the song title"),
        ("C", "MilkDrop settings"),
        ("Enter F F11", "full screen (or double-click)"),
        ("Esc", "leave full screen / close"),
    ]) + """
<p><b>Configure MilkDrop…</b> (Menu › Visualization): presets folder, how often to change,
transition length, hard cuts on the beats of the music, quality, mesh, texture, frames per
second and beat sensitivity. With “Random next preset” the next preset is picked at
random.</p>
"""),

    ("radio", "Internet radio", """
<h2>Internet radio</h2>
<p><kbd>Alt+R</kbd>. Search the stations of the public <i>radio-browser</i> directory by
name, country, language or genre. A double-click or <kbd>Enter</kbd> plays the station in
MPD. Mark your favorites to keep them at hand. The title of what is playing is shown as
with any song.</p>
"""),

    ("letras", "Lyrics", """
<h2>Lyrics</h2>
<p><kbd>Ctrl+Shift+L</kbd> (or Menu › Lyrics). Zebamp looks for the lyrics in this
order:</p>
<ol>
<li>A <code>.lrc</code> file next to the song, with the same name
(<code>song.flac</code> → <code>song.lrc</code>): your own lyrics come first.</li>
<li>The lyrics stored in the file's tags (LYRICS, SYNCEDLYRICS…).</li>
<li><i>LRCLIB</i> on the Internet, choosing the version whose length is closest to your
song. If the song has no tags, it is looked up by the file name
(“Artist - Title”).</li>
</ol>
<p>What is found is cached. If there are no lyrics, it says “No lyrics were found for this
song” and the Internet is not asked again for three days (“Search again” forces it).</p>
<h3>Lyrics out of step or too fast</h3>
<p>Sometimes the lyrics belong to another version: a faster one, or one with a shorter
intro.</p>
<ul>
<li><b>Automatic</b>: if the lyrics are from a clearly longer or shorter version, Zebamp
adjusts the speed and says so.</li>
<li><b>Shift+click a line at the moment you hear it</b>: the lyrics fall into place. If you
do it with another line further on (at least 20 seconds later), Zebamp works out the speed
too. It is the most reliable way.</li>
<li>Right-click: “Lyrics later / earlier” (half a second each time) or “Reset
sync”.</li>
<li>The correction is saved for that song and applied next time.</li>
<li><code>.lrc</code> lyrics with the <code>[offset:]</code> tag are respected.</li>
</ul>
<h3>With a classic skin</h3>
<p>The lyrics appear in a <b>window with the look of the skin</b> (the frame of Winamp's
generic windows and the colors and font of the playlist). It works like the equalizer or
the playlist: it snaps to the other windows, moves with the group, and Zebamp remembers
where it was and whether it was open.</p>
<ul>
<li>If the lyrics are <b>synced</b>, the line being sung is highlighted and the window
scrolls by itself; the lines already sung are dimmed.</li>
<li><b>Double-click</b> a line: jump to that moment of the song.
<b>Shift+click</b>: “this line is playing now” (sync).</li>
<li><b>Mouse wheel</b>: scroll through the lyrics; after 5 seconds it follows the song
again.</li>
<li>Drag the <b>bottom right corner</b> to resize.</li>
<li><b>Right-click</b>: search for the lyrics again, bigger or smaller text, open them in a
separate window or close.</li>
</ul>
<h3>With a modern skin</h3>
<p>A normal window opens with the lyrics, with the same features: current line highlighted,
double-click to jump, Shift+click to sync and right-click to adjust.</p>
"""),

    ("info", "File info and tags", """
<h2>File info and tag editing</h2>
<p><kbd>Alt+3</kbd>, the <b>I</b> of the side bar or a double-click on the title. Shows the
tags, the audio format, the cover and the path.</p>
<p>You can <b>edit</b> the title, artist, album, year, genre, track number, etc. Before
writing to the file, Zebamp shows you the changes and asks for <b>confirmation</b>. Then it
tells MPD to update its database. It only works with local files you are allowed to
modify.</p>
<h3>Audio quality</h3>
<p><kbd>Alt+Q</kbd> (or Menu › Playback › Audio quality…, or a right-click on a song in the
playlist) opens the song's <b>spectrogram</b>: a picture of its sound, with time running
from left to right and pitch from bass (bottom) to treble (top); the brighter, the
louder.</p>
<p>A file's format does not guarantee its quality: a FLAC made from an MP3 is as large as a
true one and sounds like the MP3. The picture gives it away, because lossy formats remove
everything above some frequency and leave a straight edge with nothing but black above.
Zebamp looks for that edge and gives you a verdict:</p>
<ul>
<li><b>True lossless</b>: the sound reaches the top (about 22 kHz at CD quality).</li>
<li><b>True high resolution</b>: files at 88.2 kHz or more with sound above what fits on a
CD.</li>
<li><b>Suspicious</b>: a lossless format that stops dead (it probably comes from an MP3), a
high resolution file with nothing above 22 kHz, or an MP3 with many kbps that sounds like
one with few.</li>
<li><b>Lossy</b>, with its level: the cut is around 16 kHz at 128 kbps, 19 kHz at 192 and
20 kHz at 256–320.</li>
</ul>
<p>It is an estimate: some old recordings have little treble to begin with. The program
<code>ffmpeg</code> is needed, and the file must be on this computer. For the tracks of a
<code>.cue</code> only that track's stretch is analysed.</p>
<h3>Recognising a song by its sound</h3>
<p>For files with no tags and no useful name, Zebamp can find out what song it is by
listening to it: it works out an <i>audio fingerprint</i> of the file and looks it up in the
public <b>AcoustID</b> database, which answers with the artist, the title and the album.</p>
<ul>
<li>It is enabled by putting your key in <b>Preferences › Internet</b>. The key is free: it
is created at acoustid.org/new-application. The program <code>fpcalc</code> (package
<code>chromaprint</code>) is needed too.</li>
<li>In the file info window, <b>Recognise by sound…</b> proposes the artist, title and album
in the boxes; nothing is written to the file until you press “Save changes”.</li>
<li>The cover search uses it by itself when the file lacks tags and nothing was found by
its name.</li>
<li>Each file is listened to only once; the result is remembered.</li>
</ul>
<p>It needs the Internet. Phone apps that recognise music offline carry their own database
of songs inside; a player cannot. Only the audio fingerprint and the length are sent, never
the file.</p>
"""),

    ("valoraciones", "Ratings and statistics", """
<h2>Ratings and statistics</h2>
<ul>
<li>Rate the current song from 0 to 5 stars with <kbd>Ctrl+Alt+0</kbd> …
<kbd>Ctrl+Alt+5</kbd>, from Menu › Playback › Rate, or from the tray icon.</li>
<li>Zebamp counts how many times you listen to each song (it counts once it passes half, or
4 minutes) and when the last time was.</li>
</ul>
<p>Everything is kept in MPD's <i>sticker</i> database, so you keep it even if you reinstall
Zebamp, and other clients can read it. If your MPD has no stickers, it is kept in a local
file. The “Most played”, “Best rated”, etc. views are in the
<a href="#biblioteca">library</a>, and you can use them in your
<a href="#biblioteca">smart lists</a>.</p>
<h3>Scrobbling (ListenBrainz and Last.fm)</h3>
<p>Zebamp can send what you listen to to your <b>ListenBrainz</b> or <b>Last.fm</b>
profile. It is off until you enable it in <b>Preferences › Scrobbling</b>.</p>
<ul>
<li><b>ListenBrainz</b>: copy your user token (listenbrainz.org/settings), paste it and
press <b>Check</b>. A compatible server of your own works too.</li>
<li><b>Last.fm</b>: create a free API key (last.fm/api/account/create), type the key and
the secret and press <b>Connect…</b>; the browser opens for you to authorize Zebamp, and
when you come back you press <b>I have authorized it</b>.</li>
<li>A song is sent once it has played past half (or 4 minutes). Radio is not sent, nor
files without artist and title tags, nor tracks shorter than 30 s.</li>
<li>Nothing is lost without Internet: listens are kept and sent when the connection comes
back.</li>
</ul>
<p>The token and the keys are kept in your settings file, unencrypted.</p>
"""),

    ("marcadores", "Bookmarks", """
<h2>Bookmarks</h2>
<p><kbd>Ctrl+Alt+B</kbd> saves the current song <b>at the exact point</b> it is at (useful
for long mixes, audiobooks or podcasts). Menu › Bookmarks to go back to it, or “Edit
bookmarks…” to rename or delete them.</p>
"""),

    ("reproduccion", "Playback options", """
<h2>Playback options</h2>
<ul>
<li><b>Shuffle</b> (<kbd>S</kbd>) and <b>Repeat</b> (<kbd>R</kbd>: off / whole playlist /
current track).</li>
<li><b>Consume</b>: removes each song from the playlist when it finishes playing.</li>
<li><b>Stop after the current track</b>.</li>
<li><b>Crossfade between tracks</b> from 2 to 10 s.</li>
<li><b>Sleep timer</b> (Menu › Options): pauses the music in 15, 30, 45, 60, 90 or 120
minutes, or as many as you say, or <b>when the album ends</b> (it lets its last song
finish). The same menu shows how long is left and lets you cancel it.</li>
<li><kbd>←</kbd>/<kbd>→</kbd> go back or forward 5 s; <kbd>Ctrl+J</kbd> jumps to an exact
time.</li>
<li><kbd>↑</kbd>/<kbd>↓</kbd> turn the volume up or down.</li>
</ul>
<p>In <b>Preferences › Audio (MPD)</b>: crossfade, MixRamp and ReplayGain (evening out the
volume between songs). These options are stored in MPD and affect all its clients.
<b>Menu › MPD › Audio outputs</b> turns MPD's audio outputs on or off.</p>
<h3>Several MPD servers</h3>
<p>If you have more than one MPD (the one on this computer, a server at home…), save each
connection as a profile: connect in <b>Preferences › MPD</b> and choose <b>Menu › MPD ›
Server › Save the current connection as a profile…</b>. Afterwards you switch from one to
another in that same menu; <b>Automatic</b> goes back to the MPD on this computer. Ratings
and the search index belong to each server.</p>
"""),

    ("escritorio", "Desktop integration", """
<h2>Desktop integration</h2>
<ul>
<li><b>Media keys</b> (play, next, previous, stop) and <code>playerctl</code>: Zebamp
announces itself through MPRIS, so bars such as waybar and desktop widgets control it too,
and show the title and the cover.</li>
<li><b>System tray</b>: click to show/hide; right-click to control playback, rate, search,
radio and lyrics. With <i>Close to tray</i> (Menu › Options), closing the window only hides
it.</li>
<li><b>Notifications</b> with the cover when the song changes (Menu › Options › Notify on
song change).</li>
<li><b>Always on top</b>: Menu › Options or the <b>A</b> of the side bar.</li>
<li><b>File associations</b>: <code>.wsz</code>/<code>.wal</code> skins open with
Zebamp.</li>
<li><b>Global search</b>: <kbd>Super+Shift+S</kbd> (a sway shortcut).</li>
<li><b>Drag and drop</b>: drop files or folders on the main window to play them, or on the
playlist to add them at that point. A dropped skin is installed.</li>
<li><b>Album art</b>: <kbd>Ctrl+Shift+A</kbd> opens the album cover in a window of the
classic skin, which docks and resizes like the others.</li>
</ul>
<h3>Covers from the Internet</h3>
<p>The cover your music carries always wins: the picture embedded in the file, the one MPD
gives (<code>cover.jpg</code>…) or any picture in the album's folder. Only when there is
none does Zebamp look on the Internet, and it would rather show nothing than show another
record's cover:</p>
<ol>
<li>If the file has the album's MusicBrainz id in its tags (MusicBrainz Picard writes
them), that is used: it is exact.</li>
<li>Otherwise it searches by <b>artist and album</b> on MusicBrainz (Cover Art Archive),
Deezer and iTunes, in that order. A result is accepted only if the title and the artist
really match: “Greatest Hits 2” will not do for “Greatest Hits”, nor will the same title by
another artist.</li>
<li>Songs without an album tag are searched by <b>artist, title and length</b>, so that the
studio version is not mistaken for a live one.</li>
<li>If the file lacks tags, what its <b>name</b> says is used
(“Artist - Title.mp3”).</li>
<li>If it still does not turn up, and you have enabled it, Zebamp <b>recognises the song by
its sound</b> (<a href="#info">more</a>) and uses the exact cover of its album.</li>
</ol>
<p>What is found is kept (once per album), and when nothing turns up it is not asked again
for a week. Right-click on the album art window:</p>
<ul>
<li><b>This is not the cover: look for another</b>: discards it for good and tries the next
match.</li>
<li><b>Leave this album without a cover</b>: searches no more for that album.</li>
<li><b>Look for the cover on the Internet</b>: searches now, even if a recent search found
nothing.</li>
<li><b>Look for covers on the Internet</b> (also in Menu › Options): turns the whole
feature on or off. A search sends those services the artist and the album (or the title);
nothing else.</li>
</ul>
<p>Downloaded covers are also used in notifications and desktop widgets. They are not
written into your music files.</p>
<h3>Compositors</h3>
<p>The free windows that snap together need the compositor to say where the monitors are
and to let Zebamp's window be placed. This is done and tested on <b>sway</b>. On
<b>Hyprland</b> <code>hyprctl</code> is used (experimental: it has not been tried on a real
machine yet). On the others (KDE, GNOME…) Zebamp works with what Qt tells it, and the
placement may vary; with modern skins, <b>Options › Size › All docked in one block</b> does
not depend on the compositor.</p>
<p>Closing Zebamp does not stop the music or cause dropouts: MPD keeps playing and the
equalizer stays active.</p>
"""),

    ("terminal", "Command line", """
<h2>Command line</h2>
<p>If Zebamp is already open, these commands are sent to the open window (useful for window
manager shortcuts):</p>
""" + _k([
        ("zebamp", "open Zebamp"),
        ("zebamp file.flac folder/ URL", "play files, folders or stations"),
        ("--buscar", "open the song search"),
        ("--saltar", "open “jump to file”"),
        ("--reproducir --pausa --play-pausa --detener", "control playback (play, pause, toggle, stop)"),
        ("--siguiente --anterior", "change the song (next, previous)"),
        ("--letras --radio --milkdrop", "open those windows (lyrics, radio, MilkDrop)"),
        ("--ayuda", "open this help"),
        ("--host --port", "use another MPD server"),
        ("--skin file", "load a skin"),
        ("--lang en", "use another language (es, en) for this run only"),
        ("--debug", "show diagnostic messages"),
    ]) + """
<p>Every command also has an English name: <code>--search</code>, <code>--jump</code>,
<code>--play</code>, <code>--pause</code>, <code>--toggle</code>, <code>--stop</code>,
<code>--next</code>, <code>--prev</code>, <code>--lyrics</code> and
<code>--manual</code>.</p>
<p>Example of a sway shortcut: <code>bindsym $mod+Shift+s exec zebamp --buscar</code></p>
"""),

    ("preferencias", "Preferences", """
<h2>Preferences</h2>
<p><kbd>Ctrl+P</kbd> or <kbd>Alt+K</kbd>.</p>
<ul>
<li><b>MPD</b>: server, port, password and connection status.</li>
<li><b>Display</b>: size, use the skin's font for the title (turn it off to see accented
letters with a system font), title scrolling and speed, playlist font size.</li>
<li><b>Visualization</b>: MPD's fifo and its format.</li>
<li><b>Equalizer</b>: equalizer engine and balance in PipeWire.</li>
<li><b>Audio (MPD)</b>: crossfade, MixRamp and ReplayGain.</li>
<li><b>Scrobbling</b>: ListenBrainz and Last.fm accounts
(<a href="#valoraciones">more</a>).</li>
<li><b>Internet</b>: looking for covers and recognising songs by their sound
(<a href="#info">more</a>).</li>
</ul>
<p><b>Language</b>: Menu › Options › Language (Spanish or English); it takes effect when
Zebamp is restarted.</p>
<p>The settings are kept in <code>~/.config/zebamp/config.json</code>, together with the
position of the windows.</p>
"""),

    ("atajos", "Keyboard shortcuts", """
<h2>Keyboard shortcuts</h2>
<p>They work with any Zebamp window active (except the global one).</p>
<h3>Playback</h3>
""" + _k([
        ("Z", "previous"), ("X", "play"), ("C", "pause"), ("V", "stop"),
        ("B", "next"), ("Space", "play / pause"),
        ("←/→", "back / forward 5 s"), ("↑/↓", "volume up / down"),
        ("Ctrl+J", "jump to a time"), ("S", "shuffle"), ("R", "repeat"),
        ("Ctrl+Alt+0…5", "rate the current song"),
        ("Ctrl+Alt+B", "add a bookmark"),
    ]) + "<h3>Open and search</h3>" + _k([
        ("L", "play files"), ("Shift+L", "play a folder"), ("Ctrl+L", "play a URL"),
        ("Insert", "add files to the playlist"),
        ("Ctrl+F F3 /", "instant search in the library"),
        ("Super+Shift+S", "search from anywhere on the desktop"),
        ("J", "jump to a song in the playlist"),
    ]) + "<h3>Windows</h3>" + _k([
        ("F1", "this help"),
        ("Alt+E", "playlist"), ("Alt+G", "equalizer"),
        ("Alt+L", "media library"), ("Alt+R", "Internet radio"),
        ("Ctrl+Shift+L", "lyrics"), ("Ctrl+Shift+A", "album art"), ("Ctrl+K Ctrl+Shift+K", "MilkDrop"),
        ("Alt+3", "file info"), ("Alt+Q", "audio quality (spectrogram)"),
        ("Alt+S", "skin browser"),
        ("Ctrl+P Alt+K", "preferences"), ("Ctrl+W Alt+W", "compact mode"),
        ("Ctrl+D", "double size"), ("Ctrl+T", "time remaining / elapsed"),
        ("Ctrl+Q", "quit"),
    ]) + "<h3>Playlist</h3>" + _k([
        ("Enter", "play the selected song"), ("Del", "remove"),
        ("Shift+Del", "crop"), ("Ctrl+Del", "clear"),
        ("Ctrl+A", "select all"), ("Ctrl+I", "invert the selection"),
        ("Alt+↑ Alt+↓", "move the selection"), ("Home End PgUp PgDn", "move around"),
    ]) + "<h3>Search</h3>" + _k([
        ("Enter", "play now"), ("Ctrl+Enter", "play next"),
        ("Insert Shift+Enter", "add to the end"), ("Esc", "close"),
    ]) + "<p>MilkDrop's shortcuts are in <a href='#vis'>its section</a>.</p>"),

    ("problemas", "Troubleshooting", """
<h2>Troubleshooting</h2>
<h3>“MPD not connected”</h3>
<p>Check that MPD is running (<code>systemctl --user status mpd</code> or
<code>mpc status</code>) and the details in <b>Preferences › MPD</b>. Zebamp retries by
itself every few seconds.</p>
<h3>Covers are not shown</h3>
<p>Zebamp asks MPD for them (embedded picture or <code>cover.jpg</code> in the folder). MPD
must be able to read the files; after restarting MPD by hand as another user it may lack
the permissions or the same configuration. If the music carries no cover, it is looked up
on the Internet (<a href="#escritorio">more</a>): the artist and album (or title) tags need
to be right.</p>
<h3>The visualization does not move</h3>
<p>MPD needs a <i>fifo</i> output (see <b>Preferences › Visualization</b>, which says
whether data is arriving). Without a fifo, Zebamp tries to capture the audio from
PipeWire.</p>
<h3>The equalizer does nothing</h3>
<p>It needs PipeWire, and MPD playing through it. <b>Preferences › Equalizer</b> says
whether PipeWire is available.</p>
<h3>The skin's windows are out of place or off the screen</h3>
<p>Menu › Options › Size › “Rearrange the skin's windows” (modern skins), or drag them;
if one ends up off the screen, Zebamp brings it back when you drop it.</p>
<h3>Zebamp shows on every workspace of a monitor</h3>
<p>This happens if a window of the skin was left straddling the two monitors: the player
has to cover both to show it. Drag the group so that all of it is on one monitor.</p>
<h3>The title has no accented letters</h3>
<p>That is the skin's bitmap font, which (as in Winamp) has no accented letters. Turn off
“Use the skin's font for the title” in <b>Preferences › Display</b>.</p>
<h3>More information</h3>
<p>Run <code>zebamp --debug</code> in a terminal to see diagnostic messages.</p>
"""),

    ("acerca", "About Zebamp", f"""
<h2>About Zebamp</h2>
<p>Zebamp {__version__}: a Winamp clone for MPD, written in Python with Qt (PySide6).</p>
<p>It uses MPD to play, PipeWire for the equalizer and the audio capture, projectM for
MilkDrop, LRCLIB for the lyrics and radio-browser for the stations. Skins belong to their
authors.</p>
"""),
]
