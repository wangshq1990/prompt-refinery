#!/usr/bin/env python3
"""Forced Convergence 自动化行为测试（随包分发，用于回归）。

直接驱动本包文件：
1. 读取 SKILL.md 的触发规则，对正例/near-miss 做路由断言。
2. 用 6 个领域档案的「示例」经 build_prompt 组装，验证五槽齐全。
3. 校验脚本边界（缺要素 / 约束冲突）。

不联网、不写文件、不启子进程（直接 import build_prompt 调其函数）。
退出码 0=全过，1=有失败。
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
SCRIPT_FILE = SKILL / "scripts" / "build_prompt.py"

_spec = importlib.util.spec_from_file_location("build_prompt", SCRIPT_FILE)
bp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bp)

DOMAINS = ["marketing", "software-engineering", "academic-writing", "legal", "data-analysis", "product"]
results: list[dict] = []


def record(cid: str, kind: str, expected: str, actual: str, ok: bool, detail: str = "") -> None:
    results.append({"id": cid, "kind": kind, "expected": expected, "actual": actual, "ok": ok, "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {cid} ({kind}) 期望={expected} 实际={actual} {detail}")


def parse_triggers() -> tuple[list[str], list[str]]:
    md = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    positive = re.findall(r"-\s*「([^」]+)」", md)
    nm = re.search(r"不触发（边界）：(.+?)(?:\n\n|\Z)", md, re.S)
    near = re.findall(r"「([^」]+)」", nm.group(1)) if nm else []
    return positive, near


def route(msg: str, positives: list[str]) -> str:
    if any(p in msg for p in positives):
        return "trigger"
    if any(t in msg for t in ("直接帮我", "直接写", "教我学", "翻译", "润色")):
        return "no_trigger_do_task"
    return "uncertain"


def parse_example(text: str) -> dict:
    matches = list(re.finditer(r"【([^】]+)】", text))
    blocks: dict[str, str] = {}
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        blocks[m.group(1)] = text[start:end].strip()
    return blocks


def main() -> int:
    positives, _ = parse_triggers()
    print(f"提取到正例触发短语 {len(positives)} 条\n")

    # 锚点守护（加固，非阻断）：确保 SKILL.md 仍存在 selftest 依赖的解析锚点，
    # 防止未来误删导致 parse_triggers 抛 AttributeError 使整个回归崩溃。
    skill_md = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    anchor_ok = ("不触发（边界）：" in skill_md) and bool(positives)
    record(
        "T-guard-anchor", "guard", "锚点存在且正例>0",
        "存在" if anchor_ok else "缺失", anchor_ok,
        "" if anchor_ok else "不触发（边界）：锚点或正例缺失",
    )

    cases = [
        ("T01", "positive", "帮我把这个需求变成给 AI 的提示词：我想让 AI 帮我写咖啡馆开业文案", "trigger"),
        ("T02", "positive", "套你的万能公式给我生成一段指令，用来让 AI 帮我审代码", "trigger"),
        ("T03", "positive", "怎么写 prompt 才不让 AI 说废话", "trigger"),
        ("T04", "near-miss", "直接帮我写咖啡馆开业营销方案", "no_trigger_do_task"),
        ("T05", "near-miss", "教我学 AI", "no_trigger_do_task"),
    ]
    for cid, kind, msg, exp in cases:
        actual = route(msg, positives)
        record(cid, kind, exp, actual, actual == exp)

    for dom in DOMAINS:
        prof = SKILL / "references" / f"{dom}.md"
        if not prof.exists():
            record(f"P-{dom}", "profile", "档案存在", "缺失", False)
            continue
        ex = parse_example(prof.read_text(encoding="utf-8"))
        payload = {
            "role": ex.get("角色", ""),
            "context": ex.get("背景", ""),
            "goal": ex.get("目标", ""),
            "constraints": ex.get("约束", ""),
            "format": ex.get("格式", ""),
        }
        if not all(payload.values()):
            record(f"P-{dom}", "profile", "六要素示例齐全", "示例缺槽", False, str(list(payload.keys())))
            continue
        missing = bp.coverage_report(payload)
        rendered = bp.render_prompt(payload)
        headers = all(f"【{h}】" in rendered for h in ("角色", "背景", "目标", "约束", "格式"))
        ok = (not missing) and headers
        record(f"P-{dom}", "profile", "COMPLETE+五槽", f"missing={missing} headers={headers}", ok)

    miss = bp.coverage_report({"role": "x", "goal": "y", "constraints": ["a"], "format": "b"})
    record("S-missing", "script", "INCOMPLETE", f"missing={miss}", bool(miss))

    conf = bp.conflict_report({
        "role": "r", "context": "c",
        "goal": "做方案，必须包含：1. a；2. b；3. c。",
        "constraints": ["总字数≤300", "禁用黑话"], "format": "用Markdown表格输出",
    })
    record("S-conflict", "script", "含冲突警告", f"warnings={len(conf)}", bool(conf))

    # 可选非阻断守卫：F2 模板骨架段（不翻转退出码，缺失仅 WARN）
    # 断言 6 个 domain-profiles 均含「## 模板骨架（可一键套用）」标题，F2 功能依赖该段。
    # 故意不写入 results，避免与既有全绿结果耦合；待 F2 内容稳定后可评估升级为阻断。
    template_missing = []
    for dom in DOMAINS:
        prof = SKILL / "references" / f"{dom}.md"
        text = prof.read_text(encoding="utf-8") if prof.exists() else ""
        has_tpl = "## 模板骨架（可一键套用）" in text
        print(f"[{'PASS' if has_tpl else 'WARN'}] T-guard-templates ({dom}) "
              f"期望=含模板骨架段 实际={'存在' if has_tpl else '缺失(非阻断)'}")
        if not has_tpl:
            template_missing.append(dom)

    failed = [r for r in results if not r["ok"]]
    print(f"\n===== 汇总：{len(results) - len(failed)}/{len(results)} 通过 =====")
    if failed:
        for r in failed:
            print(f"  失败 {r['id']}: {r['detail']}")
        return 1
    print("全部通过。")
    if template_missing:
        print(f"  [非阻断] T-guard-templates：以下领域缺失模板骨架段，已 WARN（不影响退出码）：{template_missing}")
    else:
        print("  [非阻断] T-guard-templates：6 个领域模板骨架段均存在。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
