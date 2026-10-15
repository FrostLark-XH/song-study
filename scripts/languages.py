"""语言注册表 — 多语言支持的单一事实来源（single source of truth）。

区分两个正交概念，避免把「语言代码」和「是否已实现」混为一谈：

  - 一个语言 *代码*（code）只是加载器能识别的标识符。
  - 一个语言只有在其「歌词字段映射、渲染器、教学路径」都就位并验收后，
    才算是 *已实现*（implemented）。

Phase 2 已实现 ja（原文/读音/译文三列）、en（原文/译文两列）与 de/fr/ru/es
（原文/注音/译文，注音列可选）。仍阻断 zh/mixed（中文与混合语言后续单独处理）
以及 it/ko（已识别未实现），绝不静默回退成日语。

新增语言 = 在 LANGUAGES 里加一项 spec；dataload / validate / build_md / build_docx
都只读 spec 的 line_fields / lyric_headers / vocab_headers / optional_fields，不需要
改语言分支逻辑。

字段说明（先实现真正需要的部分，不建复杂插件框架）：

  - line_fields     字典行字段顺序：(原文, [读音辅助], 中文翻译)。读音层可选。
  - lyric_headers   歌词表格列标题，与 line_fields 一一对应，由 MD/DOCX 渲染直接消费。
  - has_reading     是否有独立的读音/注音层（决定渲染列数）。
  - arity           旧裸元组行的列数，仅用于无 language 字段时的列数启发式回退。
  - vocab_headers   词汇表表头，是词汇教学规则在代码层的唯一入口。
  - optional_fields 可留空的字段（如可选注音 reading）；校验时这些字段为空不告警。

注音策略与字体需求：ja 的注音由 scripts/pptx_furigana.py（SudachiPy + jaconv）
负责，字体角色由 scripts/pptx_fonts.py 的 jp/gothic/furigana/romaji/cn/en 覆盖；
en 无注音层、使用 romaji/cn 角色。这些是 PPT 侧关注点，Phase 1/2 未改动，后续
接入新语言时按语言补注音器与字体角色，不必改本文件的结构。
"""

# 无独立注音层或注音可选的拉丁文字系语言，共用同一套词汇表表头（IPA/发音提示列）。
_LATIN_VOCAB = ("单词/短语", "音标/发音提示", "词性", "释义", "难度")

# 语言代码 → 语言规格。只有 IMPLEMENTED 的语言有 spec。
LANGUAGES = {
    "ja": {
        "name": "日语",
        "line_fields": ("jp", "romaji", "zh"),
        "lyric_headers": ("原文", "发音（罗马字）", "中文翻译"),
        "has_reading": True,
        "arity": 3,
        "vocab_headers": ("原文", "读音", "词性", "释义", "等级"),
    },
    "en": {
        "name": "英语",
        "line_fields": ("en", "zh"),
        "lyric_headers": ("原文", "中文翻译"),
        "has_reading": False,
        "arity": 2,
        "vocab_headers": _LATIN_VOCAB,
    },
    "de": {
        "name": "德语",
        "line_fields": ("text", "reading", "zh"),
        "lyric_headers": ("原文", "发音/注音", "中文翻译"),
        "has_reading": True,
        "arity": 3,
        "vocab_headers": _LATIN_VOCAB,
        "optional_fields": ("reading",),
    },
    "fr": {
        "name": "法语",
        "line_fields": ("text", "reading", "zh"),
        "lyric_headers": ("原文", "发音/注音", "中文翻译"),
        "has_reading": True,
        "arity": 3,
        "vocab_headers": _LATIN_VOCAB,
        "optional_fields": ("reading",),
    },
    "ru": {
        "name": "俄语",
        "line_fields": ("text", "reading", "zh"),
        "lyric_headers": ("原文", "发音/注音", "中文翻译"),
        "has_reading": True,
        "arity": 3,
        "vocab_headers": _LATIN_VOCAB,
        "optional_fields": ("reading",),
    },
    "es": {
        "name": "西班牙语",
        "line_fields": ("text", "reading", "zh"),
        "lyric_headers": ("原文", "发音/注音", "中文翻译"),
        "has_reading": True,
        "arity": 3,
        "vocab_headers": _LATIN_VOCAB,
        "optional_fields": ("reading",),
    },
}

# 已识别但尚未实现的代码。识别它们是为了给出具体、可行动的错误，
# 而不是笼统的「未知」或静默回退 ja。
KNOWN_UNIMPLEMENTED = ("zh", "mixed", "it", "ko")

IMPLEMENTED_LANGUAGES = tuple(LANGUAGES)


def is_known(code: str) -> bool:
    return code in LANGUAGES or code in KNOWN_UNIMPLEMENTED


def is_implemented(code: str) -> bool:
    return code in LANGUAGES


def spec(code: str):
    """返回语言 spec；未实现/未知返回 None。"""
    return LANGUAGES.get(code)


def implemented_list() -> str:
    return "、".join(IMPLEMENTED_LANGUAGES)
