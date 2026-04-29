#!/usr/bin/env bash
# Symlink each skill's SKILL.md into ~/.claude/skills/<name>/ so Claude Code
# discovers it. Idempotent — safe to re-run.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILLS_ROOT="${HOME}/.claude/skills"

mkdir -p "${SKILLS_ROOT}"

install_skill() {
  local skill_name="$1"
  local source_md="${REPO_ROOT}/packages/${skill_name}/skill/SKILL.md"
  local target_dir="${SKILLS_ROOT}/${skill_name}"
  local target_md="${target_dir}/SKILL.md"

  if [[ ! -f "${source_md}" ]]; then
    echo "skip: ${skill_name} (no SKILL.md at ${source_md})" >&2
    return
  fi

  mkdir -p "${target_dir}"

  # Replace any existing entry (file or symlink). Never delete a non-symlink
  # without showing what we're overwriting.
  if [[ -L "${target_md}" ]]; then
    rm "${target_md}"
  elif [[ -e "${target_md}" ]]; then
    echo "warning: ${target_md} exists and is not a symlink; backing up" >&2
    mv "${target_md}" "${target_md}.bak.$(date -u +%Y%m%dT%H%M%SZ)"
  fi

  ln -s "${source_md}" "${target_md}"
  echo "installed: ${target_md} → ${source_md}"
}

install_skill "azure-cost-investigator"
install_skill "azure-security-investigator"

echo "done. claude code will discover the skills on next launch."
