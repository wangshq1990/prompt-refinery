#!/bin/bash
# sync_to_skills.sh
# 把 prompt-refinery 仓库的"技能本体"同步到 WorkBuddy 技能目录，使其立即生效。
# 仅同步 SKILL.md + references/ + scripts/，刻意排除 .git / .gitignore / LICENSE / README.md
# （这些不是 WorkBuddy 技能需要的文件，避免污染技能目录）。
#
# 触发方式：
#   1) 手动：在仓库根目录运行 ./sync_to_skills.sh
#   2) 自动：被 .git/hooks/post-commit 在每次 commit 后调用
#
# 注意：本脚本只做"本地生效"的同步，不负责 git push（推送请单独执行）。

set -u

SRC="$(cd "$(dirname "$0")" && pwd)"
DST="${HOME}/.workbuddy/skills/prompt-refinery"
PY="C:/Users/sqwan/.workbuddy/binaries/python/versions/3.13.12/python.exe"

echo "==> 同步源 : $SRC"
echo "==> 同步目标: $DST"

if [ ! -f "$SRC/SKILL.md" ]; then
  echo "!!! 错误：源 SKILL.md 不存在，请确认在仓库根目录运行本脚本。" >&2
  exit 1
fi

mkdir -p "$DST"

# 复制技能本体（先清后拷，避免残留旧文件）
cp -f "$SRC/SKILL.md" "$DST/SKILL.md"
rm -rf "$DST/references" "$DST/scripts"
cp -r "$SRC/references" "$DST/references"
cp -r "$SRC/scripts" "$DST/scripts"

echo "==> 已同步。目标文件数: $(find "$DST" -type f | wc -l)"

# 自检（信息性，失败不阻断同步）
if [ -x "$PY" ] && [ -f "$DST/scripts/selftest.py" ]; then
  echo "==> 运行 selftest 自检..."
  if "$PY" "$DST/scripts/selftest.py" > /tmp/pr_sync_selftest.log 2>&1; then
    tail -2 /tmp/pr_sync_selftest.log
    echo "==> selftest: 通过"
  else
    echo "!!! selftest 未通过，详见 /tmp/pr_sync_selftest.log（同步已完成，请检查）" >&2
    tail -5 /tmp/pr_sync_selftest.log >&2
  fi
else
  echo "==> 跳过 selftest（python 或 selftest.py 缺失）"
fi

echo "==> 完成。WorkBuddy 重新加载/下次调用该技能即生效。"
