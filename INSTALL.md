# 安装

完整入口及命令见[README.md](README.md)，Agent必须完整阅读[SKILL.md](SKILL.md)与[FOR_AI.md](FOR_AI.md)。

1. 克隆 `https://github.com/mcs391/biaoshu-review.git`，或下载仓库ZIP并解压完整目录。
2. 使用Python 3.12（已测试版本），建议建立独立虚拟环境。
3. 运行 `python -m pip install -r requirements.txt`。
4. 运行 `python scripts/check_env.py`；可选pdftotext缺失时允许回退，但不等于扫描图片已经被读取。
5. 运行 `python tests/test_review_v3.py` 验证关键防漏功能。
6. 让Agent读取本地入口，再提供标书路径。不要只复制SKILL.md，脚本、规则和references也必须齐全。

如Agent代装系统软件/依赖，应先告知用户并征求同意；普通审核不包含自动安装或代码自动更新。
不要在同一Agent中同时启用两份相同name的旧版和新版，避免路由不确定；保留旧版备份后按工具规则切换。
