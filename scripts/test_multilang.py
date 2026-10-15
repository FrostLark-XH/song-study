"""Phase-1 multilanguage contracts: registry, verbatim detection, spec-driven
field mapping, and no-silent-fallback validation."""
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


class RegistryTests(unittest.TestCase):
    def test_implemented(self):
        self.assertTrue(is_implemented("ja"))
        self.assertTrue(is_implemented("en"))
        self.assertFalse(is_implemented("zh"))
        self.assertFalse(is_implemented("de"))

    def test_known_vs_unknown(self):
        for code in ("zh", "mixed", "de", "fr", "ru", "es", "it", "ko"):
            self.assertTrue(is_known(code), code)
        self.assertFalse(is_known("xx"))

    def test_spec_fields(self):
        self.assertEqual(spec("ja")["line_fields"], ("jp", "romaji", "zh"))
        self.assertEqual(spec("en")["line_fields"], ("en", "zh"))
        self.assertIsNone(spec("zh"))
        self.assertEqual(spec("ja")["lyric_headers"], ("原文", "发音（罗马字）", "中文翻译"))
        self.assertEqual(spec("en")["vocab_headers"],
                         ("单词/短语", "音标/发音提示", "词性", "释义", "难度"))

    def test_implemented_list(self):
        self.assertIn("ja", implemented_list())
        self.assertIn("en", implemented_list())


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
    def test_ja_maps_three_fields(self):
        d, meta = load_song(_write(JA))
        self.assertEqual(meta["language"], "ja")
        self.assertTrue(meta["implemented"])
        rec = meta["lines"][0]
        self.assertEqual(rec["jp"], "空")
        self.assertEqual(rec["romaji"], "sora")
        self.assertEqual(rec["zh"], "天空")
        self.assertEqual(len(meta["sections"][0][1][0]), 3)

    def test_en_maps_two_fields(self):
        d, meta = load_song(_write(EN))
        self.assertEqual(meta["language"], "en")
        self.assertTrue(meta["implemented"])
        rec = meta["lines"][0]
        self.assertEqual(rec["en"], "sky")
        self.assertNotIn("jp", rec)
        self.assertNotIn("romaji", rec)
        self.assertEqual(len(meta["sections"][0][1][0]), 2)

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
        for data in (JA, EN):
            errs = self._errs(data)
            self.assertFalse(any("language" in e for e in errs), errs)

    def test_unimplemented_language_blocks(self):
        data = {"language": "de", "title": "t",
                "lyric_sections": [["V", [["a", "b"]]]]}
        errs = self._errs(data)
        self.assertTrue(any("未实现" in e for e in errs), errs)

    def test_unknown_language_blocks(self):
        data = {"language": "xx", "title": "t",
                "lyric_sections": [["V", [["a", "b"]]]]}
        errs = self._errs(data)
        self.assertTrue(any("未知" in e or "非法" in e for e in errs), errs)

    def test_en_line_fields_checked_by_spec(self):
        d, meta = load_song(_write(EN))
        warnings, _ = validate_schema(d, meta["lines"], meta["language"])
        self.assertFalse(any("jp" in w or "romaji" in w for w in warnings), warnings)


class FingerprintTests(unittest.TestCase):
    def test_covers_all_text_fields(self):
        base = [{"section": "V", "id": "a", "jp": "空", "romaji": "sora", "zh": "天空"}]
        fp = compute_fingerprint(base)
        for key in ("jp", "romaji", "zh"):
            changed = [dict(base[0], **{key: base[0][key] + "X"})]
            self.assertNotEqual(compute_fingerprint(changed), fp, key)

    def test_ignores_id_and_section(self):
        base = [{"section": "V", "id": "a", "jp": "空", "romaji": "sora", "zh": "天空"}]
        fp = compute_fingerprint(base)
        renamed = [dict(base[0], id="b", section="Chorus")]
        self.assertEqual(compute_fingerprint(renamed), fp)


if __name__ == "__main__":
    unittest.main()
