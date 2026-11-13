#!/usr/bin/env python3
"""Forced Convergence 确定性组装与校验器。

读取结构化输入（JSON，来自 --input 文件或标准输入），把五要素拼成最终提示词，
并做覆盖率与约束冲突检查。默认只打印到屏幕；仅当显式传入 --output 才写文件。

设计约束：不联网、不启动子进程、不读取环境变量、不执行任何外部内容。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REQUIRED = ("role", "context", "goal", "constraints", "format")
SLOT_LABELS = {
    "role": "角色",
    "context": "背景",
    "goal": "目标",
    "constraints": "约束",
    "format": "格式",
    "acceptance": "验收",
    "realdata": "真实数据",
}


def load_input(text: str) -> dict:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"输入不是合法 JSON：{exc}")
    if not isinstance(data, dict):
        raise SystemExit("输入必须是 JSON 对象")
    return data


def render_prompt(data: dict) -> str:
    blocks: list[str] = []
    if data.get("role"):
        blocks.append(f"【角色】\n{str(data['role']).strip()}")
    if data.get("context"):
        blocks.append(f"【背景】\n{str(data['context']).strip()}")
    if data.get("goal"):
        blocks.append(f"【目标】\n{str(data['goal']).strip()}")
    constraints = data.get("constraints")
    if isinstance(constraints, list):
        lines = "\n".join(f"{i}. {str(c).strip()}" for i, c in enumerate(constraints, 1) if str(c).strip())
        if lines:
            blocks.append(f"【约束】\n{lines}")
    elif isinstance(constraints, str) and constraints.strip():
        blocks.append(f"【约束】\n{constraints.strip()}")
    if data.get("format"):
        blocks.append(f"【格式】\n{str(data['format']).strip()}")
    if data.get("acceptance"):
        blocks.append(f"【验收】\n{str(data['acceptance']).strip()}")
    realdata = data.get("realdata")
    if isinstance(realdata, list):
        lines = "\n".join(f"{i}. {str(c).strip()}" for i, c in enumerate(realdata, 1) if str(c).strip())
        if lines:
            blocks.append(f"【真实数据】\n{lines}")
    elif isinstance(realdata, str) and realdata.strip():
        blocks.append(f"【真实数据】\n{realdata.strip()}")
    return "\n\n".join(blocks)


def coverage_report(data: dict) -> list[str]:
    return [slot for slot in REQUIRED if not data.get(slot)]


def conflict_report(data: dict) -> list[str]:
    warnings: list[str] = []
    constraints = data.get("constraints")
    if isinstance(constraints, str):
        constraints = [constraints]
    if not isinstance(constraints, list):
        constraints = []
    ctext = " ".join(str(c) for c in constraints)
    goal = str(data.get("goal") or "")
    fmt = str(data.get("format") or "")

    has_word_limit = bool(re.search(r"字\s*数|字\s*以内|字\s*内|\d+\s*字", ctext))
    has_table = "表格" in fmt or "表" in fmt
    numbered = len(re.findall(r"\d+\.", goal))
    if has_word_limit and has_table and numbered >= 3:
        warnings.append(
            "约束含字数上限 + 格式为表格 + 目标含>=3个必须项：模型可能为凑字数牺牲论证深度，建议放宽字数或拆分任务。"
        )
    clean = [c for c in constraints if str(c).strip()]
    if len(clean) > 4:
        warnings.append("约束超过 4 条：建议标注优先级（硬约束 vs 软偏好），避免模型平均用力。")
    if has_word_limit and ("详尽" in ctext or "详细" in ctext):
        warnings.append("约束同时要求『极短字数』与『详尽/详细』，存在语义互斥。")
    return warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Forced Convergence 提示词组装与校验器")
    parser.add_argument("--input", type=Path, help="JSON 输入文件；省略则读标准输入")
    parser.add_argument("--output", type=Path, help="可选：将最终提示词写入该文件（默认只打印）")
    parser.add_argument("--json", action="store_true", help="以一行 JSON 输出结构化结果（coverage/conflicts/prompt），不打印人类可读报告")
    args = parser.parse_args()

    if args.input is not None:
        text = args.input.read_text(encoding="utf-8-sig")
    else:
        text = sys.stdin.read()
    data = load_input(text)

    missing = coverage_report(data)
    warnings = conflict_report(data)
    prompt = render_prompt(data)

    if args.json:
        payload = {
            "coverage": {
                "missing": missing,
                "status": "COMPLETE" if not missing else "INCOMPLETE",
            },
            "conflicts": warnings,
            "prompt": prompt,
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 1 if missing else 0

    print("=== 覆盖率 ===")
    if missing:
        print("缺失必需槽位：" + ", ".join(SLOT_LABELS[m] for m in missing))
        print("状态：INCOMPLETE")
    else:
        print("五个必需槽位齐全。")
        print("状态：COMPLETE")

    if warnings:
        print("\n=== 约束冲突警告 ===")
        for w in warnings:
            print("- " + w)

    print("\n=== 最终提示词 ===")
    print(prompt)

    if args.output is not None:
        args.output.write_text(prompt + "\n", encoding="utf-8", newline="\n")
        print(f"\n已写入：{args.output}")

    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
