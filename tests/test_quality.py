"""Tests for the audio quality viewer: finding the cut a lossy encoder
leaves, the verdict, and real files made here with ffmpeg."""
# Never touch the real user settings/caches from tests.
import os as _os, tempfile as _tempfile  # noqa: E401
_ISO = _tempfile.mkdtemp(prefix="zebamp-test-home-")
_os.environ["ZEBAMP_TESTING"] = "1"
_os.environ["XDG_CONFIG_HOME"] = _os.path.join(_ISO, "config")
_os.environ["XDG_CACHE_HOME"] = _os.path.join(_ISO, "cache")
_os.environ["XDG_DATA_HOME"] = _os.path.join(_ISO, "data")

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np

from zebamp import audioquality as Q

RATE = 44100


def music_like(seconds=6.0, cut_hz=None, rate=RATE, seed=1):
    """Noise that falls 6 dB per octave like music does, optionally with
    everything above `cut_hz` removed the way a lossy encoder does."""
    rng = np.random.default_rng(seed)
    n = int(seconds * rate)
    spectrum = np.fft.rfft(rng.standard_normal(n))
    freqs = np.fft.rfftfreq(n, 1 / rate)
    spectrum /= np.maximum(freqs, 50.0)
    if cut_hz:
        spectrum[freqs > cut_hz] = 0
    signal = np.fft.irfft(spectrum, n)
    signal = signal / np.max(np.abs(signal)) * 0.5
    # like a 16-bit file: a faint noise floor everywhere
    return (signal + rng.standard_normal(n) * 1e-5).astype(np.float32)


def average_spectrum(samples, rate=RATE):
    spectrum = Q.Spectrum(expected_frames=len(samples) // Q.HOP)
    for i in range(0, len(samples), 30000):                 # in pieces, as ffmpeg delivers it
        spectrum.feed(samples[i:i + 30000])
    return spectrum.result()


class EdgeTest(unittest.TestCase):
    def test_full_band_sound_has_no_edge(self):
        _picture, average = average_spectrum(music_like())
        self.assertIsNone(Q.find_edge(average, RATE))

    def test_lossy_cuts_are_found_where_they_are(self):
        for cut in (16000, 19000, 20000):
            _picture, average = average_spectrum(music_like(cut_hz=cut))
            edge = Q.find_edge(average, RATE)
            self.assertIsNotNone(edge, cut)
            self.assertAlmostEqual(edge, cut, delta=450, msg=cut)

    def test_a_dip_in_the_middle_is_not_a_cut(self):
        samples = music_like()
        n = len(samples)
        spectrum = np.fft.rfft(samples)
        freqs = np.fft.rfftfreq(n, 1 / RATE)
        spectrum[(freqs > 12000) & (freqs < 13500)] = 0          # a notch: the sound comes back above
        _picture, average = average_spectrum(np.fft.irfft(spectrum, n).astype(np.float32))
        self.assertIsNone(Q.find_edge(average, RATE))

    def test_silence_and_odd_input(self):
        _picture, average = average_spectrum(np.zeros(RATE * 2, dtype=np.float32))
        self.assertIsNone(Q.find_edge(average, RATE))
        self.assertIsNone(Q.find_edge(np.zeros(10), RATE))
        self.assertIsNone(Q.find_edge(average, 0))

    def test_hi_res_content(self):
        rate = 96000
        _p, real = average_spectrum(music_like(4, rate=rate), rate)
        _p, upsampled = average_spectrum(music_like(4, cut_hz=21500, rate=rate), rate)
        self.assertTrue(Q.has_content_above(real, rate, 24000))
        self.assertFalse(Q.has_content_above(upsampled, rate, 24000))
        # like a vinyl rip at 192 kHz: sound fading gently to 35 kHz, then only a low noise floor
        rate = 192000
        _p, vinyl = average_spectrum(music_like(3, cut_hz=35000, rate=rate), rate)
        self.assertTrue(Q.has_content_above(vinyl, rate, 24000))


class SpectrumTest(unittest.TestCase):
    def test_a_full_scale_tone_reads_zero_db_at_its_frequency(self):
        t = np.arange(RATE * 3) / RATE
        picture, average = average_spectrum(np.sin(2 * np.pi * 5000 * t).astype(np.float32))
        self.assertEqual(picture.shape[0], Q.IMAGE_ROWS)
        self.assertLessEqual(picture.shape[1], Q.IMAGE_COLUMNS)
        hz_per_bin = RATE / 2 / (len(average) - 1)
        self.assertAlmostEqual(np.argmax(average) * hz_per_bin, 5000, delta=hz_per_bin * 1.5)
        self.assertAlmostEqual(float(np.max(average)), 0.0, delta=1.5)
        row = np.argmax(picture.max(axis=1)) * (RATE / 2 / Q.IMAGE_ROWS)
        self.assertAlmostEqual(row, 5000, delta=60)

    def test_long_songs_are_squeezed_into_the_same_width(self):
        spectrum = Q.Spectrum(expected_frames=9000)              # ten frames per column
        spectrum.feed(np.zeros(Q.HOP * 9001, dtype=np.float32))
        picture, _average = spectrum.result()
        self.assertEqual(picture.shape, (Q.IMAGE_ROWS, Q.IMAGE_COLUMNS))
        empty = Q.Spectrum(expected_frames=10).result()
        self.assertEqual(empty[0].shape, (Q.IMAGE_ROWS, 1))

    def test_picture_colours(self):
        levels = np.array([[Q.FLOOR_DB, Q.TOP_DB], [-500.0, 50.0]])
        image = Q.to_image(levels)
        self.assertEqual(image.shape, (2, 2, 3))
        self.assertEqual(image[1, 0].tolist(), [0, 0, 0])            # silence is black (and rows are flipped)
        self.assertEqual(image[1, 1].tolist(), [255, 255, 255])
        self.assertEqual(image[0, 0].tolist(), [0, 0, 0])            # out of range values are clamped
        self.assertEqual(Q.palette().shape, (256, 3))


class VerdictTest(unittest.TestCase):
    FLAC = Q.AudioInfo("flac", 44100, 16, 2, 900, 200)
    MP3 = Q.AudioInfo("mp3", 44100, 0, 2, 128, 200)

    def test_levels(self):
        self.assertEqual(Q.level_for(None), (Q.FULL, ""))
        self.assertEqual(Q.level_for(21500)[0], Q.FULL)
        self.assertEqual(Q.level_for(20000), (Q.HIGH, "256–320 kbps"))
        self.assertEqual(Q.level_for(19000)[0], Q.HIGH)
        self.assertEqual(Q.level_for(18000), (Q.MEDIUM, "192 kbps"))
        self.assertEqual(Q.level_for(16000), (Q.LOW, "128 kbps"))
        self.assertEqual(Q.level_for(11000)[0], Q.POOR)

    def test_true_lossless(self):
        verdict = Q.judge(self.FLAC, None, False)
        self.assertEqual((verdict.level, verdict.title, verdict.suspicious), (Q.FULL, "Sin pérdida auténtico", False))

    def test_flac_made_from_an_mp3_is_called_out(self):
        verdict = Q.judge(self.FLAC, 16000.0, False)
        self.assertTrue(verdict.suspicious)
        self.assertEqual(verdict.level, Q.LOW)
        self.assertIn("16,0 kHz", verdict.detail)
        self.assertIn("128 kbps", verdict.detail)

    def test_lossy_files_are_graded_not_accused(self):
        low = Q.judge(self.MP3, 16000.0, False)
        self.assertEqual((low.level, low.title, low.suspicious), (Q.LOW, "Con pérdida, calidad baja", False))
        self.assertEqual(Q.judge(self.MP3, 20000.0, False).title, "Con pérdida, de buena calidad")
        self.assertEqual(Q.judge(self.MP3, None, False).title, "Con pérdida, de muy buena calidad")

    def test_a_big_lossy_file_that_sounds_small_is_called_out(self):
        inflated = Q.judge(Q.AudioInfo("mp3", 48000, 0, 2, 320, 200), 15800.0, False)
        self.assertTrue(inflated.suspicious)
        self.assertIn("320 kbps", inflated.detail)
        self.assertIn("15,8 kHz", inflated.detail)
        self.assertFalse(Q.judge(Q.AudioInfo("mp3", 44100, 0, 2, 320, 200), 20000.0, False).suspicious)
        self.assertFalse(Q.judge(Q.AudioInfo("mp3", 44100, 0, 2, 128, 200), 15800.0, False).suspicious)

    def test_hi_res(self):
        hires = Q.AudioInfo("flac", 96000, 24, 2, 2800, 200)
        self.assertEqual(Q.judge(hires, None, True).title, "Alta resolución auténtica")
        fake = Q.judge(hires, None, False)
        self.assertTrue(fake.suspicious)
        self.assertIn("96,0 kHz", fake.detail)
        self.assertTrue(Q.AudioInfo("pcm_s16le").lossless)
        self.assertFalse(Q.AudioInfo("vorbis").lossless)


class FilesTest(unittest.TestCase):
    def test_ffprobe_answers(self):
        probe = {"streams": [{"codec_type": "video"},
                             {"codec_type": "audio", "codec_name": "flac", "sample_rate": "44100", "channels": 2,
                              "bits_per_raw_sample": "16", "duration": "200.5"}],
                 "format": {"bit_rate": "912345"}}
        info = Q.info_from_probe(probe)
        self.assertEqual((info.codec, info.sample_rate, info.bits, info.channels, info.bitrate, info.duration),
                         ("flac", 44100, 16, 2, 912, 200.5))
        self.assertIsNone(Q.info_from_probe({"streams": [{"codec_type": "video"}]}))
        for odd in ({}, {"streams": "x"}, None, {"streams": [3]}):
            self.assertIsNone(Q.info_from_probe(odd))
        loose = Q.info_from_probe({"streams": [{"codec_type": "audio", "sample_rate": "x", "duration": "x"}],
                                   "format": "x"})
        self.assertEqual((loose.sample_rate, loose.duration), (0, 0.0))

    def test_cue_sheets(self):
        self.assertEqual(Q.cue_audio_file('PERFORMER "B"\nFILE "Banda - Disco.flac" WAVE\n  TRACK 01 AUDIO\n'),
                         "Banda - Disco.flac")
        self.assertEqual(Q.cue_audio_file("TITLE x"), "")
        self.assertEqual(Q.song_range({"range": "12.5-200.25"}), (12.5, 200.25))
        self.assertEqual(Q.song_range({"range": "300.0-"}), (300.0, 0))
        self.assertIsNone(Q.song_range({}))
        self.assertIsNone(Q.song_range({"range": "x-y"}))
        folder = tempfile.mkdtemp(prefix="zebamp-cue-")
        os.makedirs(os.path.join(folder, "Rock"))
        for name, text in (("Rock/Disco.cue", 'FILE "Disco.flac" WAVE\n'), ("Rock/Disco.flac", "audio"),
                           ("Rock/roto.cue", 'FILE "falta.flac" WAVE\n'), ("suelta.mp3", "audio")):
            with open(os.path.join(folder, name), "w") as fh:
                fh.write(text)
        self.assertEqual(Q.audio_file_of({"file": "Rock/Disco.cue/track0003"}, folder),
                         os.path.join(folder, "Rock", "Disco.flac"))
        self.assertEqual(Q.audio_file_of({"file": "suelta.mp3"}, folder), os.path.join(folder, "suelta.mp3"))
        self.assertIsNone(Q.audio_file_of({"file": "Rock/roto.cue/track0001"}, folder))
        self.assertIsNone(Q.audio_file_of({"file": "Rock/no.cue/track0001"}, folder))
        self.assertIsNone(Q.audio_file_of({"file": "suelta.mp3"}, None))
        self.assertIsNone(Q.audio_file_of({"file": "http://radio/x"}, folder))


class ScalesTest(unittest.TestCase):
    def test_frequency_and_time_ticks(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from zebamp.ui.quality import frequency_ticks, info_line, time_ticks
        self.assertEqual(frequency_ticks(22050), [0, 2000, 4000, 6000, 8000, 10000, 12000, 14000, 16000, 18000,
                                                  20000, 22000])
        self.assertEqual(frequency_ticks(48000), [0, 5000, 10000, 15000, 20000, 25000, 30000, 35000, 40000, 45000])
        self.assertEqual(time_ticks(8), [0, 5])
        self.assertEqual(time_ticks(215), [0, 30, 60, 90, 120, 150, 180, 210])
        self.assertEqual(time_ticks(0), [])
        self.assertEqual(len(time_ticks(4 * 3600)), 17)              # a very long file still gets a readable scale
        self.assertEqual(info_line(Q.AudioInfo("flac", 44100, 16, 2, 912, 200)),
                         "FLAC · 44,1 kHz · 16 bits · estéreo · 912 kbps")
        self.assertEqual(info_line(Q.AudioInfo("mp3", 48000, 0, 1, 128, 200)), "MP3 · 48 kHz · mono · 128 kbps")
        self.assertEqual(info_line(Q.AudioInfo("pcm_s16le", 0, 0, 6, 0, 0)), "PCM S16LE · 6 canales")


@unittest.skipUnless(Q.available(), "ffmpeg not installed")
class RealFilesTest(unittest.TestCase):
    """Files encoded here: a true FLAC, an MP3 and a FLAC made from that MP3."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="zebamp-quality-")
        import wave
        samples = (music_like(8.0) * 32767).astype("<i2")
        with wave.open(os.path.join(cls.dir, "original.wav"), "wb") as fh:
            fh.setnchannels(1)
            fh.setsampwidth(2)
            fh.setframerate(RATE)
            fh.writeframes(samples.tobytes())

        def ffmpeg(*args):
            subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True, cwd=cls.dir)
        ffmpeg("-i", "original.wav", "verdadero.flac")
        encoders = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
        cls.has_mp3 = "libmp3lame" in encoders
        if cls.has_mp3:
            # mono at 64 kbps is what 128 kbps is for stereo: LAME cuts at about 16 kHz
            ffmpeg("-i", "original.wav", "-c:a", "libmp3lame", "-b:a", "64k", "con-perdida.mp3")
            ffmpeg("-i", "con-perdida.mp3", "falso.flac")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def path(self, name):
        return os.path.join(self.dir, name)

    def test_true_flac(self):
        result = Q.analyse(self.path("verdadero.flac"))
        self.assertEqual((result.info.codec, result.info.sample_rate, result.info.bits), ("flac", 44100, 16))
        self.assertIsNone(result.edge_hz)
        self.assertEqual(result.verdict.title, "Sin pérdida auténtico")
        self.assertEqual(result.spectrogram_db.shape[0], Q.IMAGE_ROWS)
        self.assertAlmostEqual(result.seconds, 8.0, delta=0.3)

    def test_mp3_and_the_flac_made_from_it(self):
        if not self.has_mp3:
            self.skipTest("ffmpeg without an MP3 encoder")
        lossy = Q.analyse(self.path("con-perdida.mp3"))
        self.assertFalse(lossy.info.lossless)
        self.assertIsNotNone(lossy.edge_hz)
        self.assertLess(lossy.edge_hz, 17500)
        self.assertIn("Con pérdida", lossy.verdict.title)
        fake = Q.analyse(self.path("falso.flac"))
        self.assertTrue(fake.info.lossless)
        self.assertTrue(fake.verdict.suspicious)
        self.assertAlmostEqual(fake.edge_hz, lossy.edge_hz, delta=600)

    def test_a_stretch_of_a_file_cancelling_and_bad_files(self):
        part = Q.analyse(self.path("verdadero.flac"), (2.0, 5.0))
        self.assertAlmostEqual(part.seconds, 3.0, delta=0.3)
        self.assertIsNone(Q.analyse(self.path("verdadero.flac"), cancelled=lambda: True))
        self.assertIsNone(Q.analyse(self.path("no-existe.flac")))
        with open(self.path("texto.flac"), "w") as fh:
            fh.write("esto no es audio")
        self.assertIsNone(Q.analyse(self.path("texto.flac")))


if __name__ == "__main__":
    unittest.main()
