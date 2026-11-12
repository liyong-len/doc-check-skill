# doc-check

对一组投标文档做格式与内容检查，产出**单文件 HTML 报告**。

可安装到本机的智能体（Claude Code、Codex CLI、WorkBuddy、DSH），也可以当作普通脚本手工调用。
需要 Python 3.9 及以上。

## 它检查什么

检查分两层，来源不同，结论的可信度也不同。

**格式与体例（脚本判定，结果确定）**

抽取文档后由脚本做机械比对，只看文档内部，不引用任何外部依据：

字体一致性、段落格式一致性（对齐/缩进/行距/段间距）、标题层级体例、
图表题注体例、表格体例、列表与编号、引用标记、数字与单位（货币单位、日期格式）、
主体名称（写法一致性）、主体串写（疑似混主体）、术语与缩写。

这一层是确定性的：同样的文档在任何智能体里跑，`consistency.json` 完全一致。

**内容与逻辑（智能体判定）**

智能体读脚本抽好的文本分片，按 `references/content-rules.md` 判断这九类问题：

错别字用词、标点格式、前后矛盾、主体名误用、引用张冠李戴、待补充内容、
数字逻辑、表述不清、术语一致性。

这一层由模型完成，同样的输入可能得到不同的结论。

## 它不做什么

- **不修改任何原始文档。** 全部脚本只读输入文件。
- **不联网，不调用外部大模型 API，不做 OCR。** 扫描版 PDF 无法检查，会如实列入「未能检查的文件」。
- **不核实外部事实。** 企业名称在现实中是否真实存在、引用的文献是否真实存在、
  引用的法规是否现行有效，这三件事工具都无从确认。凡是结论依赖它们的，
  一律标注「疑似 · 需人工核实」，不会伪装成确定结论。
  「同一主体出现多种名称写法」可以确定判定；「疑似把两家企业写混」不能。

报告末尾会复述这条能力边界。

## 安装

### 一行装完

不需要 clone 仓库。macOS / Linux / Windows 上的 Git Bash：

```bash
curl -fsSL https://raw.githubusercontent.com/liyong-len/doc-check-skill/main/install/bootstrap.sh | bash
```

Windows（PowerShell 5.1 或 pwsh 7）：

```powershell
irm https://raw.githubusercontent.com/liyong-len/doc-check-skill/main/install/bootstrap.ps1 | iex
```

引导脚本做两件事：把仓库下载到 `~/.doc-check/repo`（Windows 是 `%USERPROFILE%\.doc-check\repo`），
然后调用下面的安装器完成安装。**装完别删这个目录**——虚拟环境建在里面，
技能目录的 `python-path.txt` 指向它。

国内网络访问 GitHub 不稳时可能要多跑几次。也可以用
`DOC_CHECK_REPO_URL` 指向自己的镜像。

### 手动安装

已经 clone 了仓库的话，直接跑安装器：

Windows：

```powershell
powershell -ExecutionPolicy Bypass -File install/install.ps1
```

macOS / Linux：

```bash
bash install/install.sh
```

重跑安装器覆盖已安装的副本（等价于直接再跑一次，`--update` 只是把意图写出来）：

```bash
bash install/install.sh --update
```

### 装之前先看一眼

三个选项让「装到哪儿去」这件事变得没有歧义：

```bash
# 只打印将写入的目录，一个文件都不写
bash install/install.sh --dry-run

# 改「~ 展开到哪个根目录」，不必改 HOME/USERPROFILE
bash install/install.sh --target-root /tmp/scratch-home

# 看机器上现在是什么状态：家目录根、各智能体目录、有没有残留
bash install/install.sh --status
```

`--status` 的最后一行是机器可读的结论：`doc-check 安装状态：干净`，
或者 `doc-check 安装状态：残留 N 处`（并列出残留目录的绝对路径）。
检测是全局的（PATH 上的 `claude` 命令与家目录无关），安装不是——
安装器因此在动手之前就把目标路径打印出来，装完再回显一次。

没给 `--target-root`（也没有 `DOC_CHECK_TARGET_ROOT`）时，安装器写的就是你的
真实家目录。动手之前它会先打印一段横幅，把要写的绝对路径一条条点名：

```
⚠ 即将写入你的真实家目录
  Claude Code -> C:\Users\<你>\.claude\skills\doc-check
  （若这是误操作，按 Ctrl-C 取消，或用 --dry-run 先看会写到哪里）
```

横幅是提示，不是闸：一条命令照常装好，不需要任何额外参数。
`install.sh` 与 `install.ps1` 调用的是同一份代码，横幅因此是同一段文字。

安装器会依次做完这些事：

1. 挑一个可用的 Python。候选顺序两个安装器完全一致：
   `py -3.12`、`py -3.11`、`py -3.13`、`python3.12`、`python3.11`、`python3.13`、
   `python3`、`python`、`py -3`，要求 3.9 及以上。
   优先 3.11 / 3.12，是因为 `lxml` 与 `pdfplumber` 在最新的 Python 上常常没有预编译轮子。
   判定只看退出码与标准输出里的版本号：解释器往 stderr 写一句提醒，不影响它被选中。
2. 在**仓库根目录**建 `.venv` 虚拟环境。
3. 按 `requirements.txt` 装四个依赖：`python-docx`、`openpyxl`、`pdfplumber`、`lxml`。
4. 探测本机装了哪些智能体，把 `SKILL.md`、`references/`、`scripts/`、`requirements.txt`
   复制到各自的技能目录，并写入该智能体的 `AGENT.md`、`AGENTS.md` 与 `python-path.txt`。
   复制过去之前，入口文件 `SKILL.md` 会被改写成绝对路径：
   命令里的解释器取自 `python-path.txt`，脚本取自技能目录本身。
   仓库里删掉的文件会从技能目录里清掉，不会留下过时的脚本。
5. 打印每个已安装智能体的用法；没检测到的智能体会被跳过并列出。

两个安装脚本只在 shell 语法上不同，行为一致：装到智能体目录那一步由
`install/install_skill.py` 完成，两边调用的是同一个文件。

各智能体的技能目录与核实状态：

| 智能体 | 技能目录 | 状态 |
|---|---|---|
| Claude Code | `~/.claude/skills/doc-check` | 已确认 |
| Codex CLI | `~/.codex/skills/doc-check` | 已确认 |
| WorkBuddy | `~/DoubaoWork/skills/doc-check` | 路径已确认，技能文件格式待验证 |
| DSH | `~/.dsh/skills/doc-check` | 路径尚未确认，探测到才会安装 |

你的智能体没被检测到时用通用接入方式：把 `install/adapters/generic.md` 里的片段
与仓库的绝对路径贴进你的智能体项目说明。

装完可以先做一次环境自检：

```bash
python scripts/check_env.py
```

## 用法

在已装技能的智能体里说「检查这几个文档」并给出文件路径；
Claude Code 与 Codex CLI 还可以直接用 `/doc-check`。

命令行手工跑是三段式，中间那一步由智能体（或你）完成。

命令里的 `python` 必须是**装了四个依赖的那个解释器**：安装器建好的虚拟环境在仓库根目录的
`.venv` 里（Windows 是 `.venv\Scripts\python.exe`，macOS / Linux 是 `.venv/bin/python`）；
每个已安装的技能目录里还有 `python-path.txt`，写的就是它的绝对路径。
系统里没装 `python-docx` 的 `python` 会直接 ImportError。
下面的命令块里用 `.venv` 里的解释器示意；换机器时把它换成对应的路径即可。

```bash
# ① 抽取与确定性检查
.venv/Scripts/python.exe scripts/prepare.py --files 投标文件.docx 报价表.xlsx --depth standard --work .doc-check-work
# ② 读 .doc-check-work/chunks.json 与 references/content-rules.md，把结论写进 .doc-check-work/findings.json
# ③ 渲染报告
.venv/Scripts/python.exe scripts/render.py --work .doc-check-work --out report.html
```

macOS / Linux 上第一行换成 `.venv/bin/python`。

阶段①产出四个 JSON：`docs.json`、`consistency.json`、`chunks.json`、`manifest.json`。
抽取失败的文件会列在 `manifest.json` 的 `failures` 里，报告的 §0 会点名说明。

复查模式（改完一轮再查，只看新增、已修复与未修复）：

```bash
.venv/Scripts/python.exe scripts/render.py --work .doc-check-work --out report.html --baseline .doc-check-work/last-findings.json
```

## 深度档位

| 档位 | 覆盖 |
|---|---|
| quick | 阶段①全量确定性检查 + 阶段②只做错别字与标点扫描 |
| standard | 阶段①全量确定性检查 + 阶段②九类语义检查全做（默认） |
| deep | 阶段①全量确定性检查 + 阶段②逐段细读，邻接窗口更大，跨片对照加强 |

## 输出

单个 HTML 文件，CSS 内联，无外部资源，可离线打开、邮件转发、长期归档，含打印样式。

章节：§0 检查范围与未能检查项、§1 结论概览、§2 硬伤速览（P0/P1）、§3 按文件明细、
§4 一致性差异、§5 待补充与待核实、§6 复查对比（带 `--baseline` 时才有）、§7 附录。

## 目录结构

```
SKILL.md            智能体主指令
AGENTS.md           通用接入说明
scripts/            抽取、统计、分片、渲染
references/         语义规则、格式规则、严重级别与 schema、报告规范
install/            安装器与智能体适配表（install_skill.py 是两个安装器共用的安装阶段，
                    bootstrap.sh / bootstrap.ps1 是一行安装的引导脚本）
tests/              单元测试、端到端测试、样本生成、金标评估
```

## 开发

```bash
.venv/Scripts/python.exe -m pytest -v          # macOS / Linux 用 .venv/bin/python
.venv/Scripts/python.exe tests/make_samples.py # 重新生成 tests/samples/ 下的样本
```

模型层不进 CI（输出有不确定性）。评估方法：准备一批人工标注的样本文档，
统计模型在样本上的召回率与误报率，见 `tests/gold/README.md`。

## 许可

MIT
