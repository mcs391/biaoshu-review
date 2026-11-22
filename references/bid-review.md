# 签章前 Word 全量核对

适用：用户同时提供招标与已编制的投标文件。先prep解析招标要求，再bid-init建本轮台账；不能只审招标要求就回答投标文件无风险。

## 审核矩阵（每个专项必须处置）

| stage键 | 必查内容 |
|---|---|
| requirements | 所有资格、符合性、实质性要求、评分梯度、普通参数、合同响应；引用附表跟进；▲/★意义以本招标解释为准 |
| qualification_forms | 必需表单和材料齐全；名称、项目/标项、主体、授权人、资格范围、日期；不检查投标人实际签章。缺整份承诺函不等于尚未签章 |
| price_math | 所有数量×单价、合价累计、总报价/大写、限价、缺漏与重复、税费及报价修正规则。非数值必须登记，不能按0处理 |
| price_groups | 品牌+型号全量归组，再按单位辅助。名称/单位不同不能跳过。定制、项/批、不同面积需范围证据；异价不自动判废标 |
| cross_documents | 招标清单、货物清单、技术响应、报价、产品/中小企业声明逐项核名称、品牌、型号、数量、单位、制造商；映射不明不能按顺序强配 |
| narrative_vs_list | 全文配置、配发签收表、序列号范围、设备尺寸、云资源CPU/内存/数据库、授权数量与清单一致；发现PDA20对10等需双方原文 |
| energy | 适用强制节能范围的每个产品对应图片证书；按energy-certificates.md执行 |
| certificates | 实际原图等级、主体、范围、编号、日期和附件；禁止只读标题/缩略图；OCR与原图不一致以清晰原图复核，不能猜 |
| warranty | 原厂/集成商/第三方分别核；硬件、软件、云资源、授权和维护分项；起算点及免费期间；延保环境、激活、限额、费用；投标人承诺不能替代原厂证明 |
| service_times | 响应、远程、到场、修复、替换分别比较，严重/一般故障、工作日/自然日区别；不可将不同事件时间机械判冲突 |
| schedule | 总工期、安装、调试、试运行、验收的顺序、重叠及依赖，进度图/表与正文一致，不凭未知人数算必然不可行 |
| declarations | 中小企业行业/主体/统计年、人员/营收/资产口径、本国产品声明范围、制造商对应；社保人数与从业人数不同不直接定虚假 |
| claims | 绝对化宣传、无证性能、未定选型、备选品牌、未经授权变更及超清单承诺；指出依据不足，不擅自认定造假 |
| final_regression | 修改关联项复查、最新版本确认、既有问题是否闭环、所有未知是否披露；不是签章/PDF终审 |

## review.json 填写契约

bid-init生成每个documents的固定目录与内容索引。源文件和提取产物只读。
维护状态字段，不删除固定内容块/图片/告警来达到完成度。

- stages：每个stage填status=done/not_applicable、reason、evidence数组；不适用也须解释项目依据。
- documents.*.chunks：80行一块，status=reviewed/excluded + reason；不能只搜关键词标整块已读。
- documents.*.assets：每个媒体/嵌入对象status=reviewed/excluded + reason。
  同图指纹可共享一次识别，但每个出现位置保留映射；无关logo等可有理由排除。
- alerts：文本框之外的控件/修订/外链/嵌入对象/PDF页等需人工核实，status=reviewed + reason。
  图片提取成功不表示视觉复核完成；未知格式需渲染或列未完成。
- documents.*.price_group_reviews：每个重复品牌型号组status=reviewed、reason、evidence；即使单价相同也需核名称/配置，不能只处理异价组。
- requirements：id、category、tender证据、bid证据、status=matched/risk/not_applicable/unverified、reason。
  风险与待核实分开；matched必须有双向证据。缺材料的risk注明已检查范围；unverified不能通过完成关卡。
- products：清单逐行id、name、brand、model、quantity、unit、manufacturer、evidence、energy_applicability=required/not_required/unknown、basis。
  连续重复行不可合并丢数量。服务项目无产品可在energy专项明确不适用。
- energy_checks：见energy-certificates.md。
- issues：id、category、reason、evidence数组、status=open/resolved；记录招标依据与投标原文，不能只写结论。
- hit_dispositions：对招标原始命中逐一status=included/excluded/duplicate、reason。
  verify另生成.dispositions.json用于原始+新词补扫全类别处置；included/duplicate指向工作区条目report_id。

### 证据字段

文本：{"doc":"d2","channel":"main","start":100,"end":102,"quote":"原文中的连续片段"}。
补充文本使用channel=extra，其行号只对应.extra.lines.txt。quote必须真实出现在所指范围内。
图片：{"doc":"d2","asset":"word/media/image1.png","quote":"原图可辨认的型号或文字"}。
图片quote需审核者看原图，程序只能核图片存在，不能证明识别正确。原图不清晰不得填确定值。
不得将XML定位或提取行号描述成Word页面。能可靠渲染定位时再补真实页码。

### 报价解析不全

自动结果对所有未识别表格和缺字段行保守报警。先判断无关表格/合计/续表/定制等原因。
缺品牌型号时用清单序号+产品身份+数量等复合信息联接；不得仅按行序猜配。
需要人工兜底时documents.dN.manual_price_coverage填写expected、reviewed（正整数且相等）、reason、evidence数组，
并在工作区保存完整逐行对账表、缺失字段补齐依据、各重复型号组处置。计数一致本身不是语义正确证据。
price_math独立完成，不把同型号价格检查当成算术检查。

## 完成与交付

bid-verify验证记录、证据引用、版本和必要检查，不自动判定材料真实或无废标。
风险可以在完成报告中保留；未完成审核要明确标注，不为了出报告把unknown改成通过。
输出工作区主表（##下）与Excel至少覆盖：要求响应、问题、报价归组、正文冲突、节能证书、证据不足、范围/版本。
用户只给部分投标文件时限定审查范围并列出缺件，不能称为三册全量完成。
