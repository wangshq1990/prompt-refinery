#!/usr/bin/env python3
"""F4 领域权威溯源 · 断网（离线）降级分支回归测试。

验证目标：当联网检索失败（断网 / 检索无果）时，skill 必须：
  1. 明确标注「未能联网核实 / 未联网核实」降级标记；
  2. 绝不伪造 URL 或捏造来源（输出中不得出现任何 http(s)/www 链接）；
  3. 给出「关键事实请你自行向权威渠道核实」式护栏提示；
  4. 不输出「参考来源（3）」这种带真实 URL 的溯源块（离线即无来源）。

两层验证：
  A. 静态契约校验：SKILL.md 与 references/authoritative-sourcing.md 是否确实规定了上述
     降级行为（阻断级，保证「skill 说对了」）。
  B. 行为模拟 + 严格扫描：
     - 正向：用契约规定的规范降级文本，跑一遍严格扫描器，证明「离线时 skill 应产出
       的文本」满足：零 URL、有标记、有护栏。
     - 负向（反例）：一段含伪造 URL 的文本必须被扫描器判 FAIL，证明扫描器不是橡皮图章。

可选：传入 --agent-output <path> 可对任意真实 agent 产出的离线文本做同一严格扫描
     （用于人工/agent 实际执行后的准确性复核，保证「结果信息准确、无编造」）。

除可选网络探针外不联网、不写文件（报告仅打印）、不启子进程。
退出码 0=全过，1=有失败。
"""

from __future__ import annotations

import argparse
import re
import socket
import sys
import time
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
SKILL_MD = SKILL / "SKILL.md"
SRC_MD = SKILL / "references" / "authoritative-sourcing.md"

results: list[dict] = []


def record(cid: str, kind: str, expected: str, actual: str, ok: bool, detail: str = "") -> bool:
    results.append({"id": cid, "kind": kind, "expected": expected, "actual": actual, "ok": ok, "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {cid} ({kind}) 期望={expected} 实际={actual} {detail}")
    return ok


# ---------------------------------------------------------------------------
# 严格离线输出扫描器（核心保证：零伪造 URL + 必带降级标记与护栏）
# ---------------------------------------------------------------------------
URL_RE = re.compile(r"https?://[^\s）)，。；]+|www\.[^\s）)，。；]+", re.IGNORECASE)
MARKER_RE = re.compile(r"未(?:能)?联网核实")
CAVEAT_RE = re.compile(r"自行向权威渠道核实")


def validate_offline_output(text: str) -> tuple[bool, list[str]]:
    """返回 (是否合规, 问题列表)。合规 = 有标记 + 有护栏 + 零 URL。"""
    issues: list[str] = []
    urls = URL_RE.findall(text)
    if urls:
        issues.append(f"发现 {len(urls)} 个疑似 URL（离线禁止任何链接）：{urls[:5]}")
    if not MARKER_RE.search(text):
        issues.append("缺少降级标记（『未能联网核实』/『未联网核实』）")
    if not CAVEAT_RE.search(text):
        issues.append("缺少护栏提示（『自行向权威渠道核实』）")
    return (len(issues) == 0), issues


# ---------------------------------------------------------------------------
# 网络探针（仅信息性，不阻断；在线时仍可强制跑离线模拟）
# ---------------------------------------------------------------------------
def probe_network() -> bool:
    for h, p in [("8.8.8.8", 53), ("1.1.1.1", 53), ("www.example.com", 443)]:
        try:
            s = socket.create_connection((h, p), timeout=4)
            s.close()
            return True
        except Exception:
            continue
    return False


# ---------------------------------------------------------------------------
# A. 静态契约校验：skill 文档是否真的规定了离线降级
# ---------------------------------------------------------------------------
def contract_checks() -> None:
    docs = {}
    for name, path in (("SKILL.md", SKILL_MD), ("authoritative-sourcing.md", SRC_MD)):
        docs[name] = path.read_text(encoding="utf-8") if path.exists() else ""
    combined = "\n".join(docs.values())

    has_marker = bool(MARKER_RE.search(combined))
    record("C-marker", "contract", "文档规定降级标记", "存在" if has_marker else "缺失", has_marker)

    no_fake = ("不得伪造 URL" in combined) or ("不得伪造" in combined and "URL" in combined)
    record("C-nofake", "contract", "文档规定『不得伪造 URL』", "存在" if no_fake else "缺失", no_fake)

    has_caveat = bool(CAVEAT_RE.search(combined))
    record("C-caveat", "contract", "文档规定『自行向权威渠道核实』护栏", "存在" if has_caveat else "缺失", has_caveat)

    # 断网即不输出带 URL 的『参考来源（3）』——文档应明确离线无来源
    no_source_when_offline = ("联网失败" in combined) and ("不得伪造" in combined)
    record("C-nosource-offline", "contract", "文档规定联网失败时不输出伪造来源",
           "存在" if no_source_when_offline else "缺失", no_source_when_offline)


# ---------------------------------------------------------------------------
# B. 行为模拟：规范离线文本（忠于契约原文）应通过扫描器
# ---------------------------------------------------------------------------
CANONICAL_OFFLINE = """【角色】
资深税务合规顾问（仅基于通用知识作答，未联网核实）。

【背景】
用户需要一份中国个人所得税专项附加扣除的合规说明，但本次环境联网检索失败。

【目标】
给出专项附加扣除的通用要点清单，并明确提示关键数字与政策以权威渠道为准。

【约束】
1. 不编造具体文号、条款序号或官方链接；
2. 不给出确定性税务结论，仅作通用科普；
3. 标注「未能联网核实」。

【格式】
分层要点 + 一句式护栏。

【真实数据】
未能联网核实，以下内容基于通用知识，关键事实请你自行向权威渠道核实（如国家税务总局官网、个人所得税 APP）。本次不列出参考来源，以免给出未经核实的链接或捏造出处。

专项附加扣除常见项目（通用认知，非最新口径）：
- 子女教育
- 继续教育
- 大病医疗
- 住房贷款利息
- 住房租金
- 赡养老人
- 3 岁以下婴幼儿照护
具体扣除标准与适用条件请以国家税务总局最新公告及个人所得税 APP 为准。
"""


def behavioral_checks(force_offline: bool) -> None:
    ok, issues = validate_offline_output(CANONICAL_OFFLINE)
    record("B-positive", "behavior", "规范离线文本应通过扫描（零URL+标记+护栏）",
           "通过" if ok else f"未通过:{issues}", ok, "" if ok else "；".join(issues))

    # 负向反例：含伪造 URL 的文本必须被扫描器判 FAIL（证明扫描器有效）
    fake = ("未能联网核实，以下内容基于通用知识，关键事实请你自行向权威渠道核实。"
            "参考来源：国家税务总局 https://www.chinatax.gov.cn/fake-verify-99812 。")
    ok_fake, _ = validate_offline_output(fake)
    record("B-negative", "behavior", "含伪造URL的反例必须判FAIL",
           "正确拦截" if not ok_fake else "未拦截(缺陷)", not ok_fake)


def main() -> int:
    ap = argparse.ArgumentParser(description="F4 断网降级分支回归测试")
    ap.add_argument("--agent-output", type=Path, help="可选：对真实 agent 离线产出文本做严格扫描")
    ap.add_argument("--force-offline", action="store_true", help="即便在线也强制跑离线模拟（默认：在线时也跑模拟但标注）")
    args = ap.parse_args()

    print("=== F4 断网降级分支回归 ===")
    online = probe_network()
    print(f"环境网络探针：{'ONLINE' if online else 'OFFLINE'}"
          + ("" if (online and not args.force_offline) else "（将执行/已执行离线分支）"))

    print("\n--- A. 静态契约校验 ---")
    contract_checks()

    print("\n--- B. 行为模拟 + 严格扫描 ---")
    behavioral_checks(force_offline=args.force_offline or not online)

    if args.agent_output is not None:
        print(f"\n--- C. 真实 agent 离线产出复核：{args.agent_output} ---")
        if not args.agent_output.exists():
            record("C-agent", "agent", "文件存在", "缺失", False)
        else:
            txt = args.agent_output.read_text(encoding="utf-8")
            ok, issues = validate_offline_output(txt)
            record("C-agent", "agent", "真实离线产出应通过扫描（零URL+标记+护栏）",
                   "通过" if ok else f"未通过:{issues}", ok, "" if ok else "；".join(issues))

    failed = [r for r in results if not r["ok"]]
    print(f"\n===== 汇总：{len(results) - len(failed)}/{len(results)} 通过 =====")
    if failed:
        for r in failed:
            print(f"  失败 {r['id']}: {r['detail']}")
        return 1
    print("全部通过。F4 离线降级契约与扫描器均正确。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
