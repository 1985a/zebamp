"""Tests for covers from the Internet: matching, reading the services'
answers, the search order and the cache.  No test touches the network."""
# Never touch the real user settings/caches from tests.
import os as _os, tempfile as _tempfile  # noqa: E401
_ISO = _tempfile.mkdtemp(prefix="zebamp-test-home-")
_os.environ["ZEBAMP_TESTING"] = "1"
_os.environ["XDG_CONFIG_HOME"] = _os.path.join(_ISO, "config")
_os.environ["XDG_CACHE_HOME"] = _os.path.join(_ISO, "cache")
_os.environ["XDG_DATA_HOME"] = _os.path.join(_ISO, "data")

import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from zebamp import coverfind as C

SONG = {"file": "a/01.flac", "artist": "Los Píxeles", "albumartist": "Los Píxeles", "album": "Noches de neón",
        "title": "Lluvia sobre el asfalto", "date": "2024-03-01", "duration": "217.4"}
PICTURE = b"PICTURE"


def is_image(data):
    return data == PICTURE


def album(source, ident, title, artist, year="", images=("https://img/x",)):
    return C.Candidate(source, ident, title, artist, year, images=list(images))


class CleanNamesTest(unittest.TestCase):
    def test_editions_accents_and_punctuation_do_not_matter(self):
        self.assertEqual(C.clean("Noches de Neón (Deluxe Edition)"), "noches de neon")
        self.assertEqual(C.clean("Noches de neón [2011 Remaster]"), "noches de neon")
        self.assertEqual(C.clean("Noches de neón - Remastered 2011"), "noches de neon")
        self.assertEqual(C.clean("Rock & Roll!"), "rock and roll")
        self.assertEqual(C.clean("Uno (y dos)"), "uno y dos")           # ordinary brackets are part of the name
        self.assertEqual(C.clean(None), "")

    def test_main_artist(self):
        self.assertEqual(C.clean_artist("The Píxeles feat. Ana"), "pixeles")
        self.assertEqual(C.clean_artist("Los Píxeles con Bea"), "los pixeles")
        self.assertEqual(C.clean_artist("AC/DC"), "ac dc")

    def test_similarity(self):
        self.assertEqual(C.similarity("noches de neon", "noches de neon"), 1.0)
        self.assertGreater(C.similarity("noches de neon", "noche de neon"), 0.9)
        self.assertLess(C.similarity("noches de neon", "dias de sol"), 0.6)
        self.assertEqual(C.similarity("", "x"), 0.0)

    def test_artist_names_with_additions_still_match(self):
        self.assertEqual(C.artist_similarity("juan luis guerra", "juan luis guerra 4 40"), 0.9)
        self.assertEqual(C.artist_similarity("queen adam lambert", "queen"), 0.9)
        self.assertLess(C.artist_similarity("guerra", "juan luis guerra"), 0.8)       # not the start of the name
        self.assertLess(C.artist_similarity("queens of the stone age", "queen"), 0.8)  # a word, not a prefix
        q = C.Query(artist="Juan Luis Guerra", album="Bachata Rosa")
        self.assertGreater(C.album_score(q, album("x", "1", "Bachata Rosa", "Juan Luis Guerra 4.40")), 0.9)

    def test_searches_leave_out_edition_notes(self):
        self.assertEqual(C.search_name("Nevermind (Remastered)"), "Nevermind")
        self.assertEqual(C.search_name("Noches de Neón [Deluxe Edition] - 2011 Remaster"), "Noches de Neón")
        self.assertEqual(C.search_name("Uno (y dos)"), "Uno (y dos)")
        self.assertEqual(C.search_name("(Remastered)"), "(Remastered)")               # never an empty search
        remastered = C.Query(artist="Nirvana", album="Nevermind (Remastered)")
        self.assertIn("Nevermind%22", C.musicbrainz_album_url(remastered))
        deluxe = C.Query(artist="Nirvana", album="Nevermind [Deluxe]")
        self.assertIn("q=Nirvana+Nevermind&", C.deezer_album_url(deluxe))

    def test_a_different_number_is_a_different_thing(self):
        self.assertEqual(C.similarity("exitos del verano 2001", "exitos del verano 2002"), 0.0)
        self.assertEqual(C.similarity("grandes exitos vol 1", "grandes exitos vol 2"), 0.0)
        self.assertEqual(C.similarity("grandes exitos ii", "grandes exitos iii"), 0.0)
        self.assertEqual(C.similarity("grandes exitos", "grandes exitos 2"), 0.0)
        self.assertGreater(C.similarity("grandes exitos vol 2", "grandes exitos volumen 2"), 0.85)


class QueryTest(unittest.TestCase):
    def test_from_song(self):
        q = C.query_from_song({**SONG, "musicbrainz_albumid": "abc", "artist": ["Los Píxeles", "Otro"]})
        self.assertEqual((q.artist, q.album, q.title, q.year, q.release_id), ("Los Píxeles", "Noches de neón",
                                                                             "Lluvia sobre el asfalto", "2024", "abc"))
        self.assertAlmostEqual(q.duration, 217.4)
        self.assertIsNone(C.query_from_song({**SONG, "file": "http://radio/stream"}))
        self.assertIsNone(C.query_from_song({"file": "x.mp3"}))                       # no tags at all
        self.assertIsNone(C.query_from_song({"file": "x.mp3", "artist": "Ana"}))      # nothing to look for
        self.assertIsNotNone(C.query_from_song({"file": "x.mp3", "artist": "Ana", "title": "Uno", "duration": "x"}))
        self.assertIsNotNone(C.query_from_song({"file": "x.mp3", "musicbrainz_albumid": "abc"}))

    def test_all_songs_of_an_album_share_one_cache_key(self):
        a = C.query_from_song(SONG)
        b = C.query_from_song({**SONG, "file": "a/02.flac", "title": "Otra", "album": "NOCHES DE NEON (Deluxe)"})
        other = C.query_from_song({**SONG, "album": "Otro disco"})
        self.assertEqual(a.key(), b.key())
        self.assertNotEqual(a.key(), other.key())


class ScoreTest(unittest.TestCase):
    def setUp(self):
        self.q = C.query_from_song(SONG)

    def test_only_the_same_album_by_the_same_artist_is_accepted(self):
        self.assertGreater(C.album_score(self.q, album("x", "1", "Noches de Neón", "Los Pixeles")), 0.99)
        self.assertGreater(C.album_score(self.q, album("x", "1", "Noches de neón (Deluxe)", "Los Píxeles")), 0.99)
        self.assertEqual(C.album_score(self.q, album("x", "2", "Noches de neón", "Otra Banda")), 0)      # homonym
        self.assertEqual(C.album_score(self.q, album("x", "3", "Días de sol", "Los Píxeles")), 0)        # other album
        self.assertEqual(C.album_score(self.q, album("x", "4", "Noches", "Los Píxeles")), 0)             # only similar

    def test_ranking_prefers_the_same_year_and_skips_rejected_and_pictureless(self):
        cands = [album("x", "old", "Noches de neón", "Los Píxeles", "1999"),
                 album("x", "right", "Noches de neón", "Los Píxeles", "2024"),
                 album("x", "nopic", "Noches de neón", "Los Píxeles", "2024", images=()),
                 album("x", "wrong", "Algo distinto", "Los Píxeles")]
        self.assertEqual([c.ident for c in C.ranked(self.q, cands)], ["right", "old"])
        self.assertEqual([c.ident for c in C.ranked(self.q, cands, rejected=["right"])], ["old"])

    def test_compilations_match_on_the_title_alone_but_strictly(self):
        q = C.Query(artist="Various Artists", album="Éxitos del verano 2001")
        self.assertGreater(C.album_score(q, album("x", "1", "Exitos del Verano 2001", "Varios Artistas")), 0.9)
        self.assertGreater(C.album_score(q, album("x", "1", "Éxitos del verano 2001", "Sello X")), 0.9)
        self.assertEqual(C.album_score(q, album("x", "2", "Éxitos del verano 2002", "Various Artists")), 0)

    def test_single_songs_need_title_artist_and_about_the_same_length(self):
        q = C.Query(artist="Los Píxeles", title="Lluvia sobre el asfalto", duration=217)
        def track(title, artist, seconds):
            return C.Candidate("x", "1", title, artist, duration=seconds, images=["https://img/x"])
        self.assertGreater(C.track_score(q, track("Lluvia sobre el asfalto", "Los Píxeles", 219)), 0.99)
        self.assertEqual(C.track_score(q, track("Lluvia sobre el asfalto", "Los Píxeles", 301)), 0)     # live take
        self.assertEqual(C.track_score(q, track("Lluvia sobre el asfalto", "Otros", 217)), 0)
        self.assertGreater(C.track_score(q, track("Lluvia sobre el asfalto", "Los Píxeles", 0)), 0.99)  # no length


class ReadAnswersTest(unittest.TestCase):
    """Remote data is never trusted: odd shapes give no candidates, not errors."""

    def test_musicbrainz_albums(self):
        answer = {"releases": [
            {"id": "r1", "title": "Noches de neón", "date": "2024-03-01", "release-group": {"id": "g1"},
             "artist-credit": [{"name": "Los Píxeles", "joinphrase": " & "}, {"name": "Ana"}]},
            {"title": "sin id"}, "texto", None]}
        got = C.musicbrainz_albums(answer)
        self.assertEqual(len(got), 1)
        self.assertEqual((got[0].ident, got[0].title, got[0].artist, got[0].year), ("mb:r1", "Noches de neón",
                                                                                    "Los Píxeles & Ana", "2024"))
        self.assertEqual(got[0].images, ["https://coverartarchive.org/release/r1/front-500",
                                         "https://coverartarchive.org/release-group/g1/front-500"])
        for bad in ({}, {"releases": "x"}, {"releases": [{"id": "r", "artist-credit": "x", "release-group": 3}]}):
            C.musicbrainz_albums(bad)

    def test_musicbrainz_tracks_take_the_album_release(self):
        answer = {"recordings": [{"title": "Lluvia sobre el asfalto", "length": 217000,
                                  "artist-credit": [{"name": "Los Píxeles"}],
                                  "releases": [{"id": "single", "date": "2023",
                                                "release-group": {"primary-type": "Single"}},
                                               {"id": "album", "date": "2024",
                                                "release-group": {"primary-type": "Album", "id": "g"}}]},
                                 {"title": "sin lanzamientos", "length": "x"}, 7]}
        got = C.musicbrainz_tracks(answer)
        self.assertEqual([(c.ident, c.duration) for c in got], [("mb:album", 217.0)])

    def test_deezer(self):
        answer = {"data": [{"id": 5, "title": "Noches de neón", "artist": {"name": "Los Píxeles"},
                            "cover_xl": "https://cdn/images/cover/abc/1000x1000.jpg"},
                           {"id": 6, "title": "Sin arte", "artist": {"name": "X"},
                            "cover_xl": "https://cdn/images/cover//1000x1000.jpg"},      # placeholder
                           {"id": 7, "title": "http", "artist": None, "cover_xl": "http://inseguro/x.jpg"}, "x"]}
        got = C.deezer_albums(answer)
        self.assertEqual([(c.ident, bool(c.images)) for c in got], [("deezer:5", True), ("deezer:6", False),
                                                                   ("deezer:7", False)])
        tracks = C.deezer_tracks({"data": [{"title": "Lluvia", "duration": 217, "artist": {"name": "Los Píxeles"},
                                            "album": {"id": 5, "cover_xl": "https://cdn/images/cover/abc/x.jpg"}},
                                           {"title": "roto", "duration": "x", "album": "no"}]})
        self.assertEqual([(c.ident, c.duration, bool(c.images)) for c in tracks],
                         [("deezer:5", 217.0, True), ("deezer:None", 0.0, False)])
        self.assertEqual(C.deezer_albums({"data": None}), [])

    def test_itunes_asks_for_a_bigger_picture(self):
        answer = {"results": [{"collectionId": 9, "collectionName": "Noches de neón", "artistName": "Los Píxeles",
                               "releaseDate": "2024-03-01T00:00:00Z",
                               "artworkUrl100": "https://is1.example/a/100x100bb.jpg"}, {"collectionId": 10}]}
        got = C.itunes_albums(answer)
        self.assertEqual((got[0].year, got[0].images), ("2024", ["https://is1.example/a/600x600bb.jpg"]))
        self.assertEqual(got[1].images, [])
        songs = C.itunes_tracks({"results": [{"collectionId": 9, "trackName": "Lluvia", "artistName": "Los Píxeles",
                                              "trackTimeMillis": 217000,
                                              "artworkUrl100": "https://is1.example/a/100x100bb.jpg"}]})
        self.assertEqual(songs[0].duration, 217.0)

    def test_search_addresses_quote_what_the_user_has(self):
        q = C.Query(artist='Los "Píxeles"', album="Noches \\ de neón")
        url = C.musicbrainz_album_url(q)
        self.assertIn("release%3A%22Noches+++de+ne%C3%B3n%22", url)
        self.assertIn("artist%3A%22Los++P%C3%ADxeles+%22", url)
        self.assertNotIn("artist", C.musicbrainz_album_url(C.Query(artist="Various Artists", album="X")))
        self.assertTrue(C.deezer_album_url(q).startswith("https://api.deezer.com/search/album?q="))
        self.assertIn("entity=song", C.itunes_track_url(C.Query(artist="A", title="T")))


class FakeWeb:
    """Stands in for the three services: records what is asked."""

    def __init__(self, answers=None, pictures=None, down=()):
        self.answers = answers or {}        # host fragment -> JSON answer
        self.pictures = pictures or {}      # URL -> bytes
        self.down = down                    # host fragments that cannot be reached
        self.asked = []

    def _check(self, url):
        self.asked.append(url)
        if any(host in url for host in self.down):
            raise OSError("unreachable")

    def get_json(self, url):
        self._check(url)
        return next((a for host, a in self.answers.items() if host in url), {})

    def get_image(self, url):
        self._check(url)
        return self.pictures.get(url)

    def hosts(self):
        return [u.split("/")[2] for u in self.asked]


MB_ALBUM = {"releases": [{"id": "r1", "title": "Noches de neón", "date": "2024",
                          "artist-credit": [{"name": "Los Píxeles"}]}]}
DEEZER_ALBUM = {"data": [{"id": 5, "title": "Noches de neón", "artist": {"name": "Los Píxeles"},
                          "cover_xl": "https://cdn/images/cover/abc/1000.jpg"}]}
ARCHIVE_R1 = "https://coverartarchive.org/release/r1/front-500"
DEEZER_PICTURE = "https://cdn/images/cover/abc/1000.jpg"


class FindCoverTest(unittest.TestCase):
    def find(self, web, song=SONG, rejected=()):
        return C.find_cover(C.query_from_song(song), is_image, rejected, web.get_json, web.get_image)

    def test_the_id_in_the_tags_is_used_first_and_nothing_else_is_asked(self):
        url = "https://coverartarchive.org/release/tagged/front-500"
        web = FakeWeb(pictures={url: PICTURE})
        found = self.find(web, {**SONG, "musicbrainz_albumid": "tagged"})
        self.assertEqual((found.source, found.ident), ("MusicBrainz", "mb:tagged"))
        self.assertEqual(web.asked, [url])

    def test_musicbrainz_then_deezer_then_itunes(self):
        web = FakeWeb({"musicbrainz": MB_ALBUM}, {ARCHIVE_R1: PICTURE})
        self.assertEqual(self.find(web).ident, "mb:r1")
        self.assertEqual(web.hosts(), ["musicbrainz.org", "coverartarchive.org"])
        # MusicBrainz knows the album but the archive has no picture: go on to Deezer
        web = FakeWeb({"musicbrainz": MB_ALBUM, "deezer": DEEZER_ALBUM}, {DEEZER_PICTURE: PICTURE})
        self.assertEqual(self.find(web).source, "Deezer")
        self.assertEqual(web.hosts(), ["musicbrainz.org", "coverartarchive.org", "api.deezer.com", "cdn"])

    def test_a_wrong_album_is_never_returned(self):
        wrong = {"releases": [{"id": "x", "title": "Noches de neón", "artist-credit": [{"name": "Otra Banda"}]}],
                 "data": [{"id": 1, "title": "Días de sol", "artist": {"name": "Los Píxeles"},
                           "cover_xl": "https://cdn/images/cover/zzz/1000.jpg"}], "results": []}
        web = FakeWeb({"musicbrainz": wrong, "deezer": wrong, "itunes": wrong},
                      {"https://cdn/images/cover/zzz/1000.jpg": PICTURE,
                       "https://coverartarchive.org/release/x/front-500": PICTURE})
        self.assertIsNone(self.find(web))
        self.assertFalse([u for u in web.asked if "front-500" in u or "cdn" in u])     # no picture even downloaded

    def test_a_download_that_is_not_a_picture_is_skipped(self):
        web = FakeWeb({"musicbrainz": MB_ALBUM, "deezer": DEEZER_ALBUM},
                      {ARCHIVE_R1: b"<html>error</html>", "https://cdn/images/cover/abc/1000.jpg": PICTURE})
        self.assertEqual(self.find(web).source, "Deezer")

    def test_rejected_candidates_are_not_offered_again(self):
        web = FakeWeb({"musicbrainz": MB_ALBUM, "deezer": DEEZER_ALBUM},
                      {ARCHIVE_R1: PICTURE, "https://cdn/images/cover/abc/1000.jpg": PICTURE})
        self.assertEqual(self.find(web, rejected=["mb:r1"]).ident, "deezer:5")
        self.assertIsNone(self.find(web, rejected=["mb:r1", "deezer:5"]))

    def test_one_service_down_is_skipped_but_all_down_is_not_a_miss(self):
        web = FakeWeb({"deezer": DEEZER_ALBUM}, {DEEZER_PICTURE: PICTURE}, down=["musicbrainz"])
        self.assertEqual(self.find(web).source, "Deezer")
        offline = FakeWeb(down=["musicbrainz", "deezer", "itunes"])
        with self.assertRaises(C.Unreachable):
            self.find(offline)

    def test_songs_without_album_are_looked_up_by_title_and_length(self):
        song = {"file": "x.mp3", "artist": "Los Píxeles", "title": "Lluvia sobre el asfalto", "duration": "217"}
        tracks = {"data": [{"title": "Lluvia sobre el asfalto", "duration": 305, "artist": {"name": "Los Píxeles"},
                            "album": {"id": 1, "cover_xl": "https://cdn/images/cover/live/1000.jpg"}},
                           {"title": "Lluvia sobre el asfalto", "duration": 218, "artist": {"name": "Los Píxeles"},
                            "album": {"id": 2, "cover_xl": "https://cdn/images/cover/studio/1000.jpg"}}]}
        web = FakeWeb({"deezer": tracks}, {"https://cdn/images/cover/live/1000.jpg": PICTURE,
                                           "https://cdn/images/cover/studio/1000.jpg": PICTURE})
        self.assertEqual(self.find(web, song).ident, "deezer:2")
        self.assertIn("recording", web.asked[0])


class CacheTest(unittest.TestCase):
    def setUp(self):
        self.cache = C.CoverCache(tempfile.mkdtemp(prefix="zebamp-covers-"))
        self.web = FakeWeb({"musicbrainz": MB_ALBUM, "deezer": DEEZER_ALBUM},
                           {ARCHIVE_R1: PICTURE, "https://cdn/images/cover/abc/1000.jpg": PICTURE})

    def cover(self, song=SONG, force=False, web=None):
        web = web or self.web
        return C.online_cover(song, is_image, self.cache, force, web.get_json, web.get_image)

    def test_found_once_then_served_from_disk_for_the_whole_album(self):
        path = self.cover()
        with open(path, "rb") as fh:
            self.assertEqual(fh.read(), PICTURE)
        asked = len(self.web.asked)
        self.assertEqual(self.cover({**SONG, "file": "a/02.flac", "title": "Otra"}), path)
        self.assertEqual(len(self.web.asked), asked)                 # no new request

    def test_not_found_is_remembered_for_a_week_unless_forced(self):
        empty = FakeWeb()
        self.assertIsNone(self.cover(web=empty))
        asked = len(empty.asked)
        self.assertIsNone(self.cover(web=empty))
        self.assertEqual(len(empty.asked), asked)                    # did not ask again
        query = C.query_from_song(SONG)
        self.assertFalse(self.cache.should_search(query))
        self.assertTrue(self.cache.should_search(query, now=time.time() + C.NOT_FOUND_RETRY + 5))
        self.assertIsNotNone(self.cover(force=True))                 # "search again" ignores the wait

    def test_offline_is_not_remembered_as_not_found(self):
        offline = FakeWeb(down=["musicbrainz", "deezer", "itunes"])
        self.assertIsNone(self.cover(web=offline))
        self.assertTrue(self.cache.should_search(C.query_from_song(SONG)))
        self.assertIsNotNone(self.cover())

    def test_rejecting_a_wrong_cover_moves_on_to_the_next_candidate(self):
        query = C.query_from_song(SONG)
        self.cover()
        self.assertEqual(self.cache.meta(query)["ident"], "mb:r1")
        self.cache.reject(query)
        self.assertFalse(self.cache.has_image(query))
        self.cover()
        self.assertEqual(self.cache.meta(query)["ident"], "deezer:5")
        self.cache.reject(query, give_up=True)                       # "no cover for this album"
        self.assertIsNone(self.cover())
        self.assertEqual(self.cache.rejected(query), ["mb:r1", "deezer:5"])
        self.cache.forget(query)                                     # start over
        self.assertEqual(self.cache.meta(query), {})
        self.assertIsNotNone(self.cover())

    def test_damaged_cache_files_and_untagged_songs(self):
        query = C.query_from_song(SONG)
        os.makedirs(self.cache.directory, exist_ok=True)
        with open(self.cache._meta_path(query), "w") as fh:
            fh.write("[not, a, dict")
        self.assertEqual(self.cache.meta(query), {})
        self.assertIsNotNone(self.cover())
        self.assertIsNone(self.cover({"file": "sin-etiquetas.mp3"}))
        self.assertIsNone(self.cover({**SONG, "file": "http://radio/x"}))


class MusicBrainzPaceTest(unittest.TestCase):
    def test_requests_are_spaced_and_a_busy_answer_is_retried_once(self):
        from unittest import mock
        calls = []

        def busy_then_fine(url, limit):
            calls.append(time.monotonic())
            if len(calls) == 1:
                raise OSError("HTTP 503")
            return b"{}"
        with mock.patch.object(C, "_get", busy_then_fine), mock.patch.object(C, "MUSICBRAINZ_PAUSE", 0.05):
            self.assertEqual(C._open(C.MUSICBRAINZ + "/release?query=x", 100), b"{}")
            self.assertEqual(len(calls), 2)
            self.assertGreaterEqual(calls[1] - calls[0], 0.05)
        always_busy = mock.patch.object(C, "_get", side_effect=OSError("HTTP 503"))
        with always_busy, mock.patch.object(C, "MUSICBRAINZ_PAUSE", 0), self.assertRaises(OSError):
            C._open(C.MUSICBRAINZ + "/release?query=x", 100)     # still busy: the next service is asked


class NetworkGuardTest(unittest.TestCase):
    def test_only_https_addresses_are_opened(self):
        self.assertIsNone(C._open("file:///etc/passwd", 100))
        self.assertIsNone(C._open("http://example.invalid/x.jpg", 100))
        self.assertEqual(C.fetch_json("ftp://x"), {})


from zebamp import songid as S

ANSWER = {"status": "ok", "results": [
    {"id": "low", "score": 0.4, "recordings": [{"id": "x", "title": "Otra", "artists": [{"name": "Otros"}]}]},
    {"id": "top", "score": 0.97, "recordings": [
        {"id": "live", "title": "Lluvia sobre el asfalto", "duration": 301, "artists": [{"name": "Los Píxeles"}],
         "releasegroups": [{"id": "g-live", "title": "En directo", "type": "Album", "secondarytypes": ["Live"]}]},
        {"id": "studio", "title": "Lluvia sobre el asfalto", "duration": 217,
         "artists": [{"name": "Los Píxeles", "joinphrase": " & "}, {"name": "Ana"}],
         "releasegroups": [{"id": "g-comp", "title": "Lo mejor", "type": "Album", "secondarytypes": ["Compilation"]},
                           {"id": "g-single", "title": "Lluvia", "type": "Single"},
                           {"id": "g-album", "title": "Noches de neón", "type": "Album"}]},
        {"id": "untitled", "duration": 217}]}]}


class SongNamesTest(unittest.TestCase):
    def test_file_name_fills_only_what_the_tags_lack(self):
        got = S.names_from_file({"file": "MUSIC/otras/Los Píxeles - Lluvia sobre el asfalto.mp3"})
        self.assertEqual((got["artist"], got["title"]), ("Los Píxeles", "Lluvia sobre el asfalto"))
        tagged = {"file": "x/Otro - Nombre.mp3", "artist": "Ana", "title": "Uno"}
        self.assertEqual(S.names_from_file(tagged), tagged)
        half = S.names_from_file({"file": "x/07 - Banda - Tema.mp3", "title": "Tema real"})
        self.assertEqual((half["artist"], half["title"]), ("Banda", "Tema real"))
        stream = {"file": "http://radio/Artist - Song.mp3"}
        self.assertEqual(S.names_from_file(stream), stream)

    def test_has_names(self):
        self.assertTrue(S.has_names({"artist": "Ana", "title": "Uno"}))
        self.assertTrue(S.has_names({"albumartist": ["Ana"], "album": "Disco"}))
        self.assertFalse(S.has_names({"title": "Uno"}))
        self.assertFalse(S.has_names({"artist": "Ana"}))
        self.assertFalse(S.has_names({"file": "x.mp3"}))

    def test_cover_search_uses_the_file_name_when_there_are_no_tags(self):
        song = S.described({"file": "otras/Los Píxeles - Lluvia sobre el asfalto.mp3", "duration": "217"})
        query = C.query_from_song(song)
        self.assertEqual((query.artist, query.title, query.album), ("Los Píxeles", "Lluvia sobre el asfalto", ""))


class AcoustIdAnswerTest(unittest.TestCase):
    def test_best_result_recording_of_our_length_and_its_studio_album(self):
        got = S.best_match(ANSWER, duration=218)
        self.assertEqual((got.artist, got.title, got.album, got.group_id, got.recording_id),
                         ("Los Píxeles & Ana", "Lluvia sobre el asfalto", "Noches de neón", "g-album", "studio"))
        self.assertEqual(S.best_match(ANSWER, duration=300).album, "En directo")       # we have the live take
        self.assertEqual(got.as_tags(), {"artist": "Los Píxeles & Ana", "title": "Lluvia sobre el asfalto",
                                         "album": "Noches de neón", "musicbrainz_releasegroupid": "g-album"})

    def test_unsure_or_odd_answers_identify_nothing(self):
        unsure = {"status": "ok", "results": [{"score": 0.6, "recordings": ANSWER["results"][1]["recordings"]}]}
        self.assertIsNone(S.best_match(unsure))
        for odd in ({}, {"results": "x"}, {"results": [{"score": "alto"}]}, {"results": [{"score": 0.99}]},
                    {"results": [{"score": 0.99, "recordings": [{"title": "sin artista"}, 5]}]}):
            self.assertIsNone(S.best_match(odd))
        nameless = {"results": [{"score": 0.99, "recordings": [{"title": "T", "artists": [{"name": "A"}],
                                                               "releasegroups": "x"}]}]}
        self.assertEqual(S.best_match(nameless).album, "")

    def test_invalid_key(self):
        self.assertTrue(S.invalid_key({"status": "error", "error": {"code": 4, "message": "invalid API key"}}))
        self.assertFalse(S.invalid_key({"status": "error", "error": {"code": 3}}))
        self.assertFalse(S.invalid_key({"status": "ok"}))
        self.assertFalse(S.invalid_key({"error": "texto"}))


class IdentifyTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="zebamp-songid-")
        self.cache = S.IdCache(os.path.join(self.dir, "cache"))
        self.file = os.path.join(self.dir, "sin-etiquetas.mp3")
        with open(self.file, "wb") as fh:
            fh.write(b"audio")
        self.asked = []

    def ask(self, answer):
        def fake(key, duration, print_):
            self.asked.append((key, duration, print_))
            if isinstance(answer, Exception):
                raise answer
            return answer
        return fake

    def identify(self, answer=ANSWER, **kw):
        return S.identify(self.file, "KEY", self.cache, make_print=lambda path: (217.0, "PRINT"),
                          ask=self.ask(answer), **kw)

    def test_identified_once_then_remembered(self):
        self.assertEqual(self.identify().album, "Noches de neón")
        self.assertEqual(self.asked, [("KEY", 217.0, "PRINT")])
        self.assertEqual(self.identify().title, "Lluvia sobre el asfalto")
        self.assertEqual(len(self.asked), 1)                     # from the cache
        self.identify(force=True)
        self.assertEqual(len(self.asked), 2)

    def test_a_changed_file_is_a_new_file(self):
        self.identify()
        with open(self.file, "wb") as fh:
            fh.write(b"another recording")
        self.assertIsNone(self.cache.get(self.file))
        self.assertFalse(self.cache.tried(self.file))

    def test_unknown_songs_are_not_asked_about_again_for_a_while(self):
        self.assertIsNone(self.identify({"status": "ok", "results": []}))
        self.assertIsNone(self.identify())                       # even though it would be found now
        self.assertEqual(len(self.asked), 1)
        self.assertTrue(self.cache.tried(self.file))
        self.assertFalse(self.cache.tried(self.file, now=time.time() + S.NOT_FOUND_RETRY + 5))

    def test_offline_and_errors_are_not_remembered(self):
        self.assertIsNone(self.identify(OSError("offline")))
        self.assertIsNone(self.identify({"status": "error", "error": {"code": 5, "message": "internal"}}))
        self.assertFalse(self.cache.tried(self.file))
        self.assertIsNotNone(self.identify())

    def test_bad_key_is_reported(self):
        with self.assertRaises(S.BadKey):
            self.identify({"status": "error", "error": {"code": 4, "message": "invalid API key"}})
        self.assertIs(S.key_accepted("K", ask=self.ask({"status": "error", "error": {"code": 4}})), False)
        self.assertIs(S.key_accepted("K", ask=self.ask({"status": "error", "error": {"code": 3}})), True)
        self.assertIsNone(S.key_accepted("K", ask=self.ask(OSError("offline"))))

    def test_unreadable_audio(self):
        got = S.identify(self.file, "KEY", self.cache, make_print=lambda path: None, ask=self.ask(ANSWER))
        self.assertIsNone(got)
        self.assertEqual(self.asked, [])
        self.assertIsNone(S.identify(os.path.join(self.dir, "no-existe.mp3"), "KEY", self.cache,
                                     make_print=lambda path: None, ask=self.ask(ANSWER)))

    def test_when_recognising_by_sound_makes_sense(self):
        from unittest import mock
        song = {"file": "sin-etiquetas.mp3"}
        with mock.patch.object(S, "available", return_value=True):
            self.assertEqual(S.can_identify(song, self.dir, "KEY", self.cache), self.file)
            self.assertIsNone(S.can_identify(song, self.dir, "", self.cache))                    # no key
            self.assertIsNone(S.can_identify({**song, "artist": "A", "title": "T"}, self.dir, "KEY", self.cache))
            self.assertIsNone(S.can_identify({"file": "otro.mp3"}, self.dir, "KEY", self.cache))  # not on this computer
            self.assertIsNone(S.can_identify(song, None, "KEY", self.cache))                     # remote MPD
            self.assertIsNone(S.can_identify({"file": "http://radio/x"}, self.dir, "KEY", self.cache))
            self.identify()
            self.assertIsNone(S.can_identify(song, self.dir, "KEY", self.cache))                 # already done
        with mock.patch.object(S, "available", return_value=False):
            self.assertIsNone(S.can_identify({"file": "sin-etiquetas.mp3"}, self.dir, "KEY", S.IdCache(self.dir)))

    def test_described_prefers_tags_then_sound_then_file_name(self):
        song = {"file": "Banda - Tema.mp3"}
        shutil = __import__("shutil")
        shutil.copy(self.file, os.path.join(self.dir, "Banda - Tema.mp3"))
        self.assertEqual(S.described(song, self.dir, self.cache)["artist"], "Banda")            # file name
        S.identify(os.path.join(self.dir, "Banda - Tema.mp3"), "KEY", self.cache,
                   make_print=lambda path: (217.0, "PRINT"), ask=self.ask(ANSWER))
        got = S.described(song, self.dir, self.cache)
        self.assertEqual((got["artist"], got["album"], got["musicbrainz_releasegroupid"]),
                         ("Los Píxeles & Ana", "Noches de neón", "g-album"))                     # its sound
        tagged = {**song, "artist": "Etiqueta", "title": "Manda"}
        self.assertEqual(S.described(tagged, self.dir, self.cache), tagged)                     # tags win

    def test_group_id_from_the_sound_gives_the_exact_cover(self):
        song = S.described({"file": "sin-etiquetas.mp3"}, self.dir, self.cache)
        self.identify()
        song = S.described({"file": "sin-etiquetas.mp3"}, self.dir, self.cache)
        url = "https://coverartarchive.org/release-group/g-album/front-500"
        web = FakeWeb(pictures={url: PICTURE})
        found = C.find_cover(C.query_from_song(song), is_image, (), web.get_json, web.get_image)
        self.assertEqual((found.ident, web.asked), ("mb:g-album", [url]))


class FingerprintToolTest(unittest.TestCase):
    @unittest.skipUnless(S.available() and __import__("shutil").which("ffmpeg"), "fpcalc/ffmpeg not installed")
    def test_fpcalc_on_a_real_file(self):
        import subprocess
        path = os.path.join(tempfile.mkdtemp(prefix="zebamp-fp-"), "tono.flac")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=12", path],
                       check=True)
        duration, print_ = S.fingerprint(path)
        self.assertAlmostEqual(duration, 12, delta=0.5)
        self.assertGreater(len(print_), 20)
        self.assertIsNone(S.fingerprint(path + ".missing"))

    def test_request_sent_to_acoustid(self):
        from unittest import mock
        seen = {}

        class Reply:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self, n):
                return b'{"status": "ok", "results": []}'

        def fake_open(request, timeout):
            seen["url"], seen["data"] = request.full_url, request.data.decode()
            return Reply()
        with mock.patch.object(S.urllib.request, "urlopen", fake_open):
            self.assertEqual(S.ask_acoustid("KEY", 217.4, "PRINT"), {"status": "ok", "results": []})
        self.assertEqual(seen["url"], "https://api.acoustid.org/v2/lookup")
        for part in ("client=KEY", "duration=217", "fingerprint=PRINT", "meta=recordings+releasegroups"):
            self.assertIn(part, seen["data"])


if __name__ == "__main__":
    unittest.main()
