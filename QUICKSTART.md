# 快速开始

先按[README.md](README.md)安装依赖，然后把[使用指令](README.md#发给其他agent的使用指令)发给具备本地文件及图片读取能力的Agent。

只分析招标要求：`python run_pipeline.py prep "招标.docx" --outdir "workspace/demo-v1"`。

同时核对投标文件：

```bash
python run_pipeline.py bid-init "招标.docx" --bid "qualification=资格.docx" --bid "technical=技术.docx" --bid "price=报价.docx" --project "示例项目" --bidder "示例公司" --lot "1" --outdir "workspace/demo-v1"
```

初始化只是取数与建台账，之后仍需Agent按SKILL执行完整核对。
`bid-verify`或`verify`提示pending/未完成时应补核证据，不应删除条目、修改计数或编造通过状态。

试跑虚构文件：`python run_pipeline.py prep tests/fixtures/sample_tender.docx --outdir workspace/demo-tender`。
