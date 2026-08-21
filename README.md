# 📋 标书审核全流程 Skill

> **biaoshu-review** — 面向投标人的招标规则、投标文件与签章终稿一体化审核工具。

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## ✨ 能做什么

本项目把“AI 语义判断”与“程序化防漏校验”组合为完整审核流程，支持三种模式：

| 模式 | 输入 | 核心检查 | 交付 |
|---|---|---|---|
| **规则审标** | 招标文件 | 废标项、评分项、证明材料、▲/★参数、时间节点、合同要点 | Markdown + Excel |
| **投标文件复核** | 招标文件 + 资格/商务技术/报价 | 实质响应、跨文件勾稽、数量金额、品牌型号、声明函 | Markdown + Excel + 一致性结果 |
| **签章终稿复核** | 招标文件 + 签章 PDF | 签名域、ByteRange、签后追加、重复文件、证据链 | Markdown + Excel + JSON |

### 关键能力

- **废标与评分不漏项**：先生成带行号原文，再结合判词库、专项规则和程序护栏复核。
- **同品牌同型号反向归组**：即使产品名称、单位不同，也按“品牌＋型号”继续检查同型号异价风险。
- **证据链核验**：区分原厂承诺、投标人承诺、商品页、已购延保与已激活凭证。
- **签章终稿十检**：检查 PDF 可读性、签名域、覆盖范围、签后追加字节、内容重复；不把本地结构检查误写成平台 CA 验签通过。
- **可追溯输出**：每项结论回链至 `lines.txt` 行号；生成可筛选、多 Sheet 的 Excel 清单。

---

## 🚀 快速开始

### 1. 获取项目并安装依赖

```bash
git clone https://github.com/mcs391/biaoshu-review.git
cd biaoshu-review
python scripts/check_env.py
pip install -r requirements.txt
```

### 2. 审招标文件

```bash
# 取数、判词扫描和候选词扫描
python run_pipeline.py prep <招标文件.docx 或 .pdf>

# AI 根据 SKILL.md 形成 workspace/<项目>.工作区.md 后，运行护栏并输出 Excel
python run_pipeline.py verify workspace/<项目>.工作区.md
```

### 3. 审签章终稿

```bash
python run_pipeline.py signed <资格审查.pdf> <商务技术.pdf> <报价.pdf> \
  --out workspace/<项目>.signed_package.json
```

### 4. 交给本地 AI Agent

将下列文字与文件一起发送给支持本地文件的 AI Agent：

```text
请完整阅读 <biaoshu-review绝对路径>/SKILL.md，
再按其中的工作流审核我提供的招标文件和投标文件。
首次先运行 scripts/check_env.py；所有结论必须给出行号证据。
```

详细安装说明见 [INSTALL.md](INSTALL.md)，最短操作路径见 [QUICKSTART.md](QUICKSTART.md)，AI 执行手册见 [FOR_AI.md](FOR_AI.md)。

---

## 📂 项目结构

```text
biaoshu-review/
├── README.md                         # 本使用说明
├── SKILL.md                          # Skill 定义与完整审核流程
├── FOR_AI.md                         # 给 AI Agent 的操作手册
├── QUICKSTART.md / INSTALL.md         # 快速开始与环境安装
├── ARCHITECTURE.md                    # 方法与架构说明
├── CHANGELOG.md                       # 更新记录
├── run_pipeline.py                    # 一键编排：prep / verify / signed
├── scripts/
│   ├── extract_text.py                # Word/PDF → 带行号文本
│   ├── scan_keywords.py               # 判词扫描
│   ├── check_coverage.py              # 命中覆盖护栏
│   ├── check_bid_price_consistency.py # 品牌＋型号反向归组与异价检查
│   ├── inspect_signed_bid_package.py  # 签章 PDF 结构与重复内容检查
│   └── build_excel.py                 # Markdown 清单 → 多 Sheet Excel
├── data/
│   └── keywords.json                  # 开源判词库
├── references/
│   ├── commercial/                    # 商务、评分、证明、时间、合同
│   ├── technical/                     # 技术实质响应、评分、偏离
│   └── bid-package/                   # 报价一致性、证据链、签章终稿
├── agents/
│   └── openai.yaml                    # Codex Skill 元数据
├── tests/                             # 回归测试与合成样本
└── .github/workflows/ci.yml           # 自动化测试
```

---

## 🔒 审核边界

1. 输出事实、清单和风险提示，不替投标人作“投/不投”决定。
2. 废标风险、评分项与中标后合同义务必须分开记录。
3. 本地 PDF 检查不替代采购平台 CA 验签、上传、加密、解密或外部信用查询。
4. 用户标书、报价、公司资料、工作区产物和本地词库均不应提交到仓库。

---

## ✅ 验证状态

- 既有流程回归：**61/61 通过**
- 签章检查回归：**4/4 通过**
- Skill 结构校验：**通过**

当前版本：**v0.2.0**。具体变更见 [CHANGELOG.md](CHANGELOG.md)。

## 📄 许可证

[MIT License](LICENSE)

