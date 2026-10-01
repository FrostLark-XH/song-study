# PPT 接口：逐页计划 v3 / 场景 v4

目标是把歌曲的视觉决定直接落到页面，并保留歌词可编辑性。歌词只存于 `lyric_sections`；页面引用持久行 ID，不复制文本。旧 L1–L8 路径仍保留，设置 `renderVersion: 3` 或 `4` 才进入新渲染器。v4 在相同歌词文本引擎上增加共享物件、可执行场景与页间联系，完整接口见 [references/scene-contract.md](references/scene-contract.md)。

## 先决定美术，后选接口

设计方法以 references/visual-directing.md 为准。v3 可用空 motifs 输出纯底文字页；v4 适用于需要共享对象/场景状态的方案。v4 当前每页都要求 scene，尚无显式无图页接口，不能把这项限制包装成“每页都应配图”。视觉脚本可以先于可执行页计划形成；此阶段不运行要求 pages 完整的结构验收，也不标视觉通过。

## 兼容旧计划的视觉字段示例

以下只展示渲染字段，合并到已有、通过校验的日语 `data.json` 中。将 `line_ids` 换成该文件真实 ID，并覆盖全部演唱行。它不含导演契约，不能作为新歌设计已完成的证明；新方案使用末节的完整契约及 `examples/`。

```json
{
  "visual_profile": {
    "renderVersion": 3,
    "cover": {
      "title": "歌名", "artist": "歌手",
      "background": "163AA6", "ink": "FFFFFF", "secondary": "DDE6FF"
    },
    "previewPageIds": ["opening-01"]
  },
  "visual_assets": {
    "pages": [
      {
        "id": "opening-01", "line_ids": ["line-a", "line-b"],
        "layout": "left", "role": "introduce",
        "reason": "轻声开场，以浅底与留白留出呼吸。",
        "background": "F4F3EE", "ink": "182A48",
        "secondary": "4D5D72", "accent": "173FAF",
        "font_size": 47, "vertical": 0.45, "gap": 36,
        "motifs": []
      }
    ]
  }
}
```

## v3 真正消费的字段

| 字段 | 行为 |
| --- | --- |
| `renderVersion: 3` | 选择 `scripts/pptx_editorial.py`；仅支持 `language: ja` |
| `cover` | 可设 title、artist、subtitle、typeface、background、ink、secondary、motifs；不设置则从基本信息提取标题/歌手 |
| `pages[].id` | 持久页 ID，同时决定装饰的默认随机种子 |
| `line_ids` | 每页 1–3 行，必须同段；全计划按源顺序覆盖每次演唱行且恰好一次 |
| `typeface` | `serif` 使用实际安装的明朝/衬线角色，`sans` 使用实际安装的黑体角色；正文测量与显示采用同一字体角色，默认 serif |
| `layout` | `left` 左对齐、`center` 居中、`right` 右对齐、`stagger` 后续行缩进 |
| `background / ink / secondary` | 六位十六进制色；底色、主歌词色、注音译文色 |
| `accent` | 为兼容视觉计划保留并检查格式，当前不会独立绘制装饰 |
| `font_size` | 主歌词目标字号，默认单行 62pt、双行 47pt、三行 34pt；空间不足时缩小，低于 32pt 报错 |
| `vertical` | 文本整体在正文剩余高度中的位置，0 为靠上、1 为靠下；默认 0.45 |
| `gap` | 演唱行块之间的间距（pt），单/双行默认 36、三行默认 12 |
| `motifs` | 复用原程序化引擎；每项有效 type + reason，位置尺寸为 0–1；不额外自动插入笔触 |
| `role / reason` | 页用途及理由；存入备注和清单。reason 必填，两者均不自动改变排版 |
| `previewPageIds` | 从实际页计划中选择预览，按原顺序输出；默认取前六页，另加封面 |

歌词原文、假名、罗马音、译文都是 PowerPoint 原生文本框。假名按分词单元定位；原文只在单元之间换行，罗马音与译文独立换行。文本测量使用实际安装字体。字体不嵌入 PPT，跨机器仍需相同字体或重新渲染。

## 检查与证据

构建时阻断：重复/未知行 ID、缺页/重复页、顺序错误、跨段页、不支持的布局、无理由的装饰、基础背景对比度不足、无法容纳的文本、越界文本框。对比度只针对基础底色，纹理覆盖后的实际对比仍需看渲染。

每个 PPT 附 `.manifest.json`（指纹、字体、页 ID 与行 ID 对应、实际字号）和 `.reading.txt`（注音对齐告警）。这些文件不宣称视觉或语言核验完成。

完整渲染：

```bash
python scripts/render_preview.py "<deck.pptx>" --output "<montage.png>"
```

在 `<montage_stem>_slides/` 输出逐页 PNG、后端支持时的 PDF、`render_receipt.json`。每次使用新临时目录，核对图片数等于实际幻灯片数；回执包含本次 PPT 的 SHA-256，防止旧图当新证据。PNG 生成成功不等于已经看过。完整页缩略图检查后，再看长句、深色页与异常注音页的大图。 局部修改仍渲染本次完整文件，复查改动/相邻页与整曲缩略图；其余页面仅能沿用有文件及范围记录的旧检查。首次制作或无旧证据时检查完整范围。文件哈希用于把预览绑定本次文件；回归比较仍应解包比较内容，不用 ZIP 时间戳产生的原始哈希判断功能变化。

## 旧路径与边界

- 原 L1–L8、15 种 motif、Visual Critic 保留于旧路径；v3 不调用旧 critic，也不声称支持全部八种构图。
- 旧 `visual_assets.pageIntents` 使用段名/页序号，未按持久行 ID 绑定；v3 使用独立的 `pages` 字段。
- 日语字典读法和用户罗马音对齐仅是排版辅助，无法代替听原录音；对不上的行保留告警，不编造读音。
- 构图、色彩和节奏需针对歌曲填写。此次《群青》的浅纸色→蓝色→深蓝→回到浅色，是样例的决定，不是所有歌曲的固定模板。
- 旧渲染模块未迁移，但共用的字体检测和注音对齐有修正，旧歌不应被声称为字节完全不变。当前交接包不含白日/うっせぇわ源数据，本轮未重跑它们。

## 导演契约（方法层，版本1）

新建/整体改版需填写 `visual_profile.director`，具体方法见 [references/visual-directing.md](references/visual-directing.md)。它与渲染版本3/4、内容 schema 2.1 分别编号，不能混为一个版本。最小完整数据示例见 `examples/`。

- `version: 1`；`source_fingerprint` 使用 `load_song()` 返回的 meta.fingerprint，不手工编造。
- `brief`：premise、emotional_arc、evidence_basis（lyrics_only / lyrics_and_audio），后者另需 audio_evidence 对象，至少含 recording（录音版本/定位）与 scope（实际检查范围）。
- `timeline`：按源顺序完整覆盖所有演唱行的阶段，每项有 id、line_ids、state、visual_shift、reason。
- `system`：concept、palette_logic、typography_logic、composition_logic、motif_logic、avoid（数组）。
- 每页新增必填 phase_id、role、transition；reason 继续必填。可选 focus_ids 只用于检查，不自动高亮。可选 repeat_of 指向更早的页，并需要 repeat_reason。

构建时如果 director 存在，就检查源指纹、阶段与页面覆盖、页与阶段关系、重复引用；过期计划阻断。没有 director 的旧资料只告警。`python scripts/visual_plan.py "<data.json>" --require-director` 用于新方案的显式检查。校验只证明结构一致，不能证明情绪判断、意象解释或视觉质量。

phase/role/transition/repeat/focus 是方法与追溯信息；v3 的布局、颜色、typeface、尺寸、间距、motif 实际改变图像。v4 另消费 objects、scene_library、scene、text_zone、surface；不消费旧 motifs。动画和精确时间同步未实现。
