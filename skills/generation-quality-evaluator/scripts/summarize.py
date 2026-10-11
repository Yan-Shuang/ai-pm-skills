#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline aggregation of supplied ratings, never an automatic text judge."""
import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path


class InputError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise InputError(message)


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def load_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "重复JSON键: " + key)
            result[key] = value
        return result
    with Path(path).open(encoding="utf-8") as source:
        return json.load(source, object_pairs_hook=pairs)


def validate_rubric(config):
    require(isinstance(config, dict) and config.get("schema_version") == 1, "rubric格式错误")
    require(text(config.get("rubric_id")), "缺少rubric_id")
    require(config.get("scale_min") == 0 and config.get("scale_max") == 3, "评分尺度须为0–3")
    for key in ("min_acceptable_mean", "regression_tolerance"):
        require(number(config.get(key)) and 0 <= config[key] <= 3, key + "无效")
    dims = config.get("dimensions")
    require(isinstance(dims, list) and dims, "至少配置一个维度")
    ids = set()
    for dim in dims:
        require(isinstance(dim, dict) and text(dim.get("id")) and dim["id"] not in ids, "维度ID缺失/重复")
        ids.add(dim["id"])
        require(text(dim.get("label")), "维度缺少名称")
        require(number(dim.get("weight")) and dim["weight"] > 0, "维度权重须为正有限数")
        require(isinstance(dim.get("anchors"), dict) and set(dim["anchors"]) == {"0", "1", "2", "3"}, "需完整0–3评分锚点")
        require(all(text(v) for v in dim["anchors"].values()), "评分锚点不能为空")
    require(config.get("fact_dimension") in ids or config.get("fact_dimension") is None, "事实维度不在配置中")
    types = config.get("error_types")
    require(isinstance(types, list) and types and all(text(t) for t in types) and len(set(types)) == len(types), "错误类型无效/重复")
    require(config.get("unknown_fact_type") in types or config.get("unknown_fact_type") is None, "未知事实类型未配置")
    return {dim["id"]: dim for dim in dims}


def validate_cases(data, baseline, candidate):
    require(isinstance(data, dict) and data.get("schema_version") == 1, "cases格式错误")
    require(data.get("data_origin") in ("synthetic", "user_provided"), "需注明cases来源")
    prompts = data.get("prompts")
    require(isinstance(prompts, dict) and all(text(k) and text(v) for k, v in prompts.items()), "Prompt版本快照无效")
    require(baseline != candidate and baseline in prompts and candidate in prompts, "比较须指定两个已有且不同的Prompt版本")
    require(isinstance(data.get("cases"), list), "cases须为数组")
    cases = {}
    for case in data["cases"]:
        require(isinstance(case, dict) and text(case.get("case_id")), "case_id缺失")
        ident = case["case_id"]
        require(ident not in cases, "重复case_id: " + ident)
        require(text(case.get("brief")) and text(case.get("kind")), ident + ": 缺少brief/kind")
        sources = case.get("sources")
        require(isinstance(sources, dict) and all(text(k) and isinstance(v, str) for k, v in sources.items()), ident + ": sources错误")
        require(not {"output", "brief"} & set(sources), ident + ": 来源ID与保留字段冲突")
        outputs = case.get("outputs")
        require(isinstance(outputs, dict) and all(k in prompts and isinstance(v, str) for k, v in outputs.items()), ident + ": 输出/版本无效")
        cases[ident] = case
    return cases


def validate_evidence(items, case, version, label):
    require(isinstance(items, list) and items, label + ": 缺少证据")
    refs = {**case["sources"], "brief": case["brief"], "output": case["outputs"][version]}
    for item in items:
        require(isinstance(item, dict) and item.get("ref") in refs and text(item.get("note")), label + ": 证据引用/定位无效")
        if item.get("kind") == "empty_output":
            require(item["ref"] == "output" and refs["output"] == "" and item.get("quote") is None, label + ": 空输出证据与原文不符")
        else:
            quote = item.get("quote")
            require(text(quote) and quote in refs[item["ref"]], label + ": 引文不存在于原文")


def normalize_record(record, case, dims, config):
    ident, version = record["case_id"], record["version_id"]
    label = ident + "/" + version
    require(record.get("rater_type") in ("human", "llm", "synthetic"), label + ": rater_type错误")
    scores = record.get("scores")
    require(isinstance(scores, dict) and not (set(scores) - set(dims)), label + ": 未配置的评分维度")
    normalized = {}
    for key in dims:
        item = scores.get(key, {"status": "missing", "score": None, "rationale": "未提供评分"})
        require(isinstance(item, dict) and text(item.get("rationale")), label + "/" + key + ": 缺少评分理由")
        status = item.get("status")
        require(status in ("assessed", "missing", "unverified", "not_applicable"), label + ": 评分状态错误")
        if status == "assessed":
            require(type(item.get("score")) is int and 0 <= item["score"] <= 3, label + ": 分数须为0–3整数")
            validate_evidence(item.get("evidence"), case, version, label + "/" + key)
        else:
            require(item.get("score") is None, label + ": 缺失/待核实/不适用不得填分")
            if status == "unverified":
                validate_evidence(item.get("evidence"), case, version, label + "/" + key)
        normalized[key] = item
    findings = record.get("findings")
    require(isinstance(findings, list), label + ": findings须为数组")
    issue_ids = set()
    for item in findings:
        require(isinstance(item, dict) and text(item.get("issue_id")) and item["issue_id"] not in issue_ids, label + ": issue_id缺失/重复")
        issue_ids.add(item["issue_id"])
        require(item.get("type") in config["error_types"], label + ": 错误类型未配置")
        require(item.get("status") in ("confirmed", "pending") and item.get("severity") in ("critical", "major", "minor"), label + ": 错误状态/严重度无效")
        require(text(item.get("claim")) and text(item.get("recommendation")), label + ": 问题/建议缺失")
        require(isinstance(item.get("possible_causes"), list) and all(text(c) for c in item["possible_causes"]), label + ": 可能原因须独立列示")
        validate_evidence(item.get("evidence"), case, version, label + "/" + item["issue_id"])
        if item["type"] == config.get("unknown_fact_type"):
            require(item["status"] == "pending", label + ": 未知事实不能标已确认错误")
            fact = config.get("fact_dimension")
            require(fact is not None and normalized[fact]["status"] == "unverified", label + ": 未知事实的事实评分须unverified/null")
    if "feedback" in record:
        feedback = record["feedback"]
        require(isinstance(feedback, dict) and text(feedback.get("source")), label + ": 反馈须注明来源")
        if "adopted" in feedback:
            require(type(feedback["adopted"]) is bool, label + ": adopted须为布尔值")
        for key in ("edit_minutes", "revision_rounds", "generation_seconds"):
            if key in feedback and feedback[key] is not None:
                require(number(feedback[key]) and feedback[key] >= 0, label + ": 反馈数值无效")
    assessed = [key for key, item in normalized.items() if item["status"] == "assessed"]
    counts = Counter(item["status"] for item in normalized.values())
    denominator = sum(dims[key]["weight"] for key in assessed)
    partial = sum(normalized[key]["score"] * dims[key]["weight"] for key in assessed) / denominator if denominator else None
    complete = bool(assessed) and not counts["missing"] and not counts["unverified"]
    critical = [f["issue_id"] for f in findings if f["status"] == "confirmed" and f["severity"] == "critical"]
    pending = [f["issue_id"] for f in findings if f["status"] == "pending"]
    if critical:
        gate = "blocked_critical"
    elif pending or counts["unverified"]:
        gate = "needs_verification"
    elif not complete:
        gate = "incomplete"
    elif partial < config["min_acceptable_mean"]:
        gate = "needs_revision"
    else:
        gate = "within_configured_checks"
    return {"case_id": ident, "version_id": version, "rater_type": record["rater_type"], "scores": normalized, "findings": findings, "feedback": record.get("feedback"), "status_counts": dict(counts), "assessed_dimensions": assessed, "weight_denominator": denominator, "partial_mean": partial, "full_mean": partial if complete else None, "complete": complete, "gate": gate, "critical_issues": critical, "pending_issues": pending, "context_sha256": digest({"brief": case["brief"], "sources": case["sources"]})}


def compare_pair(before, after, dims, config):
    old = {f["issue_id"]: f for f in before["findings"] if f["status"] == "confirmed"}
    new = {f["issue_id"]: f for f in after["findings"] if f["status"] == "confirmed"}
    new_critical = [key for key, item in new.items() if item["severity"] == "critical" and (key not in old or old[key]["severity"] != "critical")]
    new_issues = sorted(set(new) - set(old))
    unresolved_ids = {f["issue_id"] for f in after["findings"]}
    resolved = sorted(set(old) - unresolved_ids)
    severity = {"minor": 0, "major": 1, "critical": 2}
    escalated = sorted(key for key in set(old) & set(new) if severity[new[key]["severity"]] > severity[old[key]["severity"]])
    deltas = {key: after["scores"][key]["score"] - before["scores"][key]["score"] for key in dims if before["scores"][key]["status"] == after["scores"][key]["status"] == "assessed"}
    drops = [key for key, delta in deltas.items() if delta < -config["regression_tolerance"]]
    score_comparable = before["complete"] and after["complete"] and set(before["assessed_dimensions"]) == set(after["assessed_dimensions"])
    delta = after["full_mean"] - before["full_mean"] if score_comparable else None
    uncertain = not score_comparable or bool(before["pending_issues"] or after["pending_issues"])
    positive = bool(resolved) or (delta is not None and delta > config["regression_tolerance"])
    negative = bool(drops or new_issues or escalated)
    if new_critical:
        verdict = "regressed_critical"
    elif after["critical_issues"]:
        verdict = "blocked_existing_critical"
    elif uncertain:
        verdict = "inconclusive"
    elif negative and positive:
        verdict = "mixed"
    elif negative:
        verdict = "regressed"
    elif positive:
        verdict = "improved"
    else:
        verdict = "unchanged"
    return {"case_id": before["case_id"], "verdict": verdict, "known_regression": negative, "score_comparable": score_comparable, "total_delta": delta, "dimension_deltas": deltas, "dimension_regressions": drops, "new_confirmed_issues": new_issues, "resolved_confirmed_issues": resolved, "severity_escalations": escalated, "new_critical_issues": new_critical, "candidate_gate": after["gate"]}


def summarize(cases_data, ratings_data, config, baseline, candidate):
    dims = validate_rubric(config)
    cases = validate_cases(cases_data, baseline, candidate)
    require(isinstance(ratings_data, dict) and ratings_data.get("schema_version") == 1, "ratings格式错误")
    require(ratings_data.get("rubric_id") == config["rubric_id"], "评分rubric_id与配置不一致")
    require(ratings_data.get("rating_origin") in ("synthetic", "user_provided"), "需注明评分来源")
    require(isinstance(ratings_data.get("records"), list), "records须为数组")
    records = {}
    issue_types = {}
    for record in ratings_data["records"]:
        require(isinstance(record, dict), "评分记录须为对象")
        ident, version = record.get("case_id"), record.get("version_id")
        require(ident in cases and version in cases[ident]["outputs"], "评分没有对应case/版本输出")
        key = (ident, version)
        require(key not in records, "重复评分记录: " + ident + "/" + version)
        current = normalize_record(record, cases[ident], dims, config)
        for finding in current["findings"]:
            issue_key = (ident, finding["issue_id"])
            require(issue_key not in issue_types or issue_types[issue_key] == finding["type"], "跨版本issue_id类型冲突")
            issue_types[issue_key] = finding["type"]
        records[key] = current
    versions = {}
    for version in (baseline, candidate):
        output_ids = {key for key, case in cases.items() if version in case["outputs"]}
        rated = {key for key, v in records if v == version}
        complete = [records[(key, version)] for key in sorted(rated) if records[(key, version)]["complete"]]
        counts = Counter(records[(key, version)]["gate"] for key in sorted(rated))
        versions[version] = {"output_cases": len(output_ids), "rated_cases": len(rated), "complete_score_cases": len(complete), "mean_of_complete_scores": sum(r["full_mean"] for r in complete) / len(complete) if complete else None, "mean_denominator": len(complete), "missing_outputs": sorted(set(cases) - output_ids), "missing_ratings": sorted(output_ids - rated), "gate_counts": dict(counts)}
    baseline_ids = {key for key, v in records if v == baseline}
    candidate_ids = {key for key, v in records if v == candidate}
    paired = sorted(baseline_ids & candidate_ids)
    comparisons = [compare_pair(records[(key, baseline)], records[(key, candidate)], dims, config) for key in paired]
    comparable = [item for item in comparisons if item["score_comparable"]]
    missing = any(versions[v]["missing_outputs"] or versions[v]["missing_ratings"] for v in (baseline, candidate))
    gates = versions[candidate]["gate_counts"]
    needs_evidence = missing or not paired or any(item["verdict"] == "inconclusive" for item in comparisons)
    needs_revision = any(item["known_regression"] for item in comparisons) or bool(gates.get("needs_revision"))
    if gates.get("blocked_critical"):
        readiness = "blocked_critical"
    elif needs_evidence and needs_revision:
        readiness = "needs_revision_and_evidence"
    elif needs_evidence:
        readiness = "needs_more_evidence"
    elif needs_revision:
        readiness = "needs_revision"
    else:
        readiness = "send_for_human_review"
    return {"schema_version": 1, "calculation_scope": "supplied_ratings_only_not_semantic_truth", "data_origin": cases_data["data_origin"], "rating_origin": ratings_data["rating_origin"], "rubric_id": config["rubric_id"], "baseline": baseline, "candidate": candidate, "prompt_sha256": {v: digest(cases_data["prompts"][v]) for v in (baseline, candidate)}, "case_count": len(cases), "versions": versions, "paired_rated_cases": len(paired), "score_comparable_pairs": len(comparable), "paired_mean_delta": sum(item["total_delta"] for item in comparable) / len(comparable) if comparable else None, "paired_delta_denominator": len(comparable), "unpaired_baseline": sorted(baseline_ids - candidate_ids), "unpaired_candidate": sorted(candidate_ids - baseline_ids), "verdict_counts": dict(Counter(item["verdict"] for item in comparisons)), "readiness": readiness, "comparisons": comparisons, "records": list(records.values()), "warnings": ["只汇总给定判断，不认证评分/证据语义真实性", "版本独立均分可能有不同分母，不是版本提升", "分差仅描述本批次，不提供统计显著或提升比例"] + (["含LLM辅助评分，需人工校准"] if any(r["rater_type"] == "llm" for r in records.values()) else [])}


def markdown(result, cases_data, config):
    def value(item):
        return "—" if item is None else format(item, ".3f")
    def cell(item):
        return str(item).replace("|", "\\|").replace("\n", "<br>")
    fence, tick = chr(96) * 3, chr(96)
    origins = {"synthetic": "演示构造", "user_provided": "用户提供"}
    raters = {"synthetic": "演示评分", "llm": "LLM辅助评审", "human": "人工评审"}
    origin_note = "案例为演示构造，非企业真实业务数据；评分和反馈用于展示评测方法。" if result["data_origin"] == result["rating_origin"] == "synthetic" else "分别按输入与评分的来源标签解读；演示构造不能当真实实验，用户提供的部分也未认证真实性或评分语义真值。"
    lines = ["# 生成质量评测报告", "", "**案例来源：" + origins[result["data_origin"]] + "；评分来源：" + origins[result["rating_origin"]] + "。**", "", origin_note + "此报告由离线脚本计算，评测语义由评审者判断。", "", "## 批次与分母", "", "| 版本 | 有输出 | 已评分 | 完整评分 | 完整评分均分（0–3） | 均分分母 |", "| --- | --- | --- | --- | --- | --- |"]
    for version, info in result["versions"].items():
        lines.append("| " + " | ".join(map(str, [cell(version), info["output_cases"], info["rated_cases"], info["complete_score_cases"], value(info["mean_of_complete_scores"]), info["mean_denominator"]])) + " |")
    lines += ["", "原始case数：" + str(result["case_count"]) + "；两版本已评分配对数：" + str(result["paired_rated_cases"]) + "；可比总分配对数：" + str(result["score_comparable_pairs"]) + "。", "", "配对总分平均差（候选−基线，0–3分差）：" + value(result["paired_mean_delta"]) + "；差值分母=" + str(result["paired_delta_denominator"]) + "。正差不能覆盖退化和待核实。", "", "批次处理：**" + result["readiness"] + "**。这不是上线或合规认证。", "", "| case_id | 回归判定 | 可比总分 | 总分差 | 退化维度 | 候选状态 |", "| --- | --- | --- | --- | --- | --- |"]
    for item in result["comparisons"]:
        lines.append("| " + " | ".join(cell(v) for v in [item["case_id"], item["verdict"], item["score_comparable"], value(item["total_delta"]), ", ".join(item["dimension_regressions"]) or "无", item["candidate_gate"]]) + " |")
    for item in result["comparisons"]:
        lines += ["", item["case_id"] + "：新增已确认问题=" + str(item["new_confirmed_issues"]) + "；不再出现的已确认问题=" + str(item["resolved_confirmed_issues"]) + "；严重度升级=" + str(item["severity_escalations"]) + "。"]
    lines += ["", "未配对基线：" + str(result["unpaired_baseline"]) + "；未配对候选：" + str(result["unpaired_candidate"]) + "。"]
    for version, info in result["versions"].items():
        lines += ["", version + "缺输出：" + str(info["missing_outputs"]) + "；缺评分：" + str(info["missing_ratings"]) + "。"]
    lines += ["", "## Prompt快照", ""]
    for version in (result["baseline"], result["candidate"]):
        lines += ["### " + version, "", cases_data["prompts"][version], "", "SHA256：" + tick + result["prompt_sha256"][version] + tick, ""]
    dims = {item["id"]: item for item in config["dimensions"]}
    for case in cases_data["cases"]:
        lines += ["## " + case["case_id"] + " · " + case["kind"], "", "### 原始输入与资料", "", case["brief"], ""]
        for ref, raw in case["sources"].items():
            lines += ["**" + ref + "**：" + raw, ""]
        for version in (result["baseline"], result["candidate"]):
            if version not in case["outputs"]:
                lines += ["### " + version + "：缺输出", ""]
                continue
            lines += ["### " + version + " 原始输出", "", fence + "text", case["outputs"][version] or "（实际返回空字符串）", fence, ""]
            record = next((r for r in result["records"] if r["case_id"] == case["case_id"] and r["version_id"] == version), None)
            if not record:
                lines += ["缺评分，未计零。", ""]
                continue
            lines += ["评分者：" + raters[record["rater_type"]] + "；状态：" + record["gate"] + "；完整总分：" + value(record["full_mean"]) + "；已评部分均分：" + value(record["partial_mean"]) + "（权重分母=" + str(record["weight_denominator"]) + "）。", "", "| 维度 | 状态/分数 | 依据与理由 |", "| --- | --- | --- |"]
            for key, item in record["scores"].items():
                evidence = "; ".join(str(e["ref"]) + "/" + e["note"] + "：" + str(e.get("quote")) for e in item.get("evidence", []))
                lines.append("| " + cell(dims[key]["label"]) + " | " + cell(item["status"] + "/" + str(item["score"])) + " | " + cell(evidence + "；" + item["rationale"]) + " |")
            lines += [""]
            for finding in record["findings"]:
                evidence = "; ".join(e["ref"] + "/" + e["note"] + "：" + str(e.get("quote")) for e in finding["evidence"])
                lines += ["- **" + finding["issue_id"] + "** · " + finding["type"] + "/" + finding["status"] + "/" + finding["severity"] + "：" + finding["claim"], "  - 证据：" + evidence, "  - 修订建议：" + finding["recommendation"], "  - 可能原因（假设）：" + "; ".join(finding["possible_causes"])]
            if record["feedback"]:
                lines += ["", "给定反馈（未推算业务收益）：" + tick + json.dumps(record["feedback"], ensure_ascii=False) + tick, ""]
    lines += ["## 限制与下一步", ""] + ["- " + warning for warning in result["warnings"]]
    lines += ["- 对退化case修订Prompt，再用同输入重测；待核实主张先补来源。保持rubric和难例，不因总体均分提高而删除退化。", "- 运营反馈与评分分歧用于校准锚点；演示反馈不能当作真实采纳或耗时成果。", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("cases", "ratings", "rubric", "baseline", "candidate"):
        parser.add_argument("--" + key, required=True)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--md-out", type=Path)
    args = parser.parse_args()
    try:
        inputs = {Path(p).resolve() for p in (args.cases, args.ratings, args.rubric)}
        targets = [p.resolve() for p in (args.json_out, args.md_out) if p]
        require(not set(targets) & inputs and len(targets) == len(set(targets)), "报告路径不能覆盖输入或彼此冲突")
        data, ratings, rubric = [load_json(p) for p in (args.cases, args.ratings, args.rubric)]
        result = summarize(data, ratings, rubric, args.baseline, args.candidate)
        serialized = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if args.json_out:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(serialized, encoding="utf-8")
        if args.md_out:
            args.md_out.parent.mkdir(parents=True, exist_ok=True)
            args.md_out.write_text(markdown(result, data, rubric), encoding="utf-8")
        if not args.json_out and not args.md_out:
            print(serialized, end="")
        else:
            print(json.dumps({"case_count": result["case_count"], "paired_rated_cases": result["paired_rated_cases"], "score_comparable_pairs": result["score_comparable_pairs"], "paired_mean_delta": result["paired_mean_delta"], "readiness": result["readiness"]}, ensure_ascii=False))
        return 0
    except (InputError, OSError, ValueError, TypeError, KeyError) as error:
        print("输入/输出错误：" + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
