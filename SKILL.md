---
name: song-study
description: 用户明确要求学唱歌曲、制作歌词学习资料或修改现有资料时使用。由同一 data.json 生成 MD、DOCX、可编辑 PPTX，记录版本、来源和分项核验；PPT 先确定整曲氛围、美术设定与段落视觉脚本。普通听歌聊天或仅提到歌名不触发完整生成。
---

# 歌曲学习

先完成用户指定范围。完整学歌任务默认交付 MD、DOCX、PPTX；单改文字、PPT 或只写设计时不扩展任务。已确认的偏好与授权沿用，内部试排后自主继续；确有影响内容的版本歧义才集中确认。

## 按需读取

读本文件后，只打开本次需要的材料；不预读全部文档、示例与源码。

| 本次工作 | 读取 |
| --- | --- |
| 找歌词、确认版本、复核内容或更新核验状态 | [来源与核验](references/sources-and-verification.md) |
| 新建/迁移数据、编辑字段或维护行 ID | [数据契约](references/data-contract.md) |
| 写背景、读音翻译、词汇语法或技巧 | [学习内容](references/learning-content.md) |
| 新歌 PPT、整曲改版或调整美术方向 | [视觉设计](references/visual-directing.md) |
| 把设计转成可执行 PPT 参数 | [PPT 接口](PPTX-DESIGN.md)；仅采用 v4 时再读 [场景接口](references/scene-contract.md) |
| 需要草案格式 / 明确通过 cc-connect 发送 | 分别读 [草案格式](references/visual-script-template.md) / [发送说明](references/cc-connect-file-send.md) |

局部颜色、溢出修改只查相关接口与相邻页；不要重读整曲设计流程。示例仅在字段用法不清楚时查看一个相关示例。脚本优先直接运行，失败后定位相关代码。省 token 优先减少重复读取、搜索与报告；背景解释深度、必要语言检查和视觉表达按用户目标保留。

## 不省略的底线

- 先识别歌曲与录音版本。未指定时采用录音室完整版并注明；不把 live、翻唱与原版证据混用。歌词来自实际读取的文本，模型记忆只用于定位，不能补写缺行。
- 内容、来源、核验与正式视觉计划保存在同一 `data.json`；三格式消费同一 `load_song()`。生成后不手改某份成品造成漂移。
- 行 ID 持久化：纠错、换序、跨段移动均不改 ID；新增行用未使用 ID，重复副歌每次出现各有 ID。旧元组兼容保留，不强迁移冻结资料。
- 分开记录版本、原文、注音翻译、结构、渲染、视觉六项检查及使用范围。引用关联、实际比对、生成、渲染、看图分别有证据；缺证据就保留待核验，程序通过不能代替语言或审美判断。
- 查到来源不等于允许全文再分发；遵守当前环境的版权与访问规则。不能获取全文时说明缺口，交付可用来源与允许的学习材料，不生成空壳，不保证每次一定取得歌词。
- 没有听过指定录音，不写已确认的演唱读法、音域、配器、时间点或 BPM。事实、作者自述、听众观点与设计解读分开写。

## 执行与节省上下文

1. **确定范围与现状。** 新歌先定位版本；现有资料先运行下面的摘要命令，再按行/段读取。整曲理解、完整性核验与新视觉方案仍须阅读全曲原文，不能用摘要替代。
2. **复用可追溯证据。** 先列研究问题，合并独立查询，维护一份“结论—证据—待查缺口”的简洁记录；已有可靠结论复用，后续搜索集中补缺口，避免反复读同一资料、重复分析、多份相同报告。版本相同、内容未变且证据可查时沿用，不重复搜索；只有缺失、冲突、过期或本次改变的部分再查。不要把“已记录”自动升级为“已核验”。
3. **编辑与记录。** 更新必要字段及受影响检查。文本变更先核对相关原文/读音/译文、重复关系与覆盖，再更新核验指纹；不只刷新指纹来消除告警。段落/分页变动检查覆盖与顺序；视觉改动不重查无关歌词。
4. **设计与生成。** 新 PPT 按歌曲理解→美术设定→段落脚本→少量试排→整曲生成。颜色、文字、留白可独立成立；符号先规定依据、形态、出现/退场。正式参数写回数据后构建。
5. **检查与交付。** 修复任务范围内的 error，逐项处理或说明 warning。首次完整制作检查完整覆盖并渲染实际成品；局部修改重新渲染、查改动页和相邻页及整曲缩略图，沿用未改变且有记录的检查范围。无法渲染或看图就保留待核验。仅修改内容/文档不跑全部引擎回归；改变引擎才跑相关回归。

完整研究保留必要深度，局部修改只复核受影响内容；不能为了省 token 提前结束关键检索、压缩有价值的背景内容或省略必要核实。

摘要工具只读数据，不联网、不改状态：

```bash
python scripts/song_context.py "<song-dir>/data.json"
python scripts/song_context.py "<song-dir>/data.json" --line "<persistent-id>"
python scripts/song_context.py "<song-dir>/data.json" --section "<exact-section-name>"
```

## 构建命令

在技能目录运行。新建/整曲改版的完整页计划构建前查导演契约；纯设计草案不运行要求完整页面的校验。

```bash
python scripts/visual_plan.py "<song-dir>/data.json" --require-director
python build_all.py "<song-dir>/data.json"
python scripts/validate.py "<song-dir>/data.json" "<song-dir>"
```

仅更新 PPT 用 `build_pptx.py`，仅 MD/DOCX 用对应的 `build_md.py` / `build_docx.py`。校验器会查三格式存在性；仅改单格式时如实说明另两格式未生成，不为了消除范围外提示扩展工作。

```bash
python build_all.py "<song-dir>/data.json" --preview
python scripts/render_preview.py "<actual-deck.pptx>" --output "<montage.png>"
python scripts/render_docx.py "<actual-docx.docx>" "<preview-dir>"
```

`--preview` 写抽样 PPT 到 `_preview/`；正式交付用完整成品渲染。PPT 渲染需 PowerPoint COM 或 LibreOffice；DOCX 工具需 Windows Word COM。字体按实际安装情况处理，不保证跨机不换字体。三格式逐个原子写入，整组不是事务；失败时识别成功/失败项，重建一致批次后再交付。

最终回复只给文件、实际完成的检查和重要缺口。过程报告只保留一次必要记录；复用机器已有回执，不重复写多份相同验收表。
