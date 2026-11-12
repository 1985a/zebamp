"""Persistent settings (JSON in ~/.config/zebamp/config.json)."""
from __future__ import annotations

import copy
import json
import logging
import os
import tempfile

log = logging.getLogger(__name__)

CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME",
                                         os.path.expanduser("~/.config")), "zebamp")
DATA_DIR = os.path.join(os.environ.get("XDG_DATA_HOME",
                                       os.path.expanduser("~/.local/share")), "zebamp")
SKIN_DIR = os.path.join(DATA_DIR, "skins")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

DEFAULTS = {
    "mpd_host": "",          # "" = autodetect (MPD_HOST, mpd.conf, ~/.mpd/socket)
    "mpd_port": 6600,
    "mpd_password": "",
    "mpd_profiles": [],      # [{name, host, port, password}]: servers to switch between
    "mpd_profile": "",       # name of the profile in use ("" = none)
    "language": "es",        # es | en | auto (el del sistema); se aplica al iniciar
    "skin": "",              # path to .wsz/.wal or folder; "" = built-in
    "skin_dirs": [SKIN_DIR],
    "scale": 0,              # 0 = automático según la resolución de la pantalla
    "scale_auto_migrated": False,
    "classic_smooth": True,  # skins .wsz: ampliar con Scale2x/3x en vez de píxeles
    "modern_scale": 1.0,     # skins modernos: 1, 1.25, 1.5, 1.75, 2 (suavizado)
    "modern_smooth": True,   # filtrado suave al ampliar skins modernos
    "classic_layout": "free",  # free: ventanas sueltas con imán | fixed: apiladas
    "classic_positions": {},
    "modern_layout": "free",  # free: ventanas sueltas con imán | fixed: todas pegadas | separate
    "modern_positions": {},
    "modern_vis_slot": "spectrum",   # pestaña de visualización del skin: spectrum | milkdrop
    "modern_gamma": {},      # tema de color (gammaset) elegido por skin  # posiciones guardadas por skin (modo free)
    "show_eq": True,
    "show_playlist": True,
    "main_shade": False,
    "eq_shade": False,
    "pl_shade": False,
    "pl_width": 0,           # extra 25px segments
    "pl_height": 2,          # extra 29px segments
    "show_lyrics_panel": False,   # classic skins: skinned lyrics window
    "ly_width": 0,
    "ly_height": 2,
    "ly_font_size": 12,
    "show_art_panel": False,      # classic skins: album art window
    "art_width": 0,
    "art_height": 6,              # 275 x 290: a square picture
    "time_remaining": False,
    "vis_mode": "spectrum",  # spectrum | oscilloscope | off
    "vis_fifo": "",          # "" = autodetect from mpd.conf
    "vis_fifo_format": "",   # e.g. 44100:16:2 ("" = autodetect)
    "vis_source": "auto",    # auto | fifo | pipewire (auto: PipeWire si otro lee el fifo)
    "vis_fps": 50,
    "vis_next_random": False,  # "siguiente preset" elige uno al azar
    "vis_bands": "thick",    # thick | thin
    "vis_peaks": True,
    "vis_falloff": 2,        # 0..4  (slowest..fastest)
    "vis_peak_falloff": 1,   # 0..4
    "vis_coloring": "normal",  # normal | fire | line
    "vis_osc_style": "lines",  # dots | lines | solid
    "marquee_scroll": True,
    "marquee_speed": 1,        # 0 slow, 1 normal, 2 fast
    "use_bitmap_font": True,
    "pl_font_size": 9,
    "pl_show_numbers": True,
    "eq_enabled": False,
    "eq_auto": False,
    "eq_backend": "pipewire",  # pipewire | none
    "eq_bands": [0.0] * 10,    # dB, -12..+12
    "eq_preamp": 0.0,
    "eq_user_presets": {},
    "balance": 0,              # -100..100
    "balance_backend": True,
    "library_geometry": None,
    "library_splitter": None,
    "confirm_clear": False,
    "recent_urls": [],
    "snap": True,
    "always_on_top": False,
    "pl_follow": True,         # la lista sigue a la canción actual
    "random_skin": False,
    "modern_store": {},        # estado interno de los skins modernos (cajón abierto, pestañas…)
    "milkdrop_presets": "",    # "" = presets de projectM del sistema
    "milkdrop_w": 640,
    "milkdrop_h": 480,
    "milkdrop_fps": 60,
    "milkdrop_quality": "medium",  # low | medium | high
    "milkdrop_duration": 20,   # segundos por preset
    "milkdrop_shuffle": True,
    "milkdrop_title": True,
    "milkdrop_smooth": 3,          # segundos de transición suave entre presets
    "milkdrop_hardcut": True,      # cortes bruscos con los golpes fuertes
    "milkdrop_hardcut_min": 60,    # segundos mínimos entre cortes bruscos
    "milkdrop_hardcut_sens": 10.0,
    "milkdrop_beat": 1.0,          # sensibilidad al ritmo
    "milkdrop_aspect": True,       # corrección de aspecto de las figuras
    "milkdrop_fullscreen": False,  # abrir directamente a pantalla completa
    "milkdrop_mesh_x": 48,         # calidad personalizada
    "milkdrop_mesh_y": 36,
    "milkdrop_texture": 1024,
    "close_to_tray": False,
    "bookmarks": [],           # [{file, title, pos}]
    "smart_lists": [],         # listas por reglas (ver smartlist.py)
    "radio_favorites": [],    # cerrar la ventana la oculta en la bandeja
    "acoustid_key": "",        # clave de aplicación de AcoustID: reconocer canciones por su sonido
    "cover_online": True,      # sin carátula local: buscarla en Internet (MusicBrainz, Deezer, iTunes)
    "notify_song": True,       # notificación con carátula al cambiar de canción
    "notify_timeout": 5,       # segundos
    "scroll_title_in_taskbar": False,
    # scrobbling (off until the user enables a service in Preferences)
    "listenbrainz_enabled": False,
    "listenbrainz_token": "",
    "listenbrainz_url": "",    # "" = listenbrainz.org; otro servidor compatible (p. ej. Maloja)
    "lastfm_enabled": False,
    "lastfm_api_key": "",      # la clave y el secreto los crea cada usuario en last.fm/api
    "lastfm_secret": "",
    "lastfm_session": "",
    "lastfm_user": "",
    "lastfm_url": "",          # "" = Last.fm; otro servidor compatible (p. ej. Libre.fm)
}


def default_config_path() -> str:
    """Resolved when a Config is created (not at import time), so tests and
    tools that set XDG_CONFIG_HOME never touch the user's real settings."""
    base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return os.path.join(base, "zebamp", "config.json")


class Config:
    def __init__(self, path: str | None = None):
        self.path = path or default_config_path()
        self.data = copy.deepcopy(DEFAULTS)
        self.load()

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as fh:
                stored = json.load(fh)
            if isinstance(stored, dict):
                # keep everything, even keys this version doesn't know:
                # dropping them silently loses state (e.g. skin settings)
                for k, v in stored.items():
                    self.data[k] = v
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as e:
            log.warning("config unreadable (%s); using defaults", e)
        # sanity
        if len(self.data.get("eq_bands") or []) != 10:
            self.data["eq_bands"] = [0.0] * 10
        if self.data.get("scale") not in (0, 1, 2, 3):
            self.data["scale"] = 0
        # Older configs saved 1x before automatic sizing existed: re-pick once.
        if not self.data.get("scale_auto_migrated"):
            self.data["scale"] = 0
            self.data["scale_auto_migrated"] = True

    def save(self):
        if os.environ.get("ZEBAMP_TESTING") and os.path.abspath(self.path) == os.path.abspath(
                os.path.expanduser("~/.config/zebamp/config.json")):
            raise RuntimeError("test run tried to write the real user config")
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.path), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
        except OSError as e:
            log.warning("could not save config: %s", e)
            try:
                os.unlink(tmp)
            except OSError:
                pass

    def __getitem__(self, k):
        return self.data.get(k, DEFAULTS.get(k))

    def __setitem__(self, k, v):
        self.data[k] = v

    def get(self, k, default=None):
        return self.data.get(k, default)
