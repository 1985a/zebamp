"""How good is a music file really: its spectrogram and what it tells.

A file's format says little about its quality: a FLAC made from an MP3 is
as large as a true one and sounds like the MP3.  The picture of the sound
does not lie -- lossy encoders throw away everything above some frequency
(about 16 kHz at 128 kbps, 19 kHz at 192, 20 kHz at 320), which shows as a
sharp edge with nothing above it, while a real lossless file reaches the top.

`analyse()` decodes the file with ffmpeg (as a stream, never the whole song
in memory), builds the spectrogram and the average spectrum, finds that edge
and words a verdict.  Everything else here is pure and tested with made-up
signals.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field

import numpy as np

from .i18n import tr

log = logging.getLogger(__name__)

FFT_SIZE = 4096
HOP = FFT_SIZE // 2
IMAGE_COLUMNS = 900         # width of the spectrogram, in time steps
IMAGE_ROWS = 512            # its height, in frequency steps
FLOOR_DB, TOP_DB = -120.0, 0.0      # range of levels the picture shows

LOSSLESS = {"flac", "alac", "ape", "wavpack", "tta", "wmalossless", "mlp", "truehd", "tak"}
LOSSLESS_PREFIXES = ("pcm_", "dsd_")

# the edge: a fall of at least EDGE_DROP_DB between the band just below a
# frequency and the band just above it, looked for from EDGE_FROM_HZ up
EDGE_FROM_HZ = 10_000
EDGE_BAND_HZ = (200, 1000)
EDGE_DROP_DB = 18.0
FULL_BAND_HZ = 20_800       # an edge this high is the top of CD audio, not a lossy cut
HIRES_RATE = 60_000         # sample rates above this promise more than 20 kHz
HIRES_CONTENT_HZ = 24_000
HIRES_BAND_WIDTH_HZ = 8_000
HIRES_REFERENCE_HZ = (16_000, 20_000)
INFLATED_KBPS = 224         # a lossy file at least this big should not sound like 128 kbps
HIRES_MAX_FALL_DB = 30.0    # real ultrasonic content is at most this far below the top of the audible band

FULL, HIGH, MEDIUM, LOW, POOR = "full", "high", "medium", "low", "poor"
# (edge at least this high, level, the MP3 bitrate that cuts about there)
LEVELS = ((FULL_BAND_HZ, FULL, ""), (19_000, HIGH, "256–320 kbps"), (17_500, MEDIUM, "192 kbps"),
          (15_000, LOW, "128 kbps"), (0, POOR, "96 kbps"))


# ------------------------------------------------------------- the file
@dataclass
class AudioInfo:
    codec: str = ""
    sample_rate: int = 0
    bits: int = 0
    channels: int = 0
    bitrate: int = 0            # kbps
    duration: float = 0.0

    @property
    def lossless(self) -> bool:
        return self.codec in LOSSLESS or self.codec.startswith(LOSSLESS_PREFIXES)


def available() -> bool:
    """ffmpeg and ffprobe are installed."""
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _int(value) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def info_from_probe(probe: dict) -> AudioInfo | None:
    """AudioInfo from ffprobe's JSON; None when the file has no audio."""
    streams = probe.get("streams") if isinstance(probe, dict) else None
    audio = next((s for s in streams or [] if isinstance(s, dict) and s.get("codec_type") == "audio"), None)
    if audio is None:
        return None
    container = probe.get("format") if isinstance(probe.get("format"), dict) else {}
    try:
        duration = float(audio.get("duration") or container.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    return AudioInfo(codec=str(audio.get("codec_name") or ""), sample_rate=_int(audio.get("sample_rate")),
                     bits=_int(audio.get("bits_per_raw_sample")) or _int(audio.get("bits_per_sample")),
                     channels=_int(audio.get("channels")),
                     bitrate=(_int(audio.get("bit_rate")) or _int(container.get("bit_rate"))) // 1000,
                     duration=duration)


_CUE_FILE = re.compile(r'^\s*FILE\s+"([^"]+)"', re.I | re.M)
_INSIDE_CUE = re.compile(r"^(.*\.cue)/[^/]+$", re.I)


def cue_audio_file(cue_text: str) -> str:
    """The audio file a CUE sheet describes (its first FILE line)."""
    found = _CUE_FILE.search(cue_text)
    return found.group(1) if found else ""


def song_range(song: dict) -> tuple[float, float] | None:
    """(start, end) seconds of a song that is a stretch of a bigger file (a
    track of a CUE sheet); end 0 = to the end of the file."""
    start, _dash, end = str(song.get("range") or "").partition("-")
    try:
        return float(start), float(end or 0)
    except ValueError:
        return None


def audio_file_of(song: dict, music_dir: str | None) -> str | None:
    """The file on this computer holding the song's audio (for a track of a
    CUE sheet, the album file the sheet names); None if it is not here."""
    uri = song.get("file", "")
    if not uri or "://" in uri or not music_dir:
        return None
    inside = _INSIDE_CUE.match(uri)
    if not inside:
        path = os.path.join(music_dir, uri)
        return path if os.path.isfile(path) else None
    sheet = os.path.join(music_dir, inside.group(1))
    try:
        with open(sheet, encoding="utf-8", errors="replace") as fh:
            named = cue_audio_file(fh.read())
    except OSError:
        return None
    path = os.path.join(os.path.dirname(sheet), named)
    return path if named and os.path.isfile(path) else None


# ---------------------------------------------------------- the spectrum
def smooth(levels: np.ndarray, width: int) -> np.ndarray:
    """Moving average over `width` points (edges keep their own mean)."""
    width = max(1, int(width))
    if width == 1 or len(levels) < width:
        return levels.astype(np.float64)
    padded = np.concatenate([np.full(width // 2, levels[0]), levels, np.full(width - width // 2 - 1, levels[-1])])
    return np.convolve(padded, np.ones(width) / width, mode="valid")


def find_edge(spectrum_db: np.ndarray, sample_rate: int) -> float | None:
    """Frequency (Hz) of the sharp fall a lossy encoder leaves in the
    average spectrum, or None when the sound just fades naturally.

    For each frequency the mean level of the band just below is compared
    with the band just above; the biggest fall wins if it is big enough and
    the sound stays down above it."""
    bins = len(spectrum_db)
    if bins < 64 or sample_rate <= 0:
        return None
    hz_per_bin = sample_rate / 2 / (bins - 1)
    levels = smooth(spectrum_db, max(1, round(150 / hz_per_bin)))
    near, far = (max(1, round(hz / hz_per_bin)) for hz in EDGE_BAND_HZ)
    first, last = round(EDGE_FROM_HZ / hz_per_bin), bins - far - 1
    if last <= first:
        return None
    sums = np.concatenate([[0.0], np.cumsum(levels)])

    def band_mean(lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
        return (sums[hi] - sums[lo]) / (hi - lo)
    at = np.arange(first, last)
    drops = band_mean(at - far, at - near) - band_mean(at + near, at + far)
    best = int(np.argmax(drops))
    if drops[best] < EDGE_DROP_DB:
        return None
    edge = at[best]
    above = levels[edge + near:]
    below = levels[max(0, edge - far):edge - near]
    if len(above) == 0 or np.max(above) > np.mean(below) - EDGE_DROP_DB / 2:
        return None             # the sound comes back above it: a dip, not a cut
    return float(edge * hz_per_bin)


def has_content_above(spectrum_db: np.ndarray, sample_rate: int, hz: float) -> bool:
    """Whether the sound goes on above `hz` instead of falling off a cliff.

    The band just above `hz` is compared with the top of CD audio: real
    hi-res sound keeps fading gently there, while a CD stretched to a hi-res
    file has nothing but the resampler's silence.  (Only that first band is
    looked at: far above it even true hi-res files are just noise.)"""
    bins = len(spectrum_db)
    hz_per_bin = sample_rate / 2 / (bins - 1)
    start = round(hz / hz_per_bin)
    stop = min(round((hz + HIRES_BAND_WIDTH_HZ) / hz_per_bin), round(0.95 * (bins - 1)))
    if stop - start < 8:
        return False
    audible = spectrum_db[round(HIRES_REFERENCE_HZ[0] / hz_per_bin):round(HIRES_REFERENCE_HZ[1] / hz_per_bin)]
    return bool(np.mean(spectrum_db[start:stop]) > np.mean(audible) - HIRES_MAX_FALL_DB)


# ------------------------------------------------------------ the verdict
@dataclass
class Verdict:
    level: str                  # FULL, HIGH, MEDIUM, LOW or POOR
    title: str
    detail: str
    suspicious: bool = False    # the file claims more than it holds


def level_for(edge_hz: float | None) -> tuple[str, str]:
    """(level, the MP3 bitrate that cuts there) for an edge frequency."""
    if edge_hz is None:
        return FULL, ""
    return next((level, bitrate) for floor, level, bitrate in LEVELS if edge_hz >= floor)


def _khz(hz: float) -> str:
    return f"{hz / 1000:.1f}".replace(".", tr(","))


def judge(info: AudioInfo, edge_hz: float | None, hires_content: bool) -> Verdict:
    """What the spectrum says about the file, in words."""
    level, like = level_for(edge_hz)
    if info.lossless and level != FULL:
        return Verdict(level, tr("Sospechoso: no parece sin pérdida de verdad"), tr(
            "El formato no pierde calidad, pero el sonido se corta en seco a {0} kHz, como un archivo de unos "
            "{1}. Lo más probable es que se creara a partir de un MP3 u otro formato con pérdida. (Algunas "
            "grabaciones antiguas tienen pocos agudos de origen.)").format(_khz(edge_hz), like), suspicious=True)
    if info.lossless and info.sample_rate > HIRES_RATE and not hires_content:
        return Verdict(HIGH, tr("Sin pérdida, pero no de alta resolución real"), tr(
            "El archivo es de {0} kHz, pero no hay sonido por encima de unos 22 kHz: probablemente es un CD "
            "ampliado. Suena igual que a 44,1 kHz.").format(_khz(info.sample_rate)), suspicious=True)
    if info.lossless and info.sample_rate > HIRES_RATE:
        return Verdict(FULL, tr("Alta resolución auténtica"), tr(
            "Sin pérdida y con sonido más allá de lo que cabe en un CD."))
    if info.lossless:
        return Verdict(FULL, tr("Sin pérdida auténtico"), tr(
            "El sonido llega hasta arriba del todo, sin el corte que dejan los formatos con pérdida."))
    if level == FULL:
        return Verdict(HIGH, tr("Con pérdida, de muy buena calidad"), tr(
            "Formato con pérdida, pero conserva todos los agudos."))
    if info.bitrate >= INFLATED_KBPS and level in (LOW, POOR):
        return Verdict(level, tr("Sospechoso: el tamaño no corresponde al sonido"), tr(
            "El archivo es de {0} kbps, pero los agudos se cortan a {1} kHz, como en uno de unos {2}. "
            "Probablemente se volvió a comprimir desde un archivo de menos calidad.").format(
                info.bitrate, _khz(edge_hz), like), suspicious=True)
    titles = {HIGH: tr("Con pérdida, de buena calidad"), MEDIUM: tr("Con pérdida, calidad media"),
              LOW: tr("Con pérdida, calidad baja"), POOR: tr("Con pérdida, calidad muy baja")}
    return Verdict(level, titles[level], tr(
        "Los agudos se cortan a {0} kHz, lo normal en un archivo de unos {1}.").format(_khz(edge_hz), like))


# ------------------------------------------------------------ the picture
def palette() -> np.ndarray:
    """256 colours from silence to loud: black, blue, purple, red, yellow, white."""
    stops = np.array([[0, 0, 0], [0, 0, 110], [110, 0, 150], [210, 30, 60], [255, 150, 0], [255, 240, 120],
                      [255, 255, 255]], dtype=np.float64)
    at = np.linspace(0, len(stops) - 1, 256)
    low = np.minimum(at.astype(int), len(stops) - 2)
    part = (at - low)[:, None]
    return (stops[low] * (1 - part) + stops[low + 1] * part).astype(np.uint8)


def to_image(levels_db: np.ndarray) -> np.ndarray:
    """A spectrogram (rows = frequency from low to high, columns = time, in
    dB) as RGB bytes with the high frequencies at the top."""
    scaled = (np.clip(levels_db, FLOOR_DB, TOP_DB) - FLOOR_DB) / (TOP_DB - FLOOR_DB)
    return palette()[(scaled[::-1] * 255).astype(np.uint8)]


# --------------------------------------------------------------- analyse
@dataclass
class Analysis:
    info: AudioInfo
    verdict: Verdict
    edge_hz: float | None
    spectrogram_db: np.ndarray = field(repr=False)      # IMAGE_ROWS x columns
    spectrum_db: np.ndarray = field(repr=False)         # average level per frequency
    seconds: float = 0.0        # length of what was analysed


class Spectrum:
    """Builds the spectrogram and the average spectrum from samples as they
    arrive (mono, -1..1), keeping only the picture -- not the song."""

    def __init__(self, expected_frames: int):
        self.window = np.hanning(FFT_SIZE).astype(np.float32)
        self.scale = float(np.sum(self.window)) / 2          # a full-scale sine reads 0 dB
        self.group = max(1, -(-expected_frames // IMAGE_COLUMNS))     # frames per picture column
        self.columns: list[np.ndarray] = []
        self.column = np.zeros(FFT_SIZE // 2 + 1)
        self.in_column = 0
        self.total = np.zeros(FFT_SIZE // 2 + 1)
        self.frames = 0
        self.pending = np.zeros(0, dtype=np.float32)

    def feed(self, samples: np.ndarray):
        data = np.concatenate([self.pending, samples])
        count = (len(data) - FFT_SIZE) // HOP + 1 if len(data) >= FFT_SIZE else 0
        for i in range(count):
            frame = data[i * HOP:i * HOP + FFT_SIZE] * self.window
            power = (np.abs(np.fft.rfft(frame)) / self.scale) ** 2
            self.total += power
            self.frames += 1
            np.maximum(self.column, power, out=self.column)
            self.in_column += 1
            if self.in_column == self.group:
                self._close_column()
        self.pending = data[count * HOP:]

    def _close_column(self):
        self.columns.append(self.column)
        self.column = np.zeros(FFT_SIZE // 2 + 1)
        self.in_column = 0

    def result(self) -> tuple[np.ndarray, np.ndarray]:
        """(spectrogram in dB: IMAGE_ROWS x columns, average spectrum in dB)."""
        if self.in_column:
            self._close_column()
        if not self.columns:
            return np.full((IMAGE_ROWS, 1), FLOOR_DB), np.full(FFT_SIZE // 2 + 1, FLOOR_DB)
        power = np.stack(self.columns, axis=1)[1:]                     # drop the 0 Hz row
        per_row = power.shape[0] // IMAGE_ROWS
        rows = power[:per_row * IMAGE_ROWS].reshape(IMAGE_ROWS, per_row, -1).max(axis=1)
        return _db(rows), _db(self.total / max(1, self.frames))


def _db(power: np.ndarray) -> np.ndarray:
    return 10 * np.log10(np.maximum(power, 1e-14))


def probe(path: str) -> AudioInfo | None:
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-of", "json", "-show_format", "-show_streams", path],
                             capture_output=True, text=True, timeout=20).stdout
        return info_from_probe(json.loads(out))
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        log.info("ffprobe %s: %s", path, e)
        return None


def analyse(path: str, time_range: tuple[float, float] | None = None, cancelled=lambda: False) -> Analysis | None:
    """Spectrogram and verdict of an audio file (or of a stretch of it).
    Blocking: call it from a worker thread.  None when the file cannot be
    read or `cancelled()` became true."""
    info = probe(path)
    if info is None or info.sample_rate <= 0:
        return None
    start, end = time_range or (0.0, 0.0)
    seconds = (end or info.duration) - start
    command = ["ffmpeg", "-v", "error", "-nostdin"]
    if start:
        command += ["-ss", f"{start:.3f}"]
    if end:
        command += ["-to", f"{end:.3f}"]
    command += ["-i", path, "-map", "0:a:0", "-ac", "1", "-f", "f32le", "-"]
    spectrum = Spectrum(expected_frames=int(max(1.0, seconds) * info.sample_rate / HOP))
    try:
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as process:
            try:
                while chunk := process.stdout.read(4 * 65536):
                    if cancelled():
                        return None
                    spectrum.feed(np.frombuffer(chunk[:len(chunk) // 4 * 4], dtype=np.float32))
            finally:
                process.kill()          # also when cancelled or failing: never leave ffmpeg behind
    except OSError as e:
        log.info("ffmpeg %s: %s", path, e)
        return None
    if spectrum.frames == 0:
        return None
    picture, average = spectrum.result()
    edge = find_edge(average, info.sample_rate)
    hires = has_content_above(average, info.sample_rate, HIRES_CONTENT_HZ) if info.sample_rate > HIRES_RATE else False
    if info.sample_rate > HIRES_RATE and edge is not None and edge >= FULL_BAND_HZ and not hires:
        edge = None             # the top of a CD inside a hi-res file: told by the hi-res verdict
    return Analysis(info, judge(info, edge, hires), edge, picture, average, spectrum.frames * HOP / info.sample_rate)
