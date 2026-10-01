"""Ruby engine for Japanese lyric cards.

Two jobs:
  1. tokenize() — SudachiPy 分词 → 送假名剥离，产出「unit 列表」
  2. plan_ruby() — slot 布局 + 碰撞检测，计算每行 ruby 的字号与水平位置

Unit model:
  {"base": str, "ruby": str}
  - base: 表面文字（汉字或假名），按正文字号连续排布
  - ruby: 需悬在该 base 上方的平假名读音（空串 = 不注音）

核心规则：ruby 只盖在汉字上，送假名（送り仮名）以正文字号裸排，与汉字
共用一条基线。例如「戻れ」→ 汉字部「戻」注音「もど」，送假名「れ」裸排。
"""

import jaconv
import re
from sudachipy import Dictionary
from sudachipy.tokenizer import Tokenizer

EMU_PER_PT = 12700

# SplitMode.A（短分割）把「受け取る」拆成「受け+取る」、「見失わ」拆成
# 「見+失わ」，避免内部送假名的混合词，让 okurigana 剥离更可靠。
_tokenizer = Dictionary().create(mode=Tokenizer.SplitMode.A)

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


def _is_hiragana(ch: str) -> bool:
    return 'ぁ' <= ch <= 'ん' or ch in 'ーゝゞぁぃぅぇぉゃゅょっ'


def _is_katakana(ch: str) -> bool:
    return 'ァ' <= ch <= 'ヶ' or ch in 'ーヽヾヮヵッ'


def _is_kana(ch: str) -> bool:
    return _is_hiragana(ch) or _is_katakana(ch)


def _has_kanji(text: str) -> bool:
    """Check if text contains CJK unified ideographs."""
    for ch in text:
        if '一' <= ch <= '鿿' or '㐀' <= ch <= '䶿':
            return True
    return False


def _split_token(surface: str, reading: str) -> list[dict]:
    """Split one token into kanji(ruby) + okurigana(bare) units.

    Okurigana is the trailing kana run of the surface. The reading covers the
    whole token; the kanji portion's ruby = reading minus the trailing
    okurigana (matched by suffix, since okurigana reads as itself).
    """
    if not _has_kanji(surface):
        return [{"base": surface, "ruby": ""}]

    i = len(surface)
    while i > 0 and _is_kana(surface[i - 1]):
        i -= 1
    okuri = surface[i:]
    kanji_part = surface[:i]

    if okuri:
        ruby = reading[:len(reading) - len(okuri)] if reading.endswith(okuri) else reading
    else:
        ruby = reading

    units = []
    if kanji_part:
        units.append({"base": kanji_part, "ruby": ruby})
    if okuri:
        units.append({"base": okuri, "ruby": ""})
    return units


# ── Romaji-driven reading alignment ───────────────────────────────────────────

_READING_WARNINGS: list[str] = []

_PARTICLE_READING = {"は": "わ", "へ": "え", "を": "を"}


def reset_reading_warnings() -> None:
    _READING_WARNINGS.clear()


def get_reading_warnings() -> list[str]:
    seen = set()
    out = []
    for w in _READING_WARNINGS:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


def _kana_only(text: str) -> str:
    return "".join(ch for ch in text if _is_kana(ch))


def _norm_reading(text: str) -> str:
    """Merge Hepburn-lossy pairs: ず/づ and じ/ぢ are indistinguishable in romaji."""
    return text.replace("づ", "ず").replace("ぢ", "じ")


def _surface_kana_to_reading(ch: str) -> str:
    return _PARTICLE_READING.get(ch, ch)


def _split_kanji_okuri(surface: str) -> tuple[str, str]:
    if not _has_kanji(surface):
        return surface, ""
    i = len(surface)
    while i > 0 and _is_kana(surface[i - 1]):
        i -= 1
    return surface[:i], surface[i:]


def tokenize(text: str) -> list[dict]:
    """Tokenize Japanese text into ruby units (kanji with ruby + bare kana)."""
    raw = _tokenizer.tokenize(text)
    units = []
    for tok in raw:
        surface = tok.surface()
        reading = _kata_to_hira(tok.reading_form())
        units.extend(_split_token(surface, reading))
    return units


def _search_seg_end(seg: list[dict], kana: str, rp: int, next_mapped: str) -> int | None:
    """Locate a kanji segment's right edge via its trailing kana anchor.

    Used when the Sudachi length hint is wrong (a homograph). The anchor is the
    kana token that immediately follows the segment; it must sit after at least
    `min_kana` (one kana per kanji glyph). If several positions match the edge
    is ambiguous → None (caller bails to bare text).
    """
    min_kana = sum(len(s["kanji_part"]) for s in seg)
    hint = sum(len(s["sudachi_kanji"]) + len(s["okuri"]) for s in seg)
    slack = max(2, len(next_mapped) + 1)
    lo = rp + min_kana
    hi = min(rp + hint + slack, len(kana) - len(next_mapped))
    found = None
    for end in range(lo, hi + 1):
        if kana[end:end + len(next_mapped)] == next_mapped:
            if found is not None:
                return None
            found = end
    return found


def _resolve_segment(seg: list[dict], kana: str, rp: int, next_mapped: str | None):
    """Align one run of contiguous kanji tokens.

    The segment's right edge is pinned by the trailing kana anchor (or the line
    end); inside it each token's kanji reading is sized by the Sudachi length
    hint and checked against its own okurigana. A homograph that breaks either
    check triggers an anchor search; anything still ambiguous bails out.

    Returns (units, new_rp, ok). On failure units are bare and ok is False.
    """
    seg_hint = sum(len(s["sudachi_kanji"]) + len(s["okuri"]) for s in seg)
    seg_end = rp + seg_hint

    if next_mapped is not None:
        if seg_end + len(next_mapped) > len(kana) or kana[seg_end:seg_end + len(next_mapped)] != next_mapped:
            seg_end = _search_seg_end(seg, kana, rp, next_mapped)
            if seg_end is None:
                return [{"base": s["surf"], "ruby": ""} for s in seg], rp, False
    else:
        seg_end = len(kana)

    S = kana[rp:seg_end]
    units: list[dict] = []
    sp = 0
    for s in seg:
        kl = len(s["sudachi_kanji"])
        ok = s["okuri_mapped"]
        if ok:
            if sp + kl + len(ok) <= len(S) and S[sp + kl:sp + kl + len(ok)] == ok:
                kl_actual = kl
            else:
                pos = S.find(ok, sp + len(s["kanji_part"]))
                if pos < 0:
                    return [{"base": s["surf"], "ruby": ""} for s in seg], rp, False
                kl_actual = pos - sp
        else:
            kl_actual = len(S) - sp if s is seg[-1] else kl

        ruby_romaji = S[sp:sp + kl_actual]
        sudachi_kanji = s["sudachi_kanji"]
        if _norm_reading(ruby_romaji) == _norm_reading(sudachi_kanji):
            ruby = sudachi_kanji  # keep Sudachi spelling (fix づ/ぢ)
        else:
            ruby = ruby_romaji  # romaji authoritative (homograph)
            _READING_WARNINGS.append(
                f"[多读法] {s['surf']}：romaji={ruby_romaji}，sudachi={sudachi_kanji} → 用 romaji")

        if s["kanji_part"]:
            units.append({"base": s["kanji_part"], "ruby": ruby})
        if s["okuri"]:
            units.append({"base": s["okuri"], "ruby": ""})
        sp += kl_actual + len(ok)

    if sp != len(S):
        return [{"base": s["surf"], "ruby": ""} for s in seg], rp, False
    return units, seg_end, True


def align_reading(text: str, romaji: str) -> list[dict]:
    """Align a reliable romaji reading to the lyric text and emit ruby units.

    The reading comes from the romaji (human-verified). Sudachi supplies only
    segmentation plus a per-token length hint; the original kana (okurigana and
    standalone kana tokens) act as anchors pinning each kanji reading's span.
    On any unstable alignment the whole line is rendered bare with a
    `[人工确认]` warning — never guessed.
    """
    if not romaji:
        return tokenize_fallback(text)

    # jaconv maps 'sonna' to そんあ unless the syllabic n is disambiguated.
    normalized_romaji = re.sub(r"nn(?=[aeiouy])", "n'n", romaji.lower())
    kana = _kana_only(jaconv.alphabet2kana(normalized_romaji))
    tokens = _tokenizer.tokenize(text)

    # First accept dictionary segmentation only when its entire spoken reading
    # exactly matches the supplied romaji. Punctuation and katakana do not consume
    # extra morae. This verifies alignment, not the source's linguistic accuracy.
    spoken = []
    for tok in tokens:
        surface = tok.surface()
        reading = _kana_only(_kata_to_hira(tok.reading_form()))
        if tok.part_of_speech()[0] == "助詞":
            reading = {"は": "わ", "へ": "え", "を": "お"}.get(surface, reading)
        spoken.append(reading)
    canonical = lambda value: _norm_reading(value).replace("を", "お")
    if canonical("".join(spoken)) == canonical(kana):
        return tokenize(text)

    infos = []
    for tok in tokens:
        surf = tok.surface()
        if _has_kanji(surf):
            kanji_part, okuri = _split_kanji_okuri(surf)
            s_read = _kata_to_hira(tok.reading_form())
            infos.append({
                "kind": "kanji", "surf": surf, "kanji_part": kanji_part,
                "okuri": okuri,
                "okuri_mapped": "".join(_surface_kana_to_reading(c) for c in okuri),
                "sudachi_kanji": s_read[:len(s_read) - len(okuri)],
            })
        elif _is_kana(surf):
            infos.append({
                "kind": "kana", "surf": surf,
                "mapped": "".join(_surface_kana_to_reading(c) for c in surf),
            })
        else:
            infos.append({"kind": "symbol", "surf": surf})

    units: list[dict] = []
    aligned = True
    rp = 0
    i, n = 0, len(infos)
    while i < n:
        info = infos[i]
        if info["kind"] == "kana":
            m = info["mapped"]
            if rp + len(m) <= len(kana) and kana[rp:rp + len(m)] == m:
                rp += len(m)
            else:
                aligned = False
            units.append({"base": info["surf"], "ruby": ""})
            i += 1
        elif info["kind"] == "symbol":
            units.append({"base": info["surf"], "ruby": ""})
            i += 1
        else:
            seg = []
            j = i
            while j < n and infos[j]["kind"] == "kanji":
                seg.append(infos[j])
                j += 1
            # Punctuation has no sung mora. Look past it to the next kana
            # anchor so 嗚呼、いつもの様に does not consume the whole reading.
            anchor = j
            while anchor < n and infos[anchor]["kind"] == "symbol":
                anchor += 1
            next_mapped = infos[anchor]["mapped"] if anchor < n and infos[anchor]["kind"] == "kana" else None
            seg_units, rp, ok = _resolve_segment(seg, kana, rp, next_mapped)
            units.extend(seg_units)
            if not ok:
                aligned = False
            i = j

    if rp != len(kana):
        aligned = False

    if not aligned:
        _READING_WARNINGS.append(f"[人工确认] {text}：罗马音无法稳定对齐，相关汉字已裸排")
        units = [{"base": u["base"], "ruby": ""} for u in units]

    return units


def tokenize_fallback(text: str) -> list[dict]:
    """No-romaji path: Sudachi reading with OOV manual-confirm + report trace.

    Reliable romaji is absent, so Sudachi is only trusted for words it knows.
    Out-of-vocabulary kanji are rendered bare with a `[人工确认]` warning; every
    accepted reading is tagged `sudachi_fallback` so the report shows it was
    never human-confirmed.
    """
    _READING_WARNINGS.append(f"[Sudachi回退] {text}：无罗马音，读音来自 Sudachi 词典（未经逐字人工确认）")
    units = []
    for tok in _tokenizer.tokenize(text):
        surf = tok.surface()
        if _has_kanji(surf) and tok.is_oov():
            _READING_WARNINGS.append(f"[人工确认] {surf}：词典外词，读音无法确认，已裸排")
            units.append({"base": surf, "ruby": "", "readingSource": "sudachi_fallback"})
            continue
        reading = _kata_to_hira(tok.reading_form())
        for u in _split_token(surf, reading):
            if _has_kanji(surf):
                u["readingSource"] = "sudachi_fallback"
            units.append(u)
    return units


def _char_w_em(fs_pt: float) -> int:
    """CJK/kana glyph width as a square em at the given font size."""
    return int(fs_pt * EMU_PER_PT)


def plan_ruby(units: list[dict], base_fs_pt: float, max_width_em: int,
              ruby_start_pt: float = 13.0, ruby_floor_pt: float = 10.0):
    """Compute ruby font size and per-unit placement, guaranteeing no collision.

    Base text stays continuous; each ruby is centered over its kanji base.
    If a ruby is wider than its base it would overrun the next unit — the ruby
    font is shrunk stepwise until every ruby clears the next unit by GAP_EM.
    If even at the floor it still collides, ruby is dropped (base-only).

    Returns (ruby_fs_pt, placements, drop_ruby):
      placements = list of {x, w, text, base_x, base_w} in EMU, x/w absolute
      from line start (renderer adds the line's x origin).
    """
    GAP_EM = int(1.5 * EMU_PER_PT)
    base_cw = _char_w_em(base_fs_pt)

    positions = []
    x = 0
    for u in units:
        positions.append(x)
        x += len(u["base"]) * base_cw

    ruby_fs = ruby_start_pt
    drop_ruby = False

    while True:
        placements = []
        for i, u in enumerate(units):
            if not u["ruby"]:
                continue
            base_w = len(u["base"]) * base_cw
            ruby_w = len(u["ruby"]) * _char_w_em(ruby_fs)
            cx = positions[i] + base_w // 2
            placements.append({
                "x": cx - ruby_w // 2,
                "w": ruby_w,
                "text": u["ruby"],
                "idx": i,
                "base_x": positions[i],
                "base_w": base_w,
            })

        collision = False
        for p in placements:
            ni = p["idx"] + 1
            if ni < len(positions):
                if p["x"] + p["w"] + GAP_EM > positions[ni]:
                    collision = True
                    break
            if p["x"] + p["w"] > max_width_em:
                collision = True
                break

        if not collision:
            break
        if ruby_fs <= ruby_floor_pt:
            drop_ruby = True
            break
        ruby_fs -= 1.0

    return ruby_fs, placements, drop_ruby
