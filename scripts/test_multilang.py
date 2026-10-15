"""Multilanguage contracts: registry, verbatim detection, spec-driven field
mapping, canonical 原文/注音/译文 slots, and no-silent-fallback validation."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.languages import spec, is_known, is_implemented, implemented_list
from scripts.dataload import detect_language, load_song, compute_fingerprint
from scripts.validate import validate_schema


def _write(data):
    d = tempfile.mkdtemp()
    p = Path(d) / "data.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return str(p)


JA = {
    "language": "ja",
    "title": "t",
    "lyric_sections": [["Verse", [
        {"id": "a", "jp": "空", "romaji": "sora", "zh": "天空"},
    ]]],
}
EN = {
    "language": "en",
    "title": "t",
    "lyric_sections": [["Verse", [
        {"id": "a", "en": "sky", "zh": "天空"},
    ]]],
}
DE = {
    "language": "de",
    "title": "t",
    "lyric_sections": [["Verse", [
        {"id": "a", "text": "Der Himmel ist weit", "reading": "/deːɐ/", "zh": "天空辽阔"},
    ]]],
}
RU = {
    "language": "ru",
    "title": "t",
    "lyric_sections": [["Verse", [
        {"id": "a", "text": "Небо широко", "reading": "Nebo shiroko", "zh": "天空辽阔"},
    ]]],
}


class RegistryTests(unittest.TestCase):
    def test_implemented(self):
        for code in ("ja", "en", "de", "fr", "ru", "es"):
            self.assertTrue(is_implemented(code), code)

    def test_unimplemented(self):
        for code in ("zh", "mixed", "it", "ko"):
            self.assertFalse(is_implemented(code), code)

    def test_known_vs_unknown(self):
        for code in ("ja", "en", "de", "fr", "ru", "es", "zh", "mixed", "it", "ko"):
            self.assertTrue(is_known(code), code)
        self.assertFalse(is_known("xx"))

    def test_spec_fields(self):
        self.assertEqual(spec("ja")["line_fields"], ("jp", "romaji", "zh"))
        self.assertEqual(spec("en")["line_fields"], ("en", "zh"))
        for code in ("de", "fr", "ru", "es"):
            sp = spec(code)
            self.assertEqual(sp["line_fields"], ("text", "reading", "zh"), code)
            self.assertEqual(sp["has_reading"], True, code)
            self.assertEqual(sp["optional_fields"], ("reading",), code)
            self.assertEqual(sp["lyric_headers"], ("原文", "发音/注音", "中文翻译"), code)
        self.assertIsNone(spec("zh"))
        self.assertIsNone(spec("it"))

    def test_implemented_list(self):
        for code in ("ja", "en", "de", "fr", "ru", "es"):
            self.assertIn(code, implemented_list())


class DetectionTests(unittest.TestCase):
    def test_verbatim_no_coercion(self):
        self.assertEqual(detect_language({"language": "DE"}), ("de", True))
        self.assertEqual(detect_language({"language": "zh"}), ("zh", True))
        self.assertEqual(detect_language({"language": "ko"}), ("ko", True))

    def test_legacy_fallback(self):
        self.assertEqual(
            detect_language({"lyric_sections": [["V", [["a", "b", "c"]]]]}),
            ("ja", False))
        self.assertEqual(
            detect_language({"lyric_sections": [["V", [["a", "b"]]]]}),
            ("en", False))


class LoadSongTests(unittest.TestCase):
    def test_ja_maps_three_fields_and_canonical(self):
        d, meta = load_song(_write(JA))
        rec = meta["lines"][0]
        self.assertEqual(rec["jp"], "空")
        self.assertEqual(rec["romaji"], "sora")
        self.assertEqual(rec["zh"], "天空")
        self.assertEqual(rec["original"], "空")
        self.assertEqual(rec["reading"], "sora")
        self.assertEqual(len(meta["sections"][0][1][0]), 3)

    def test_en_maps_two_fields_and_canonical(self):
        d, meta = load_song(_write(EN))
        rec = meta["lines"][0]
        self.assertEqual(rec["en"], "sky")
        self.assertNotIn("jp", rec)
        self.assertNotIn("romaji", rec)
        self.assertEqual(rec["original"], "sky")
        self.assertNotIn("reading", rec)
        self.assertEqual(len(meta["sections"][0][1][0]), 2)

    def test_de_maps_generic_fields(self):
        d, meta = load_song(_write(DE))
        self.assertTrue(meta["implemented"])
        rec = meta["lines"][0]
        self.assertEqual(rec["text"], "Der Himmel ist weit")
        self.assertEqual(rec["reading"], "/deːɐ/")
        self.assertEqual(rec["zh"], "天空辽阔")
        self.assertEqual(rec["original"], "Der Himmel ist weit")
        self.assertEqual(len(meta["sections"][0][1][0]), 3)

    def test_ru_maps_generic_fields(self):
        d, meta = load_song(_write(RU))
        rec = meta["lines"][0]
        self.assertEqual(rec["original"], "Небо широко")
        self.assertEqual(rec["reading"], "Nebo shiroko")
        self.assertEqual(rec["zh"], "天空辽阔")

    def test_unimplemented_not_routed_to_ja(self):
        data = {"language": "zh", "title": "t",
                "lyric_sections": [["V", [{"id": "a", "zh": "天空"}]]]}
        d, meta = load_song(_write(data))
        self.assertEqual(meta["language"], "zh")
        self.assertFalse(meta["implemented"])


class ValidateTests(unittest.TestCase):
    def _errs(self, data):
        d, meta = load_song(_write(data))
        _, errors = validate_schema(d, meta["lines"], meta["language"])
        return errors

    def test_implemented_languages_have_no_language_error(self):
        for data in (JA, EN, DE, RU):
            errs = self._errs(data)
            self.assertFalse(any("language" in e for e in errs), errs)

    def test_unimplemented_languages_block(self):
        for code in ("zh", "mixed", "it", "ko"):
            data = {"language": code, "title": "t",
                    "lyric_sections": [["V", [["a", "b"]]]]}
            errs = self._errs(data)
            self.assertTrue(any("未实现" in e for e in errs), (code, errs))

    def test_unknown_language_blocks(self):
        data = {"language": "xx", "title": "t",
                "lyric_sections": [["V", [["a", "b"]]]]}
        errs = self._errs(data)
        self.assertTrue(any("未知" in e or "非法" in e for e in errs), errs)

    def test_optional_reading_not_warned(self):
        data = {"language": "de", "title": "t",
                "lyric_sections": [["V", [
                    {"id": "a", "text": "Hallo", "reading": "", "zh": "你好"}]]]}
        d, meta = load_song(_write(data))
        warnings, _ = validate_schema(d, meta["lines"], meta["language"])
        self.assertFalse(any("reading" in w for w in warnings), warnings)


class FingerprintTests(unittest.TestCase):
    def test_covers_canonical_fields(self):
        base = [{"section": "V", "id": "a", "original": "空", "reading": "sora", "zh": "天空"}]
        fp = compute_fingerprint(base)
        for key in ("original", "reading", "zh"):
            changed = [dict(base[0], **{key: base[0][key] + "X"})]
            self.assertNotEqual(compute_fingerprint(changed), fp, key)

    def test_ignores_id_and_section(self):
        base = [{"section": "V", "id": "a", "original": "空", "reading": "sora", "zh": "天空"}]
        fp = compute_fingerprint(base)
        renamed = [dict(base[0], id="b", section="Chorus")]
        self.assertEqual(compute_fingerprint(renamed), fp)

    def test_new_language_text_participates(self):
        d, meta1 = load_song(_write(DE))
        de2 = json.loads(json.dumps(DE))
        de2["lyric_sections"][0][1][0]["text"] = "Der Himmel ist eng"
        d, meta2 = load_song(_write(de2))
        self.assertNotEqual(meta1["fingerprint"], meta2["fingerprint"])

    def test_ja_fingerprint_unchanged(self):
        # ja canonical slots == jp/romaji/zh, so the legacy algorithm must hold.
        d, meta = load_song(_write(JA))
        rec = meta["lines"][0]
        expect = compute_fingerprint(
            [{"original": rec["jp"], "reading": rec["romaji"], "zh": rec["zh"]}])
        self.assertEqual(meta["fingerprint"], expect)


if __name__ == "__main__":
    unittest.main()
