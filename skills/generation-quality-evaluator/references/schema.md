# 输入契约与错误标签

三个UTF-8 JSON文件：rubric（评分配置）、cases（原始资料/Prompt/输出）、ratings（评审者已给评分）。未知字段不提供能力授权。脚本只读输入，只有明确指定的报告路径会被写入；不访问网络、账号、模型或环境密钥。

## Cases

顶层schema_version=1、data_origin（synthetic/user_provided）、prompts（version_id→Prompt原文）、cases数组。每个case：case_id、kind、brief、sources（来源编号→原文）、outputs（version_id→输出原文）。同case所有版本共享brief/sources；若上下文改变，建立新的case_id，不能冒充同输入对照。脚本在报告中记录上下文与Prompt的SHA256。

本地演示所有上下文、Prompt、输出、评分及反馈均为AI辅助编写的演示案例，未调用生成模型产出这批脚本；这与tests/forward中的实际AI测试回答分开。

## Ratings

顶层schema_version=1、rubric_id（必须与配置一致）、rating_origin（synthetic/user_provided）、records数组。记录必须含case_id、version_id、rater_type（human/llm/synthetic）、scores对象、findings数组；可选feedback。

维度ID与rubric一致。每项：

| status | score | 其他字段 | 计算 |
| --- | --- | --- | --- |
| assessed | 0/1/2/3整数 | rationale与非空evidence | 进入权重分母 |
| unverified | null | rationale、证据 | 记待核实，不计零，不形成完整总分 |
| missing | null | rationale | 缺评分，不计零，不形成完整总分 |
| not_applicable | null | rationale | 从适用维度中排除；必须有业务理由 |

scores中缺某维度按missing显示，不报“零分”。没有任何适用且已评维度时均分为null。full_mean仅在所有适用维度均assessed时给出；partial_mean显示已评部分且显式标分母，不用于总分版本比较。不适用集合不同的版本总分不可比，即使都已完整评分。

证据：`{"ref":"output","quote":"精确短引文","note":"第2句"}`。ref可为当前版本output、brief或sources中编号。quote必须在该原文里出现；脚本只验证引文存在，不验证理由正确或来源可信。

实际返回空字符串可用`{"ref":"output","kind":"empty_output","quote":null,"note":"完整输出为空"}`定位，只有原文确为`""`时有效。它仍是实际输出，与未提供output字段不同；是否该给0分由评审按锚点判断。

错误：issue_id（同case同问题跨版本稳定）、type、status（confirmed/pending）、severity（critical/major/minor）、claim、evidence、recommendation、possible_causes（字符串列表）。同一记录内issue_id不得重复；不同版本同issue_id的type应保持一致。严重度升级会单独报告。

| type | 含义 |
| --- | --- |
| factual_contradiction | 明确来源矛盾，需定位双方 |
| factual_unknown | 未获得足够支持，必须pending，事实维度unverified |
| persona_conflict | 人设/受众要求被违背 |
| topic_drift | 偏离任务主题 |
| omission | 明示必要信息遗漏 |
| repetition | 非必要重复影响完整性/密度 |
| unnatural | 表达空泛或不自然 |
| style_mismatch | 与明示风格不一致 |
| oral_flow | 文本不便口播；没有录音就不称实测流畅度/耗时 |
| production_infeasible | 超过明示设备、场地、人力或动作条件 |
| forbidden_expression | 用户明确禁止的表达，不能泛化为合规认证 |

feedback可保留用户给定的采纳、编辑耗时、修改轮次与说明；需source注明human_operator/synthetic_example等来源。脚本原样展示，不算未提供的采纳率或效率提升，不把缺反馈填false/0。

## 配对与回归

基线/候选均来自指定version_id。报告披露：原始case数、各版本有输出数、已评分数、完整评分数、缺输出/缺评分、两版本均已评分的配对数，以及适用维度一致且完整的可比总分数。

优先发现新增confirmed critical（regressed_critical）；候选已有critical未解决则blocked_existing_critical。其他维度下降或严重度升级标regressed/mixed；全部资料与评分完整且目标错误消失/分数上升才可描述该case改善。未知、缺评分、不适用集合改变则inconclusive。只允许可比配对计算平均分差（0–3分差，不是提升百分比）；正差也不能覆盖退化case。

inconclusive不会抹掉可确定的退化：known_regression记录已评维度下降、新增confirmed问题或严重度升级；若同时存在未决项，批次返回needs_revision_and_evidence。confirmed变成pending不算问题已解决；resolved_confirmed_issues仅表示新版本记录中不再出现，仍需人工核对是否漏标。

数据不足时返回needs_more_evidence；有严重错误时blocked_critical。其余可送人工复核，不代表准许上线或真实业务效果。config中的阈值/权重属于用户配置，不是经统计校准的行业标准。
