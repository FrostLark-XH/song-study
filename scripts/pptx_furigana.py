"""Token-based Japanese lyric parsing via SudachiPy.

Each token: {base, kana, needs_furi}
  - base: original surface text
  - kana: hiragana reading (empty string if pure kana)
  - needs_furi: True if token contains kanji → needs furigana overlay
"""

from sudachipy import Dictionary
from sudachipy.tokenizer import Tokenizer

_tokenizer = Dictionary().create()

# Katakana → Hiragana mapping
_KATA_SHIFT = 0x30A1 - 0x3041  # カ(0x30AB) - か(0x304B) = 96


def _kata_to_hira(text: str) -> str:
    """Convert katakana string to hiragana."""
    result = []
    for ch in text:
        if 'ァ' <= ch <= 'ヶ':
            result.append(chr(ord(ch) - _KATA_SHIFT))
        elif ch == 'ヷ':
            result.append('わ')
        elif ch == 'ヸ':
            result.append('ゐ')
        elif ch == 'ヹ':
            result.append('ゑ')
        elif ch == 'ヺ':
            result.append('を')
        else:
            result.append(ch)
    return ''.join(result)


def _has_kanji(text: str) -> bool:
    """Check if text contains CJK unified ideographs."""
    for ch in text:
        if '一' <= ch <= '鿿' or '㐀' <= ch <= '䶿':
            return True
    return False


def tokenize(text: str) -> list[dict]:
    """Tokenize Japanese text and produce base/kana/furi tokens.

    Only tokens containing kanji get furigana readings. Pure kana tokens
    (including okurigana after a kanji stem) get empty kana string.
    Consecutive kana-only tokens are merged for cleaner layout.
    """
    raw = _tokenizer.tokenize(text)
    tokens = []
    for tok in raw:
        surface = tok.surface()
        reading = _kata_to_hira(tok.reading_form())
        has_kj = _has_kanji(surface)
        tokens.append({
            "base": surface,
            "kana": reading if has_kj else "",
            "needs_furi": has_kj,
        })
    return _merge_tokens(tokens)


def _merge_tokens(tokens: list[dict]) -> list[dict]:
    """Merge consecutive kana-only tokens. Merge consecutive kanji tokens
    for compound words (e.g., '見' + '失わ' → '見失わ')."""
    merged = []
    buf_base = ""
    buf_kana = ""
    buf_has_kanji = False

    for t in tokens:
        if t["needs_furi"]:
            # Kanji token: accumulate with previous kanji/kana
            if buf_base and not buf_has_kanji:
                # Flush kana buffer before starting kanji group
                merged.append({"base": buf_base, "kana": "", "needs_furi": False})
                buf_base = ""
                buf_kana = ""
            buf_base += t["base"]
            buf_kana += t["kana"]
            buf_has_kanji = True
        else:
            if buf_has_kanji:
                # Flush kanji group
                merged.append({"base": buf_base, "kana": buf_kana, "needs_furi": True})
                buf_base = ""
                buf_kana = ""
                buf_has_kanji = False
            buf_base += t["base"]

    # Flush remaining
    if buf_base:
        merged.append({
            "base": buf_base,
            "kana": buf_kana,
            "needs_furi": buf_has_kanji,
        })

    return merged
