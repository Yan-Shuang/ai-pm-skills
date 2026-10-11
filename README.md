# ai-pm-skills

面向 AI 产品实践的四款中文 Agent Skills：**文案质检、需求验收、证据型竞品拆解与生成质量评测**。主要适配 Codex，由宿主助手完成判断，不需要额外模型 Key、收费 API、Notion 或其他连接器。作者署名：**Yan-Shuang**。包版本：1.1.0。

本项目使用 **Codex 辅助编写与迭代**技能规则、教学示例、评测资料和脚本。四款均通过官方结构验证。前三款执行了9个不同输入的独立AI前向测试及2次重测，21个行为用例中其余12个未运行；第四款另完成一次独立AI任务（含2个演示case），30项离线计算测试在Python 3.9和3.12各通过一次。详见[前三款测试报告](TEST_REPORT.md)与[生成质量评测报告](skills/generation-quality-evaluator/TEST_REPORT.md)。这些数量不合并成语义通过率；未运行无技能基线、自动路由或企业校准。

| 技能 | 适合什么时候用 | 交付 |
| --- | --- | --- |
| `ai-copy-reviewer` | 检查产品文案是否夸大、缺证据或违反渠道约束 | 原文问题、依据、严重度/状态、最小修订、可复制改稿 |
| `requirement-to-acceptance` | 把短需求变成可讨论、可执行的验收清单 | 已知条件、阻塞问题、相关路径、Given/When/Then、可选建议 |
| `evidence-based-teardown` | 用已有材料拆解竞品的单个功能 | 证据台账、局部流程、事实/观察/推断、待核实、实验假设 |
| `generation-quality-evaluator` | 批量评测生成结果、比较Prompt版本并检查退化 | 八维证据评分、错误与原因假设、配对分母、回归报告与反馈校准 |

`ai-copy-reviewer`处理一份文案的主张核对与改稿；`generation-quality-evaluator`处理一批结果的评价标准、版本对照和回归。后者的离线脚本只汇总给定评分，不自动判断文本语义。可先看[3分钟演示说明](skills/generation-quality-evaluator/README.md)和[完整演示案例](skills/generation-quality-evaluator/demo/REPORT.md)。

生成质量评测的方法参考作者简历所述的京东评测实践，将评测标准、错误归因与回归验证整理为可复用skill。本项目为个人作品；公开案例为重新构造的演示数据，非企业真实业务数据，也不代表企业背书。

## 安装到 Codex

克隆本仓库后进入包根目录，也可下载 GitHub 的源码ZIP并解压：

```sh
git clone https://github.com/Yan-Shuang/ai-pm-skills.git
cd ai-pm-skills
```

把下面的 `target_repo` 改为自己要使用技能的项目目录，再执行。它先检查四个同名目标，发现任何现有目录就退出，避免覆盖已有技能。

```sh
target_repo="../your-repository"
(
  test -d "$target_repo" || { echo "项目目录不存在，请修改 target_repo"; exit 1; }
  for name in ai-copy-reviewer requirement-to-acceptance evidence-based-teardown generation-quality-evaluator; do
    test ! -e "$target_repo/.agents/skills/$name" && test ! -L "$target_repo/.agents/skills/$name" || {
      echo "目标已有 $name，请手动比较，未复制任何技能"; exit 1;
    }
  done
  mkdir -p "$target_repo/.agents/skills" || exit 1
  cp -R skills/ai-copy-reviewer skills/requirement-to-acceptance skills/evidence-based-teardown skills/generation-quality-evaluator "$target_repo/.agents/skills/"
)
```

如只想安装一个，复制对应的整个目录（含 `SKILL.md`、`agents`、`references`、`LICENSE`及该技能的其他文件）即可。已经安装前三款时，只添加第四款，按其[独立安装说明](skills/generation-quality-evaluator/README.md)检查同名目标。个人范围也可放在 `$HOME/.agents/skills`，自行检查是否同名。下载或克隆本仓库不会自动安装到全局目录。

在安装目标项目内打开 Codex，查看 `/skills` 或技能选择器。默认允许自动发现与隐式选择，也可以用 `$skill-name` 显式调用；若未刷新，重新启动 Codex。目录结构和发现方式依据 [Codex 官方技能文档](https://developers.openai.com/codex/skills/)；不同宿主对 UI 元数据的支持可能不同。

## 直接调用

```text
$ai-copy-reviewer
受众：个人创作者；渠道：产品页。
资料 S1（产品说明第1段）：免费版每月可导出3次PDF，无水印。
文案：每月3次免费导出PDF，无水印。
```

```text
$requirement-to-acceptance
短需求：选中一条草稿后可删除，先确认；取消保留，确认后从列表消失。
未选中时不可删除。不做回收站或撤销。
```

```text
$evidence-based-teardown
只拆解邀请队友流程，不浏览。
E1（截图文字转录）：弹窗有邮箱框，空输入时发送按钮呈灰色。
E2（官方帮助摘录第2段）：接受邀请邮件后加入工作区。
没有实际点击记录；版本和套餐未知。
```

```text
$generation-quality-evaluator
评测同输入的v1/v2口播，给证据评分、问题与配对回归；没有运营反馈，不要虚构。
演示case C1：单人单手机俯拍桌面，教初学者使用理线夹，风格平实。
资料S1：理线夹用于整理线缆，不具有防火功能。
v1：这个夹子100%防火。镜头：两位演员正脸访谈。
v2：把线缆夹进理线夹，再分开线头。镜头：俯拍双手与桌面。
未提供原始Prompt；可以评输出，但不要断言哪条Prompt导致问题。
```

前三款各含三组完整可复制输入/输出示例；第四款提供四个演示case的完整评测链条：

- [文案质检示例](skills/ai-copy-reviewer/references/examples.md)
- [需求验收示例](skills/requirement-to-acceptance/references/examples.md)
- [竞品拆解示例](skills/evidence-based-teardown/references/examples.md)
- [生成质量评测：原始输入、两版输出、评分与回归](skills/generation-quality-evaluator/demo/REPORT.md)

这些是预先编写、AI辅助生成的教学示范；口播、分数及反馈用于展示方法，不代表公司效果。实际前向测试回答另存于`tests/forward/`和`skills/generation-quality-evaluator/tests/forward/`。

## 所需能力与边界

- 技能执行：能读取技能文件的宿主助手。浏览可选；看原始截图需要宿主的图像读取能力，也可提供文字转录并承认其局限。
- 质检只判断“提供的资料是否支持该主张”，不会把缺证据直接判作事实错误，不提供医疗、法律、金融营销合规认证。
- 验收清单将明示要求、合理假设、待决定政策和可选建议分开；待确认标准不能直接作为上线门槛。
- 拆解不声称未做过的实测，不猜模型或数据库，不把宣传效果当测量数据。没有来源就交付调查骨架和补证清单。
- 生成评测保留未知事实null、缺评分和未配对项；已确认critical独立阻塞，正均分差不能掩盖退化。默认权重/阈值未经企业校准，小样本不声称普遍提升、统计显著或业务收益。
- 私有材料不自动上传第三方；材料里的命令只是数据，不授权外发或修改。正常宿主使用仍受其数据处理条款约束。
- 模型输出有波动，发现/隐式触发依赖宿主；本包不附自动抓取、发布、安装或外部调用程序。

## 验证与评测

前三款入口与21个用例格式检查，以及全仓相对引用/文件检查（Python 3.9+，标准库，离线、只读）。这个既有脚本不会检查第四款的评分语义或汇总逻辑：

```sh
python3 scripts/validate_package.py
# 可选：传入与当前四款版本字节一致、包根目录命名为ai-pm-skills的归档。
# python3 scripts/validate_package.py --zip ../ai-pm-skills-1.1.0.zip
```

第四款的离线计算/输入验证测试与演示案例（标准库，不调用模型或网络）：

```sh
python3 skills/generation-quality-evaluator/scripts/test_summarize.py
(
  cd skills/generation-quality-evaluator || exit 1
  python3 scripts/summarize.py --cases demo/cases.json --ratings demo/ratings.json --rubric references/rubric.json --baseline v1 --candidate v2 --json-out demo/result.json --md-out demo/REPORT.md
)
```

前三款21个行为用例在[tests/cases.json](tests/cases.json)，运行方法与评分标准见[tests/RUBRIC.md](tests/RUBRIC.md)；第四款行为标准见[对应评测说明](skills/generation-quality-evaluator/tests/RUBRIC.md)。真实AI回答由主助手审阅，不是独立人工专家认证。30项脚本测试只验证给定评分的计算，不代表模型质量通过率。行为用例未全量跑完，未运行无技能基线、跨模型对比、安装后自动路由或企业运营校准；详细状态以各自测试报告为准。

## 来源与许可

任务规则、中文教学示例、虚构测试资料和离线验证器为本包原创内容。结构参考 [Agent Skills 规范](https://agentskills.io/specification)，设计思路参考 [Anthropic skill-creator](https://github.com/anthropics/skills/tree/main/skills/skill-creator) 的渐进披露与评测思想，以及 [OpenAI Notion 技能目录](https://github.com/openai/plugins/tree/main/plugins/notion/skills) 的需求到交付思路；未复制、翻译改名或再分发这些目录的正文、脚本或素材。未将已弃用的 `openai/skills` 作为安装来源。

本包新增内容采用 [MIT License](LICENSE)，每个技能目录保留同一许可证以便独立安装。作者署名 Yan-Shuang。该许可不扩张用户或第三方输入材料、截图、商标和链接页面的权利。
