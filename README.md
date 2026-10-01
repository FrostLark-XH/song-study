# song-study

从同一个 `data.json` 生成 Markdown 学习资料、Word 文档和可编辑歌词 PPT。歌词来源、版本、读音翻译及六项核验状态记录在数据中；生成脚本不会自动证明来源或语言正确。

## 安装与生成

保留完整文件夹：四个 `build_*.py`、`scripts/`、`references/` 和文档都要一起复制。不要只替换 SKILL.md。生成脚本需 Python 3.10+，可选飞书发送脚本使用 tomllib，需 3.11+。

```bash
pip install -r requirements.txt
python build_all.py "<song-dir>/data.json"
python scripts/validate.py "<song-dir>/data.json" "<song-dir>"
```

产物写在歌曲文件夹中。只改歌词内容时编辑 `data.json`，随后重新生成；不手工维护三份不同内容。

## 设计顺序

先按 [视觉设计方法](references/visual-directing.md) 写歌曲理解、美术设定和段落视觉脚本，起草格式见 [视觉脚本格式](references/visual-script-template.md)。颜色、文字与留白可独立构成画面；符号须经过筛选并规定出现/退场。新歌不默认采用场景版，也不要求每页有图。既有 examples 仅作接口示例，不是所有歌曲的画风。

## PPT v3

新日语 PPT 可用 `visual_profile.renderVersion: 3` 和 `visual_assets.pages`。先按 [歌曲视觉导演](references/visual-directing.md) 理解歌曲和安排情绪进程，再按 [PPTX-DESIGN.md](PPTX-DESIGN.md) 写逐页分镜。每页明确行 ID、作用、前后关系、构图、字体类型、颜色与设计理由。新方案使用 director 契约；每页按语义取1–3条演唱行。无此开关的旧数据继续用原 L1–L8。

```bash
python build_pptx.py "<song-dir>/data.json"
python build_all.py "<song-dir>/data.json" --preview
python scripts/render_preview.py "<deck.pptx>" --output "<montage.png>"
```

`build_all --preview` 只写 `_preview/` 下的抽样 PPT，保留完整成品。最终检查要渲染完整 PPT，并查看逐页图片；本次渲染回执包含页数、后端、PPT 哈希，避免混用旧预览。

PPT 渲染需要 Windows PowerPoint COM 或已安装的 LibreOffice `soffice`。字体检测支持 Windows Fonts 与 Fontconfig。推荐安装 Noto Serif CJK JP、Noto Sans CJK JP、Noto Sans CJK SC；罗马音使用已安装的等宽字体。没有可用字体会明确报错。字体不嵌入 PPT，不同机器可能换字体；交付 PDF 可固定当前预览外观。Word 字体替换由 Word/渲染软件负责。

## 校验与边界

```bash
python scripts/test_line_ids.py
python scripts/test_editorial.py
python scripts/test_visual_plan.py
```

- `validate.py` 检查数据和产物覆盖，error 阻断，warning 需阅读。来源引用关联与实际文本比对是独立指标。
- v3 额外检查逐页覆盖、顺序、对比度、文本框边界；输出 `.manifest.json` 与 `.reading.txt`。
- v3 当前只支持日语。其他语言保留旧路径，本次未扩展或验收其渲染能力。
- 一份正式构建由多个单文件原子写入组成，整组三格式不是事务。失败时查清成功/失败项后重建，不把混合批次当最终产物。
- 旧验收日志是对应日期的历史记录；不能当作新版视觉或新数据的验收结果。

使用流程见 [SKILL.md](SKILL.md)，按任务读取对应参考。已有数据可先用 `python scripts/song_context.py "<data.json>"` 查看摘要，再用 `--line` / `--section` 定位；完整设计仍须读全曲。PPT 字段以 [PPTX-DESIGN.md](PPTX-DESIGN.md) 为准。

新歌或整曲改版，生成前运行 `python scripts/visual_plan.py "<data.json>" --require-director`。三个自拟短歌示例位于 examples/；用于演示不同设计方向，不是所有歌曲的模板。

## 场景版 v4

新日语 PPT 可使用共享物件、场景轨迹、镜头与静态页之间的承接；方法见 `references/visual-directing.md`，字段见 `references/scene-contract.md`。`examples/scene-return/data.json` 是可运行的自拟短歌，v3 示例与旧渲染仍保留。整曲证据用 `scripts/scene_evidence.py`，不自动给审美通过结论。

```bash
python build_pptx.py examples/scene-return/data.json scene-example.pptx
python -m unittest discover -s scripts -p 'test_*.py'
python scripts/test_line_ids.py
```
