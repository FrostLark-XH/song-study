# 场景接口 v4：从分镜到实际画面

仅在设计需要共享物件或场景关系时使用；配色、文字和留白优先的方案可使用 v3，本接口不是新歌默认模式。内容 schema 仍是 2.1，导演契约仍是 1；`visual_profile.renderVersion: 4` 只选择渲染方式。v3 和旧 L1–L8 保留，不强迁移。完整可运行示例：`examples/scene-return/data.json`（自拟窗与茶的短歌）；不要把该示例或《群青》的美术当通用模板。

本接口当前仍要求每页具备 scene，没有显式“该页完全无图”选项。不要用透明占位对象或无关涂鸦满足校验。先按 visual-directing.md 写视觉脚本；混合需求的能力缺口在实施时明确处理，不能反过来改变已经成立的美术意图。

## 数据的三个层次

1. `visual_assets.objects` 定义共享对象。每个对象有 `meaning` 和 `primitives`，说明它从哪些歌词含义而来。一个对象多次出现时复用同一个键；不同实例在场景里用独立 layer ID。
2. `visual_assets.scene_library` 定义环境、对象层次及状态轨迹。每个场景有 `meaning` 和 `layers`。层按数组顺序绘制。
3. `cover.scene` / `pages[].scene` 选择某个场景的一个静态状态、视域与镜头。它们实际改变画面。`visual_event` 写本页看得见的事件或状态；`lyric_basis` 写本页 `line_ids` 支持的解读，不再复制整段歌词。

```json
{
  "objects": {
    "orb": {
      "meaning": "自拟例子的同一个光点，由微弱到清晰。",
      "primitives": [
        {"kind":"ellipse", "box":[-70,-70,70,70], "fill":"D6B46D"}
      ]
    }
  },
  "scene_library": {
    "field": {
      "meaning": "光点在开放空间中逐渐显现。",
      "layers": [
        {"id":"light", "object":"orb", "x":500, "y":500,
         "frames":[{"at":0,"scale":0.3},{"at":1,"scale":1.5}]}
      ]
    }
  }
}
```

以上片段合并到 `visual_assets`，并保留原 `pages`。它不是一份可独立构建的 data.json。新建数据应以完整例子理解字段关系，再针对歌曲重新设计。

## 绘图与状态字段

| 字段 | 实际行为 |
| --- | --- |
| `kind` | `polygon` 多边形、`line` 折线、`rect` 矩形、`ellipse` 椭圆、`wash` 带细颗粒的色块 |
| `points` | polygon / line / wash 使用 `[[x,y],...]`；闭合图形至少 3 点，line 至少 2 点 |
| `box` | rect / ellipse 使用 `[x0,y0,x1,y1]`，后端坐标必须大于前端；不是归一化宽高 |
| `fill / stroke / width / opacity` | 六位 HEX 填色/描边；线宽 .1–60，透明度 0–1；line 必须有 stroke |
| `smooth` | 布尔值，闭合轮廓采用平滑曲线；line 不消费该选项 |
| `seed` | wash 的整数种子；相同数据、软件及绘图尺寸下可重复，不受导出次序影响 |
| layer 的 `x / y / scale / rotation / opacity` | 局部对象放到场景中的位置、比例、角度、透明度；缺省 0、0、1、0、1 |
| `frames` | `at` 在 0–1 严格递增；只支持上列五个变换字段，各字段独立线性插值；没有该字段的节点跳过。进程早于某字段第一个节点时，直接取该节点值；晚于最后节点时取末值。要从 layer 原值保持到中段，必须在 at:0 和保持结束位置显式写出该值 |

对象可围绕局部原点绘制，场景习惯使用 1000×1000 的世界空间。颜色无需局限在蓝色；物件无需是纸张。`wash` 是程序绘图效果，不宣称生成了真实水彩、摄影或高精度人物。

## 页字段

v3 的原文、假名、罗马音、译文排版与 1–3 条演唱行限制沿用；v4 对单字尾行会移动完整注音单元，减少孤立假名，不修改源文。增加：

```json
{
  "text_zone": [0.51,0.17,0.44,0.69],
  "scene": {
    "id":"field", "progress":0.7,
    "viewport":[0.03,0.12,0.43,0.75],
    "camera":[500,500,1.2],
    "state":{"light":{"y":430}}
  },
  "visual_event":"同一光点在更近的观察距离中显现。",
  "lyric_basis":"本页的动作由寻找转为发现，这是设计解读。",
  "visual_link": {
    "from":"earlier-page-id", "mode":"continue", "anchor":"orb",
    "change":"保留光点，推进比例并拉近观察距离。"
  }
}
```

- `text_zone` / `viewport` 均为归一化 `[x,y,width,height]`，必须在画布内。viewport 是实际绘图裁切区域；局部特写可裁切对象，必须看图确认裁切有意且仍可识别。
- `camera` 为世界空间中心 x/y 和 zoom（.2–4），默认 `[500,500,1]`。按 viewport 短边等比缩放，宽视域不会自动拉伸对象。
- `progress` 为这段设计进程的相对位置，**不是演唱时间**。PPT 导出静态帧，无音频同步和逐字动效。
- `state` 可覆盖本页某层的上述五个变换字段。它在轨迹插值后生效，不支持临时改对象 ID 或随意加新字段。
- 画面区与阅读区重叠时，必须显式提供 `surface`，其颜色等于 `background`，后端为阅读区加不透明底。这样基础底色的对比度检查仍有效。不要透过字面铺复杂图像。
- `visual_link.from` 只能指向更早的页 ID 或 `cover`。`mode` 是 `continue / match / cut / return`；除 cut 外，`anchor` 必须是双方场景内存在且状态透明度大于 .01 的共享 object ID。程序不推断隐喻是否成立，也不能只凭透明度判断对象最终没有被裁切/遮挡。
- cover 需要 scene 和 text_zone，不需要 visual_link；留足标题、歌手与副标题的空间。页眉/页脚占顶部约 35–55pt、底部约 504–521pt，正文区和画面设计应避开。
- v4 不消费旧 `motifs`；使用空数组，所有实际插图写进 objects/scene_library。

图像层会栅格化进 PPT；歌词文本保持 PowerPoint 原生可编辑。修改物件形状或运动状态应改 data.json 后重建，不能把背景图层说成全部可逐对象编辑。

## 完整证据

```bash
python scripts/visual_plan.py path/to/data.json --require-director
python build_pptx.py path/to/data.json path/to/deck.pptx
python scripts/render_preview.py path/to/deck.pptx --output path/to/montage.png
python scripts/scene_evidence.py path/to/data.json path/to/deck.pptx path/to/montage_slides --output path/to/evidence
```

最后一步读取现有完整渲染，不重复导出。它拒绝 preview 文件、过期内容/视觉指纹、错误的 PPT 哈希、缺图和不一致的图片哈希。输出整曲、所有阶段的连续页面、全部 `repeat_of` 对照、首尾对照及 `evidence.json`。不能手工修改回执来让旧图通过。

先检查符号本身的造型、作用和必要性，再看整曲与关键大图。场景方案说明物件何时出现/退场、重复如何处理、首尾关系；允许停留与保持。若各页只是同一物件缩放，回查是否应该减少图形或改用纯底文字方案。审美依据以 visual-directing.md 为准，接口字段齐全不证明画面成立。

结构测试：`python -m unittest discover -s scripts -p 'test_*.py'`。持久 ID 另运行 `python scripts/test_line_ids.py`。只改 PPT 时，validate.py 的三格式产物检查仍会提示缺 MD/DOCX；这不代表本次 PPT 构建失败。此范围以内容 schema、visual_plan、PPT manifest 和完整渲染为准，不为消除提示额外生成无关格式。测试、成功导出和 AI 看图各自记录；人工评价、录音检查、读音翻译检查不可混称完成。

## 方法参考与适用边界

本方法参考 [PDoomVideo 的 STORYBOARD](https://github.com/JohnHeibel/PDoomVideo/blob/main/STORYBOARD.md) 与 [ANIMATION_GUIDE](https://github.com/JohnHeibel/PDoomVideo/blob/main/ANIMATION_GUIDE.md) 中的连续叙事组织：共享物件、可见事件、呼应中变化、首尾回收、确定性的状态绘制与边界检查。用于 PPT 的转译是“歌词相对进程上的静态场景”，并未移植其角色、歌词、美术、剧院情节或视频引擎。不要把参考案例的成功当作本 skill 已达到同等视觉质量的证据。
