# biaoshu-review

供具备本地文件读写能力的 AI Agent 使用的标书审核工作流。当前发布版 **v3.0**。
程序负责提取、索引、扫描、报价归组、版本核验和检查完成度；Agent负责读原文、看证书图片及判断条款适用性。
这不是一键自动判定废标的软件，不保证零遗漏，也不替代采购评审决定。

## 下载与安装

```bash
git clone https://github.com/mcs391/biaoshu-review.git
cd biaoshu-review
python -m venv .venv
```

激活虚拟环境：Windows PowerShell执行 `.venv\Scripts\Activate.ps1`；macOS/Linux执行 `source .venv/bin/activate`。
如无法激活，可直接使用虚拟环境中的Python运行以下命令。

```bash
python -m pip install -r requirements.txt
python scripts/check_env.py
python tests/test_review_v3.py
```

已在Python 3.12下测试。PDF文字提取可选安装Poppler的pdftotext，未安装会回退到pypdf。
旧版.doc先保留原件转换为.docx或PDF；扫描件/证书图片仍需Agent视觉读取或合适的OCR辅助，未包含自动OCR模型。

其他Agent不必依赖特定平台插件。支持本地skill的工具可以把整个仓库放入它支持的skill目录；
不支持skill安装的工具也可以直接读取仓库中的说明执行。安装目录由具体工具配置决定，不要复制本机用户路径。

## 发给其他Agent的使用指令

```text
请完整阅读 <biaoshu-review绝对路径>/SKILL.md 和 FOR_AI.md，
按其中路由读取所需 references，首次先运行 scripts/check_env.py。
使用本仓库工作流核对我提供的招标文件及签章前Word投标文件。
同品牌型号必须反向归组，图片节能证书逐型号查看原图，所有事实提供文件及行号/图片证据。
使用版本缓存与分块读取节省Token，但不减少检查覆盖；未完成项不得写成已通过。
默认不检查投标人的实际签章，不改原文件，不上传项目资料。
```

## 两种工作模式

### 只解读招标文件

```bash
python run_pipeline.py prep "招标文件.docx" --outdir "workspace/project-v1"
# Agent读取原文、图片及对应reference，写同目录下“招标文件.工作区.md”
python run_pipeline.py verify "workspace/project-v1/招标文件.工作区.md"
```

首次verify会创建逐命中处置台账并因pending停止，这不是安装失败。
Agent需逐条核查并登记纳入/排除/重复关联，再重跑。详见 [SKILL.md](SKILL.md)。

### 全量核对投标文件

```bash
python run_pipeline.py bid-init "招标文件.docx" --bid "qualification=资格.docx" --bid "technical=技术.docx" --bid "price=报价.docx" --project "项目名称" --bidder "投标公司" --lot "标项1" --outdir "workspace/project-v1"
```

生成 `review.json`、d1/d2等文件目录、原图、内容索引和报价归组底稿。
Agent必须按 [投标审核规范](references/bid-review.md) 完成证据与专项台账。

```bash
python run_pipeline.py bid-verify "workspace/project-v1/review.json"
python run_pipeline.py verify "workspace/project-v1/d1/招标文件.工作区.md" --review "workspace/project-v1/review.json"
```

输出多sheet Excel和Markdown工作区。发现问题可以完成审核并保留风险；重要内容尚未核实则不能称为全量完成。
不提供“签章终稿验签”模式：本版按签章前Word内容审核，但必需表单及原厂/第三方证明仍需核验。

## 核心改进

- 品牌+型号反向归组，不因名称或台/套不同跳过；重复型号即使同价也核配置。
- 报价漏行、未识别表格、定制型号列待复核；逐行数量与金额检查不替代总价/限价核对。
- 正文与清单、售后时限、质保范围、工期、资格和声明函纳入必查专项。
- [图片节能证书](references/energy-certificates.md)：精确型号/后缀、范围、主体、有效期及附件；看不清不猜。
- [Token优化](references/token-efficiency.md)：一次提取、按需读取、内容指纹、变更索引；不自动复用审核结论。
- 逐命中处置和证据关卡，缺步骤或旧版本不能直接生成完成报告。

## 项目结构

```text
SKILL.md / FOR_AI.md          Agent入口及操作规范
run_pipeline.py              prep / verify / bid-init / bid-verify
scripts/                     提取、扫描、版本缓存、报价及完成度检查
references/                  商务/技术、投标核对、节能证书、Token规范
data/keywords.json           公共线索词库
tests/                       合成样例及防漏回归测试
requirements.txt             Python依赖
.github/workflows/ci.yml      Windows/Linux测试
```

## 更新、隐私与验证

更新前保存本地修改，再执行 `git pull --ff-only`，重新安装依赖并运行测试。
规则变化会使旧审核缓存失效。复核新文件请使用新的项目版本目录；可加 `--previous "上一轮/review.json"` 生成差异索引。

```bash
python tests/test_smoke.py
python tests/test_qa_full.py
python tests/test_review_v3.py
```

仓库只含程序、规则及虚构测试；真实标书、证书、报价、审核结果和本地私有词库不应提交。
`.gitignore`不是充分的隐私保证，提交前还须检查暂存文件。词库入库和外部贡献必须分别获得明确授权。
程序不自带云端模型服务；使用Agent读取标书时，数据是否发送给模型服务取决于该Agent的部署和隐私设置。

代码按 [MIT许可证](LICENSE) 分发，保留已有版权与许可声明。
