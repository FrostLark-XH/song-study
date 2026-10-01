# 内容数据契约

正式数据入口是 `scripts/dataload.load_song(path)`，返回 `(data, meta)`；所有生成器共用它。`meta.lines` 是有 ID 的归一化记录，`meta.sections` 是渲染元组，`meta.fingerprint` 是当前文本指纹。视觉字段由 [PPT 接口](../PPTX-DESIGN.md) 定义，不另造渲染字段。

## 新数据

内容 schema 为 `2.1`，与渲染版本 3/4、director 版本 1 分别编号。下例为自拟内容骨架，待核验状态不代表已经完成任何检查；完整任务按真实内容填充。

```json
{
  "schema_version": "2.1", "title": "練習 — Sample", "language": "ja",
  "info_rows": [["歌曲名", "練習"], ["演唱者", "Sample"], ["版本", "自拟例句"]],
  "lyric_sections": [["[Verse]", [
    {"id": "line-a", "jp": "今日も歩く", "romaji": "Kyou mo aruku", "zh": "今天也继续走"}
  ]]],
  "bg_paras": [], "vocab_table": [], "grammar_points": [], "culture_notes": [], "singing_tips": [],
  "sources_lyrics": [], "sources_bg": [],
  "verification": {
    "license": "自拟例句；实际歌曲另记使用范围",
    "checks": {
      "song_version": {"status": "待核验", "note": ""},
      "lyric_text": {"status": "待核验", "note": ""},
      "reading_translation": {"status": "待核验", "note": ""},
      "structure": {"status": "待核验", "note": ""},
      "render": {"status": "待核验", "note": ""},
      "visual": {"status": "待核验", "note": ""}
    },
    "lyrics": {"sources": [], "text_compared": "尚未比对", "diff_summary": []},
    "lines": {"line-a": "待核验"}
  },
  "bg_color": "F4F3EE", "mood": "quiet"
}
```

| 字段 | 实际形态与边界 |
| --- | --- |
| language | schema 接受 ja/en/zh/mixed；v3/v4 只支持 ja。语言接受值不等于渲染已验收。非日语沿用已适配旧路径；中文/混合/韩语先查列结构与能力，不直接套日语对象 |
| lyric_sections | `[段名, 行列表]`；日语行 `{id,jp,romaji,zh}`，英文旧路径 `{id,en,zh}`。每格一句，不用 `/` 拼多句 |
| bg_paras / culture_notes | 字符串列表；需要的出处与解读身份写入文本或来源记录 |
| vocab_table | 日语每行 `[原文,读音,词性,释义,参考JLPT]`，不确定等级 `—`；其他语言按已有生成器形态 |
| grammar_points | 对象列表：name、section、quote、analysis、extra（歌词外例句） |
| singing_tips | 对象列表：name、problem、solution |
| sources_lyrics / sources_bg | 去重字符串列表，包含来源名、描述、URL、抓取日期；来源结构化记录另在 verification.lyrics.sources |
| verification | 状态、比对与证据定义见 [来源与核验](sources-and-verification.md) |

## 持久 ID 与指纹

ID 是身份而非当前位置。插行分配未用 ID；重排、跨段移动、文字纠错保留原 ID，逐行元数据按 ID 跟随。相同歌词的多次演唱使用独立 ID。删除行时清除悬空引用；文字纠错虽然保留 ID，仍须重查受影响状态。别把 `[Verse]:L01` 中的历史段名/编号解释为当前位置。

`compute_fingerprint(meta.lines)` 对源序下各行原文、注音、翻译计算 SHA-256 前 16 位。文本或顺序改变会影响它；ID、段名、颜色和位置不进入散列。它能提醒证据可能过期，不能单独证明内容未变：改段名/ID/版本仍按实际影响检查。核验结束后写 `verification.fingerprint`，设计落地后写 `director.source_fingerprint`；刷新两者都需核对受影响内容，不能消除告警了事。

## 旧数据

`load_song()` 兼容旧元组行，并派生 ID、标 `derived`；仅作兼容，不是持久 ID。缺 language 会按列数回退并告警，缺 schema/来源/分项状态也不能推定正确。`mood` 非 hex 回退底色。只有用户要求迁移或编辑需要时才迁移，冻结基准不强改。

迁移：补 schema_version/language；vocab_rows→vocab_table；grammar_points/singing_tips 元组→对象；culture_notes 元组→字符串；歌词保存独立 ID；补 sources_* 与有真实依据的 verification，旧 verify_text 仅是历史文字，不直接转为已核验。先备份、再归一化及校验；不改未涉及内容或复用重复 ID。
