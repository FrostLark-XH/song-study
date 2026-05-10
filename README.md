# song-study

AI 驱动的歌曲学习资料生成器 — Claude Code skill，输出精美排版的 `.md` + `.docx` 双格式。

## 这是什么

给 Claude Code 装一个"学歌助手"技能。你只要说"学一下 tuki. 的 騙シ愛"，Claude 会自动搜索歌词、多源交叉校验、逐句标注发音和翻译、分析语法点和文化笔记、拆解演唱技巧——最后生成两份排版精良的学习资料放在 `E:/song-study/` 下。

## 输出物

每首歌一个文件夹：

```
E:/song-study/{歌手名}_{歌名}/
├── {歌手名}_{歌名}.md      # Markdown — 呼吸感排版、引文缩进、校验标注
├── {歌手名}_{歌名}.docx    # Word — 色彩语义系统、交替行着色、左边框引文
└── gen_docx.py             # 生成脚本（由 Claude 根据本 skill 编写）
```

Markdown 示例：

```
# 歌曲学习：騙シ愛 (Damashiai)

───

## 基本信息
| 项目 | 内容 |
|------|------|
...
```

Word 示例 — 表头用颜色区分信息类型：

| 表类型 | 表头色 | 语义 |
|--------|--------|------|
| 基本信息 | `#D6E4F0` 淡蓝 | 信息、客观 |
| 歌词对照 | `#F5EBE0` 暖米 | 文本、人文 |
| 核心词汇 | `#E8F0E4` 淡绿 | 学习、成长 |
| 语法/文化 | `#EDE8F5` 淡紫 | 分析、思辨 |

## 目录结构

```
skill.md                     # 主文件 — 完整执行流程（~340 行）
scripts/
├── docx_template.py         # Word 生成模板 — create_document / make_table / add_quote / add_singing_tip / add_verification_block
└── feishu_sender.py         # cc-connect 飞书文件发送 — Python urllib 直连，正确处理 CJK 文件名
references/
└── cc-connect-file-send.md  # cc-connect 环境文件发送参考文档
```

### feishu_sender.py

通过飞书 Open API 上传文件 + 发送文件消息。接受文件路径列表作为参数：

```bash
PYTHONUTF8=1 python scripts/feishu_sender.py <file1> <file2> ...
```

- 从 `~/.cc-connect/config.toml` 读取 app_id/app_secret
- 从 session 文件提取当前飞书 chat_id
- 用 `urllib` multipart/form-data 直传，避免 shell 编码损伤 CJK 文件名

## 内容结构

每首歌的资料覆盖以下模块，缺一不可：

1. **基本信息** — 歌名、演唱者、词曲作者、专辑、发行日期、语言、版本（录音室/live/remastered）
2. **背景故事** — 创作动机、过程细节、发行反响、影视/游戏 tie-up（有事实不写套话）
3. **歌词** — 多源交叉验证后的完整歌词
   - 日语歌：三列表格（原文 | 罗马音 | 中文翻译）
   - 英文歌：两列表格（原文 | 中文翻译），逐短句拆分
   - 中文歌：段落排版
4. **语言学习**（外文歌专属）
   - 核心词汇 10–15 个（JLPT 等级标注）
   - 语法点 3–5 个（歌词原句引用 + 结构拆解）
   - 文化笔记（不直译会误解的表达）
5. **演唱技巧** — 音高/节奏/气息/咬字/情绪，问题→方法对照
6. **附录** — 歌词来源 URL、背景信息来源 URL、校验声明

## 设计系统

文档排版不是随便加的格式——每种颜色、每种边框都对应特定的信息类型。

### Markdown 视觉规则

- `#` 标题下方 `───` 分隔线
- `##` 标题前后空行，保持呼吸感
- 歌手原话用 `>` 引文块 + 前后空行
- 校验状态用 `> ✅` 或 `> ⚠️`
- 表格前后各空一行
- 演唱技巧 `→` 分两行，形成视觉对比

### Word 文档视觉规则

- 表头着色：每种信息类型独立颜色（蓝/米/绿/紫）
- 交替行着色：奇数行白底、偶数行 `#F8F8F8`
- 歌手引文：左缩进 0.8cm + 左边框 `#D4A574` 1.5pt + 斜体
- 语法点标题：加粗 + `#B85C3A` 琥珀色
- 演唱技巧整节：`#FFF3E0` 暖金底色
- 校验声明块：`#F8F8F8` 底色 + `#2C3E50` 左边框

### 字体只用系统自带

| 语言 | 正文 | 标题 |
|------|------|------|
| 中文 | SimSun（宋体） | Microsoft YaHei（微软雅黑） |
| 日文 | MS Mincho（MS 明朝） | Meiryo（メイリオ） |
| 英文/罗马音 | Arial | Arial |

禁止使用 Noto CJK、思源系列等第三方字体——系统字体字符覆盖最完整，无缺字风险。

## 歌词验证流程

歌词不能出错。执行流程：

```
WebSearch（多关键词、多语言）
  → WebSearch 聚合摘要（优先利用，不易被拦）
  → WebFetch / curl（抓取 2–3 个来源）
  → 逐句交叉比对
  → 发现出入 → 官方来源 > 大型歌词数据库 > 博客
  → 无法确认 → 标注 ⚠️
```

## Word 生成管线

```
SKILL.md（Claude 执行）
  → 编写 gen_docx.py（import scripts/docx_template.py 函数）
  → python-docx 渲染
  → {歌名}.docx
```

`scripts/docx_template.py` 提供可复用函数：
- `create_document(path)` — 创建文档，设置页边距
- `make_table(doc, headers, rows, header_color, widths)` — 表头着色 + 交替行
- `add_quote_paragraph(doc, text)` — 左边框引文
- `add_singing_tip(doc, name, problem, solution)` — 暖金底色演唱技巧
- `add_verification_block(doc, text)` — 校验声明块
- `set_font(run, cn, en, size, bold, color)` — 中日英字体指定
- `set_cell_shading(cell, color)` — 单元格着色

Python 选用 `python-docx` 而非 JS `docx-js`——对中日文字符的字体回落处理更可靠。

## cc-connect 发送

运行在 cc-connect 环境中时，生成文件后自动推送到飞书。发送使用 Python `urllib` 直连（不用 shell curl——CJK 文件名会被 shell 编码损坏）。详见 `references/cc-connect-file-send.md`。

## 安装

```bash
git clone https://github.com/FrostLark-XH/song-study.git
cp SKILL.md ~/.claude/skills/song-study/SKILL.md
cp -r scripts/ ~/.claude/skills/song-study/scripts/
cp -r references/ ~/.claude/skills/song-study/references/
pip install python-docx
```

触发词：`学歌` `学唱` `这首歌怎么唱` `帮我扒歌词` `歌词` `学一下X的歌` `最近在听X`

## 示例

已生成的学习资料：

| 歌曲 | 语言 | 特点 |
|------|------|------|
| [tuki. — 騙シ愛](tuki._騙シ愛/) | 日语 | TBS 日剧《Caster》主题歌，16 岁创作歌手 |
| [Jekyll & Hyde — Façade](Jekyll_Hyde_Façade/) | 英语 | 音乐剧选段，社会批判主题 |

## 约束

- 歌词绝对不能编造——宁可标注"无法完全确认"
- 发音标注必须能直接跟唱，不用 IPA
- 翻译忠实第一，优美第二
- 不跳过任何步骤
- 纯音乐/无人声曲跳过歌词部分，重点做背景和演奏技巧
- Word 文档必须带颜色语义，交替行着色不能省略
- 字体只许用系统自带，禁止第三方 CJK 字体
- shell curl 不用于飞书发送——用 `scripts/feishu_sender.py`
