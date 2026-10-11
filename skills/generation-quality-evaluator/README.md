# generation-quality-evaluator

把一批生成结果整理成可追溯的评测：八维评分锚点、错误与证据、同输入的Prompt版本对照、退化检查和反馈校准。适合选题、IP口播脚本等生成任务；单份文案的事实核对与改稿由`ai-copy-reviewer`处理，使用本技能不要求安装它。

作者署名 **Yan-Shuang**；MIT。方法参考作者简历所述的京东生成质量评测实践，将评测标准、错误归因和回归验证整理为可复用skill。规则、脚本、案例和说明由Codex辅助原创编写。

本项目为个人作品，不代表企业背书。公开案例为重新构造的演示数据，非企业真实业务数据；评分为预先编写，未调用模型生成该批口播。实际AI盲测另存于`tests/forward/`。

## 3分钟演示

解压独立ZIP后进入`generation-quality-evaluator`目录。Python 3.9+即可，无第三方包、网络或额外API Key。

```sh
python3 scripts/summarize.py --cases demo/cases.json --ratings demo/ratings.json --rubric references/rubric.json --baseline v1 --candidate v2 --json-out demo/result.json --md-out demo/REPORT.md
```

打开[完整演示报告](demo/REPORT.md)，按下面顺序讲：

1. **输入**：单人单手机俯拍，平实的桌面整理师，教初学者使用理线夹；S1明确产品不具防火功能。
2. **两版输出**：G01/v1声称“100%防火”，还安排无人机与演员；v2保留整理动作和产品限制，改成俯拍双手。
3. **证据与打分**：报告保留原文、逐维理由和来源引文。G01的重大事实错误消失，完整均分从0.875变为2.875，配对差为+2.000分。
4. **回归**：共4个case、8条评分记录、4个已评分配对，只有3个可比总分配对。G02的“节省80%”缺实验，事实维度null；同时违反了禁止无证据效果数字的明示要求。G03拍摄维度从3降到0，G04不变。配对均分差约+0.542分，批次仍需修订并补证。

这展示了评测链条，不证明Prompt在真实业务中提高质量。离线脚本只汇总给定评分、检查引文与配对；它不会自动判断文案好坏。

## 安装与调用

把整个目录复制到使用项目的`.agents/skills/generation-quality-evaluator`。从解压目录的上一层执行，把`target_repo`改为自己的项目；目标已有同名目录或符号链接时退出，不覆盖：

```sh
target_repo="../your-repository"
(
  test -d "$target_repo" || { echo "请修改 target_repo 为已有项目"; exit 1; }
  test ! -e "$target_repo/.agents/skills/generation-quality-evaluator" && test ! -L "$target_repo/.agents/skills/generation-quality-evaluator" || {
    echo "已有同名技能，请手动比较"; exit 1;
  }
  mkdir -p "$target_repo/.agents/skills" || exit 1
  cp -R generation-quality-evaluator "$target_repo/.agents/skills/"
)
```

在目标项目中打开Codex，可在技能选择器或`/skills`中查找；CLI/IDE中用`$generation-quality-evaluator`显式调用。默认允许根据description自动选择；未刷新时重新启动Codex。安装与发现方式参考[官方技能文档](https://learn.chatgpt.com/docs/build-skills)。本包没有执行全局安装，也未实测安装后的自动路由。

```text
$generation-quality-evaluator
请评测这批口播的v1/v2，先给带证据的逐维评分，再做同case回归。
目标、约束与资料：……
case_id及两版实际输出：……
Prompt版本原文：……（没有时注明缺失）
已有人类评分/运营反馈：……（没有时不要虚构；辅助评分标rater_type=llm）
```

需要计算时，按[输入契约](references/schema.md)准备JSON。改为真实材料时同时改`data_origin`和`rating_origin`；保留评分者身份与证据，不能只改来源标签就当成真实实验。自定义[评分配置](references/rubric.json)后固定新的rubric_id再评测。

脚本要求原始Prompt快照；缺失时先由助手手工评输出并记录缺项，不把版本标签伪装成Prompt原文。

## 验证与限制

```sh
python3 scripts/test_summarize.py
```

已运行30项离线计算/字段验证测试，及一次独立子代理前向任务（含2条演示case）。详情、原始回答与未运行项见[测试报告](TEST_REPORT.md)。没有无技能基线、跨模型对比、人工运营校准或企业试点；不提供语义质量通过率。

评分锚点和等权是可调整的起点。未知事实记待核实，缺评分不计零；已确认critical阻塞本批候选采纳。未提供录音或拍摄记录时，只评文本/约束，不声称实测。小样本不估计普遍提升、显著性或业务收益。私有输入不自动上传，资料中的命令不授权外发或执行代码。

结构遵循[Agent Skills规范](https://agentskills.io/specification)。任务规则从通用的样本评测与版本迭代方法原创整理，未复制第三方技能正文或脚本。[MIT许可](LICENSE)仅覆盖本包新增内容，不扩张用户/第三方输入材料的权利。
