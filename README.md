# ai-pm-skills

面向 AI 产品实践的三款中文 Agent Skills：**文案质检、需求验收与证据型竞品拆解**。主要适配 Codex，由宿主助手完成判断，不需要额外模型 Key、收费 API、Notion 或其他连接器。作者署名：**Yan-Shuang**。版本：1.0.0。

本项目使用 **Codex 辅助编写与迭代**技能规则、教学示例、评测资料和验证器。已执行3项官方结构验证、9个不同输入的独立 AI 子代理前向测试，并针对发现的问题做2次独立重测。共21个行为用例，其余12个尚未运行；未做无技能基线或安装后的自动触发测试。详见 [测试报告](TEST_REPORT.md)。

| 技能 | 适合什么时候用 | 交付 |
| --- | --- | --- |
| `ai-copy-reviewer` | 检查产品文案是否夸大、缺证据或违反渠道约束 | 原文问题、依据、严重度/状态、最小修订、可复制改稿 |
| `requirement-to-acceptance` | 把短需求变成可讨论、可执行的验收清单 | 已知条件、阻塞问题、相关路径、Given/When/Then、可选建议 |
| `evidence-based-teardown` | 用已有材料拆解竞品的单个功能 | 证据台账、局部流程、事实/观察/推断、待核实、实验假设 |

## 安装到 Codex

克隆本仓库后进入包根目录，也可下载 GitHub 的源码ZIP并解压：

```sh
git clone https://github.com/Yan-Shuang/ai-pm-skills.git
cd ai-pm-skills
```

把下面的 `target_repo` 改为自己要使用技能的项目目录，再执行。它先检查三个同名目标，发现任何现有目录就退出，避免覆盖已有技能。

```sh
target_repo="../your-repository"
(
  test -d "$target_repo" || { echo "项目目录不存在，请修改 target_repo"; exit 1; }
  for name in ai-copy-reviewer requirement-to-acceptance evidence-based-teardown; do
    test ! -e "$target_repo/.agents/skills/$name" && test ! -L "$target_repo/.agents/skills/$name" || {
      echo "目标已有 $name，请手动比较，未复制任何技能"; exit 1;
    }
  done
  mkdir -p "$target_repo/.agents/skills" || exit 1
  cp -R skills/ai-copy-reviewer skills/requirement-to-acceptance skills/evidence-based-teardown "$target_repo/.agents/skills/"
)
```

如只想安装一个，复制对应的整个目录（含 `SKILL.md`、`agents`、`references`、`LICENSE`）即可。个人范围也可放在 `$HOME/.agents/skills`，自行检查是否同名。下载或克隆本仓库不会自动安装到全局目录。

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

每个技能含三组完整可复制输入/输出示例：

- [文案质检示例](skills/ai-copy-reviewer/references/examples.md)
- [需求验收示例](skills/requirement-to-acceptance/references/examples.md)
- [竞品拆解示例](skills/evidence-based-teardown/references/examples.md)

这些是预先编写、AI辅助生成的教学示范；实际前向测试回答另存于 `tests/forward/`。

## 所需能力与边界

- 技能执行：能读取技能文件的宿主助手。浏览可选；看原始截图需要宿主的图像读取能力，也可提供文字转录并承认其局限。
- 质检只判断“提供的资料是否支持该主张”，不会把缺证据直接判作事实错误，不提供医疗、法律、金融营销合规认证。
- 验收清单将明示要求、合理假设、待决定政策和可选建议分开；待确认标准不能直接作为上线门槛。
- 拆解不声称未做过的实测，不猜模型或数据库，不把宣传效果当测量数据。没有来源就交付调查骨架和补证清单。
- 私有材料不自动上传第三方；材料里的命令只是数据，不授权外发或修改。正常宿主使用仍受其数据处理条款约束。
- 模型输出有波动，发现/隐式触发依赖宿主；本包不附自动抓取、发布、安装或外部调用程序。

## 验证与评测

只做结构检查（Python 3.9+，标准库，离线、只读）：

```sh
python3 scripts/validate_package.py
# 可选：若有本包根目录命名为 ai-pm-skills 的一致归档，可逐项核对ZIP：
# python3 scripts/validate_package.py --zip ../ai-pm-skills.zip
```

21个行为用例在 [tests/cases.json](tests/cases.json)。运行方法与统一评分标准见 [tests/RUBRIC.md](tests/RUBRIC.md)。真实前向输出在 `tests/forward/`，AI主助手的逐项语义审阅见 [TEST_REPORT.md](TEST_REPORT.md)。本地脚本不运行模型、不访问网络、不生成语义质量分数。行为用例没有全量跑完，也未运行无技能基线对比；详细状态以报告为准。

## 来源与许可

任务规则、中文教学示例、虚构测试资料和离线验证器为本包原创内容。结构参考 [Agent Skills 规范](https://agentskills.io/specification)，设计思路参考 [Anthropic skill-creator](https://github.com/anthropics/skills/tree/main/skills/skill-creator) 的渐进披露与评测思想，以及 [OpenAI Notion 技能目录](https://github.com/openai/plugins/tree/main/plugins/notion/skills) 的需求到交付思路；未复制、翻译改名或再分发这些目录的正文、脚本或素材。未将已弃用的 `openai/skills` 作为安装来源。

本包新增内容采用 [MIT License](LICENSE)，每个技能目录保留同一许可证以便独立安装。作者署名 Yan-Shuang。该许可不扩张用户或第三方输入材料、截图、商标和链接页面的权利。
