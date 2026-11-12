"""Read/write song tags and embedded cover art with mutagen.

MPD cannot edit tags, but when the music folder is local Zebamp writes the
file directly and then asks MPD to rescan it.
"""
from __future__ import annotations

import base64
import os
from .i18n import tr

FIELDS = [("title", tr("Título")), ("artist", tr("Artista")), ("album", tr("Álbum")),
          ("albumartist", tr("Artista del álbum")), ("date", tr("Año")), ("genre", tr("Género")),
          ("tracknumber", tr("Pista")), ("discnumber", tr("Disco")), ("composer", tr("Compositor"))]


def available() -> bool:
    try:
        import mutagen  # noqa: F401
        return True
    except ImportError:
        return False


def _easy(path):
    import mutagen
    f = mutagen.File(path, easy=True)
    if f is None:
        raise ValueError("formato no reconocido")
    if f.tags is None:
        f.add_tags()
    return f


def read_tags(path: str) -> dict:
    f = _easy(path)
    out = {}
    for k, _label in FIELDS:
        try:
            v = f.tags.get(k)
        except (KeyError, ValueError):
            v = None
        if v:
            out[k] = "; ".join(str(x) for x in v)
    return out


def write_tags(path: str, values: dict):
    """values: field -> text ("" removes the tag; ";" separates multiple)."""
    f = _easy(path)
    for k, v in values.items():
        v = (v or "").strip()
        try:
            if not v:
                if k in f.tags:
                    del f.tags[k]
            else:
                f.tags[k] = [x.strip() for x in v.split(";") if x.strip()]
        except (KeyError, ValueError) as e:
            raise ValueError(f"no se puede escribir «{k}» en este formato: {e}") from e
    f.save()


def _mime(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    return "image/jpeg"


def write_cover(path: str, data: bytes | None):
    """Embed `data` as the front cover (None removes embedded pictures)."""
    import mutagen
    from mutagen.flac import FLAC, Picture
    from mutagen.id3 import APIC, ID3
    from mutagen.mp4 import MP4, MP4Cover
    f = mutagen.File(path)
    if f is None:
        raise ValueError("formato no reconocido")
    mime = _mime(data) if data else ""
    if isinstance(f, FLAC):
        f.clear_pictures()
        if data:
            p = Picture()
            p.type, p.mime, p.data, p.desc = 3, mime, data, "Front cover"
            f.add_picture(p)
        f.save()
    elif isinstance(f, MP4):
        if data:
            fmt = MP4Cover.FORMAT_PNG if mime == "image/png" else MP4Cover.FORMAT_JPEG
            f["covr"] = [MP4Cover(data, imageformat=fmt)]
        elif "covr" in f:
            del f["covr"]
        f.save()
    elif isinstance(getattr(f, "tags", None), ID3) or path.lower().endswith(".mp3"):
        try:
            tags = ID3(path)
        except Exception:
            tags = ID3()
        tags.delall("APIC")
        if data:
            tags.add(APIC(encoding=3, mime=mime, type=3, desc="Front cover", data=data))
        tags.save(path)
    elif f.tags is not None and hasattr(f.tags, "keys"):     # Ogg Vorbis / Opus
        for k in ("metadata_block_picture", "METADATA_BLOCK_PICTURE"):
            if k in f.tags:
                del f.tags[k]
        if data:
            p = Picture()
            p.type, p.mime, p.data, p.desc = 3, mime, data, "Front cover"
            f.tags["metadata_block_picture"] = [base64.b64encode(p.write()).decode("ascii")]
        f.save()
    else:
        raise ValueError("este formato no admite carátula incrustada")


def local_path(player, uri: str) -> str | None:
    """Absolute path of an MPD URI if the music folder is reachable here."""
    if not uri or "://" in uri:
        return None
    md = player.music_directory
    if not md:
        return None
    p = os.path.join(md, uri)
    return p if os.path.isfile(p) else None
