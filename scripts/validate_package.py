#!/usr/bin/env python3
"""Offline, read-only package checks. This never evaluates model output quality."""
import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

SKILLS = ("ai-copy-reviewer", "requirement-to-acceptance", "evidence-based-teardown")


def check_package(root, archive=None):
    errors = []

    def check(ok, message):
        if not ok:
            errors.append(message)

    check(root.is_dir(), "包目录不存在")
    for required in ("README.md", "LICENSE", "TEST_REPORT.md", "tests/RUBRIC.md", "tests/cases.json"):
        check((root / required).is_file(), "缺少 " + required)
    for name in SKILLS:
        folder = root / "skills" / name
        entry = folder / "SKILL.md"
        check(entry.is_file(), name + ": 缺少SKILL.md")
        if not entry.is_file():
            continue
        content = entry.read_text(encoding="utf-8")
        match = re.match(r"\A---\n(.*?)\n---\n", content, re.S)
        check(match is not None, name + ": 前言格式错误")
        if match:
            fields = dict(re.findall(r"^([a-z-]+): ([^\n]+)$", match.group(1), re.M))
            check(fields.get("name") == name, name + ": name与目录不一致")
            check(0 < len(fields.get("description", "")) <= 1024, name + ": description缺失/过长")
            check(fields.get("license") == "MIT", name + ": 缺少MIT标识")
            check("author: Yan-Shuang" in match.group(1), name + ": 缺少作者署名")
        check(len(content.splitlines()) < 500, name + ": 入口过长")
        ui = folder / "agents/openai.yaml"
        check(ui.is_file(), name + ": 缺少openai.yaml")
        if ui.is_file():
            ui_text = ui.read_text(encoding="utf-8")
            check(re.search(r"^  allow_implicit_invocation: true$", ui_text, re.M), name + ": 未开启隐式调用")
            for key in ("display_name", "short_description", "default_prompt"):
                value = re.search(r'^  ' + key + r': "([^"\n]+)"$', ui_text, re.M)
                check(value is not None, name + ": UI字段缺失或未加引号: " + key)
                if value and key == "short_description":
                    check(25 <= len(value.group(1)) <= 64, name + ": UI简介长度不合要求")
                if value and key == "default_prompt":
                    check("$" + name in value.group(1), name + ": 默认提示未显式调用技能")
        examples = folder / "references/examples.md"
        check(examples.is_file(), name + ": 缺少示例")
        if examples.is_file():
            example_text = examples.read_text(encoding="utf-8")
            check(len(re.findall(r"^## [1-9]\d*\.", example_text, re.M)) >= 3, name + ": 少于三组示例")
            check(example_text.count("输入：") >= 3 and example_text.count("输出示范：") >= 3, name + ": 输入/输出示例缺失")
        check((folder / "LICENSE").is_file(), name + ": 缺少可独立安装的许可证")

    files = {}
    path_fragments = ("/" + "Users/", "/" + "home/", "C:" + "\\Users\\")
    private_markers = ("-----BEGIN " + "PRIVATE KEY-----", "sk-" + "proj-", "gh" + "p_")
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if Path(rel).parts[0] == ".git":
            continue
        check(not path.is_symlink(), rel + ": 不应含符号链接")
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix in (".pyc", ".zip") or path.name == ".DS_Store":
            errors.append(rel + ": 包内含临时/嵌套归档文件")
            continue
        check(path.name not in (".env", "auth.json", "config.toml"), rel + ": 不应包含本地配置")
        check(path.suffix in (".md", ".json", ".py", ".yaml") or path.name in ("LICENSE", ".gitignore"), rel + ": 未识别文件类型")
        data = path.read_bytes()
        files[rel] = data
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            errors.append(rel + ": 不是UTF-8文本")
            continue
        check(not any(marker in text for marker in path_fragments), rel + ": 包含机器绝对路径")
        check(not any(marker in text for marker in private_markers), rel + ": 包含疑似凭据片段")
        check("[" + "TODO:" not in text, rel + ": 存在未完成脚手架")
        if path.suffix == ".md":
            for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
                if "://" in target or target.startswith("#"):
                    continue
                target = target.split("#", 1)[0]
                resolved = (path.parent / target).resolve()
                check(root.resolve() == resolved or root.resolve() in resolved.parents, rel + ": 引用越过包目录")
                check(resolved.is_file(), rel + ": 引用不存在: " + target)

    cases_path = root / "tests/cases.json"
    cases = []
    try:
        payload = json.loads(cases_path.read_text(encoding="utf-8"))
        check(payload.get("schema_version") == 1, "用例schema_version错误")
        cases = payload["cases"]
        check(isinstance(cases, list) and 15 <= len(cases) <= 30, "用例总数须为15–30")
        ids = set()
        for item in cases:
            ident = item.get("id", "")
            check(bool(re.fullmatch(r"[A-Z]{2}\d{2}", ident)) and ident not in ids, "用例id无效或重复: " + str(ident))
            ids.add(ident)
            check(item.get("skill") in SKILLS, ident + ": skill无效")
            for key in ("category", "prompt"):
                check(isinstance(item.get(key), str) and item[key].strip(), ident + ": 缺少 " + key)
            for key in ("must_include_checks", "forbidden_behavior"):
                values = item.get(key)
                check(isinstance(values, list) and len(values) >= 2 and all(isinstance(v, str) and v.strip() for v in values), ident + ": 检查点格式错误: " + key)
        for name in SKILLS:
            subset = [case for case in cases if case.get("skill") == name]
            check(len(subset) >= 3, name + ": 用例不足")
            categories = {case.get("category") for case in subset}
            check({"qualified", "conflict", "missing_evidence", "scope"} <= categories, name + ": 缺少核心边界用例")
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        errors.append("用例JSON无效: " + type(error).__name__)

    if archive:
        try:
            with zipfile.ZipFile(archive) as package:
                expected = {root.name + "/" + rel: data for rel, data in files.items()}
                names = package.namelist()
                check(len(names) == len(set(names)), "ZIP含重复条目")
                check(set(names) == set(expected), "ZIP文件集合与包目录不一致")
                check(package.testzip() is None, "ZIP校验失败")
                for info in package.infolist():
                    parts = Path(info.filename).parts
                    check(not info.filename.startswith("/") and ".." not in parts, "ZIP路径不安全")
                    check((info.external_attr >> 16) & 0o170000 != 0o120000, "ZIP含符号链接")
                    if info.filename in expected:
                        check(package.read(info.filename) == expected[info.filename], "ZIP字节不一致: " + info.filename)
        except (OSError, zipfile.BadZipFile):
            errors.append("ZIP不能读取")
    return {"ok": not errors, "scope": "structure_only_no_semantic_score", "skills": len(SKILLS), "eval_cases": len(cases), "files": len(files), "archive_checked": bool(archive), "errors": errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--zip", type=Path, dest="archive")
    args = parser.parse_args()
    result = check_package(args.root, args.archive)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
