# song-study

想学一首歌，你只需要说出它的名字。

剩下的交给 song-study。它自己去查——找到这首歌的歌词，追到最可靠的出处，辨清是哪一个录音版本，给每一个字标上读音，把意思译成你能懂的话，再顺着歌词往下挖：这首歌在唱什么，写给谁，背后发生过什么。

查到的、核验过的、翻译好的，最后都长成你能带走的东西：一份能慢慢读的学习笔记，一页页能翻的讲义，还有一版能跟着唱、跟着看的歌词 PPT。

你不必是日语专家，也不用懂什么文件格式。你只要，知道那首歌的名字。

## 它能给你什么

三种成品，同一条根。

**学习笔记（Markdown）**——歌词、逐字读音、翻译、词汇与语法讲解，还有这首歌的背景故事。适合慢慢读。

**讲义（Word）**——同样的内容，排版成方便打印、方便记笔记的文档。

**歌词 PPT**——可编辑的演示文稿，一页页跟着唱、跟着看。歌词的排版、配色、留白，都按这首歌自己的情绪来设计。

所有内容都出自同一份 `data.json`。你只写一次，剩下的交给脚本——改了歌词就重新生成，不用手工维护三份不同的内容。

## 它是怎么工作的

你说出歌名，它去检索歌词——从官方来源到歌词平台（Genius、uta-net、Musixmatch、QQ 音乐、网易云等），追到最可靠的出处，区分开原文、翻译和注音。接着确认版本、标注读音、翻译意思、写清背景，把每一处的来源和核验状态都记下来。最后，从这份记录生成三种成品。

歌词的来源、版本、读音翻译，以及六项核验的状态，都保存在 `data.json` 里。生成脚本不会替你证明来源或语言是否正确——它们只负责把记录变成成品。

## 想自己动手

如果想让它在你的机器上跑起来：

```bash
pip install -r requirements.txt
python build_all.py "<song-dir>/data.json"
python scripts/validate.py "<song-dir>/data.json" "<song-dir>"
```

生成脚本需要 Python 3.10+；可选的飞书发送脚本用到 tomllib，需要 3.11+。安装时保留完整文件夹：四个 `build_*.py`、`scripts/`、`references/` 和文档一起复制，不要只替换 SKILL.md。产物写在歌曲文件夹里。

## 设计顺序

先按 [视觉设计方法](references/visual-directing.md) 写歌曲理解、美术设定和段落视觉脚本，起草格式见 [视觉脚本格式](references/visual-script-template.md)。颜色、文字与留白可独立构成画面；符号须经过筛选并规定出现/退场。新歌不默认采用场景版，也不要求每页有图。既有 examples 仅作接口示例，不是所有歌曲的画风。

## PPT v3

新日语 PPT 可用 `visual_profile.renderVersion: 3` 和 `visual_assets.pages`。先按 [歌曲视觉导演](references/visual-directing.md) 理解歌曲和安排情绪进程，再按 [PPTX-DESIGN.md](PPTX-DESIGN.md) 写逐页分镜。每页明确行 ID、作用、前后关系、构图、字体类型、颜色与设计理由。新方案使用 director 契约；每页按语义取 1–3 条演唱行。无此开关的旧数据继续用原 L1–L8。

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
