#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ALLOW_IMPLICIT = frozenset(
    {
        "systematic-debugging",
        "verification-before-completion",
    }
)

TOP_LEVEL_KEY = re.compile(r"^([A-Za-z0-9_.-]+)\s*:")
POLICY_HEADER = re.compile(r"^policy:\s*(?:#.*)?$")
INVOCATION_KEY = re.compile(r"^  allow_implicit_invocation\s*:")
INVOCATION_ENTRY = re.compile(
    r"^  allow_implicit_invocation:\s*(?:true|false)\s*(?:#.*)?$"
)


class PolicyError(RuntimeError):
    pass


def discover_skills(root: Path) -> dict[str, Path]:
    skills_root = root / "skills"
    if not skills_root.is_dir():
        raise PolicyError(f"skills directory not found: {skills_root}")

    return {
        skill_dir.name: skill_dir
        for skill_dir in sorted(skills_root.iterdir())
        if skill_dir.is_dir() and (skill_dir / "SKILL.md").is_file()
    }


def _line_ending(line: str) -> str:
    if line.endswith("\r\n"):
        return "\r\n"
    return "\n"


def render_metadata(current: str, allow_implicit: bool) -> str:
    value = "true" if allow_implicit else "false"
    if not current:
        return f"policy:\n  allow_implicit_invocation: {value}\n"

    lines = current.splitlines(keepends=True)
    if lines and not lines[-1].endswith(("\n", "\r")):
        lines[-1] += "\n"

    policy_indexes: list[int] = []
    for index, line in enumerate(lines):
        content = line.rstrip("\r\n")
        key_match = TOP_LEVEL_KEY.match(content)
        if key_match and key_match.group(1) == "policy":
            if not POLICY_HEADER.fullmatch(content):
                raise PolicyError("unsupported policy key or inline mapping")
            policy_indexes.append(index)

    if len(policy_indexes) > 1:
        raise PolicyError("duplicate top-level policy blocks")

    if not policy_indexes:
        lines.extend(
            [
                "policy:\n",
                f"  allow_implicit_invocation: {value}\n",
            ]
        )
        return "".join(lines)

    policy_index = policy_indexes[0]
    block_end = len(lines)
    for index in range(policy_index + 1, len(lines)):
        content = lines[index].rstrip("\r\n")
        if TOP_LEVEL_KEY.match(content):
            block_end = index
            break

    invocation_indexes = [
        index
        for index in range(policy_index + 1, block_end)
        if INVOCATION_KEY.match(lines[index].rstrip("\r\n"))
    ]
    if len(invocation_indexes) > 1:
        raise PolicyError("duplicate allow_implicit_invocation entries")

    if invocation_indexes:
        index = invocation_indexes[0]
        content = lines[index].rstrip("\r\n")
        if not INVOCATION_ENTRY.fullmatch(content):
            raise PolicyError("unsupported allow_implicit_invocation entry")
        lines[index] = (
            f"  allow_implicit_invocation: {value}{_line_ending(lines[index])}"
        )
    else:
        ending = _line_ending(lines[policy_index])
        lines.insert(
            block_end,
            f"  allow_implicit_invocation: {value}{ending}",
        )

    return "".join(lines)


def apply_policy(root: Path, check: bool) -> list[str]:
    skills = discover_skills(root)
    missing = sorted(ALLOW_IMPLICIT.difference(skills))
    if missing:
        raise PolicyError(f"allowlisted skills not found: {', '.join(missing)}")

    changed: list[str] = []
    for name, skill_dir in skills.items():
        metadata_path = skill_dir / "agents" / "openai.yaml"
        if metadata_path.exists():
            with metadata_path.open("r", encoding="utf-8", newline="") as metadata:
                current = metadata.read()
        else:
            current = ""
        expected = render_metadata(current, name in ALLOW_IMPLICIT)
        if current == expected:
            continue
        changed.append(name)
        if not check:
            metadata_path.parent.mkdir(parents=True, exist_ok=True)
            with metadata_path.open("w", encoding="utf-8", newline="") as metadata:
                metadata.write(expected)

    if check and changed:
        raise PolicyError(f"policy drift: {', '.join(changed)}")

    if not check:
        drift = []
        for name, skill_dir in skills.items():
            metadata_path = skill_dir / "agents" / "openai.yaml"
            with metadata_path.open("r", encoding="utf-8", newline="") as metadata:
                current = metadata.read()
            if render_metadata(current, name in ALLOW_IMPLICIT) != current:
                drift.append(name)
        if drift:
            raise PolicyError(f"policy verification failed: {', '.join(drift)}")

    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply Codex skill invocation policy")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (default: parent of scripts directory)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="report policy drift without changing files",
    )
    args = parser.parse_args()

    try:
        changed = apply_policy(args.root.resolve(), args.check)
    except (OSError, PolicyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    if args.check:
        skill_count = len(discover_skills(args.root.resolve()))
        print(f"checked {skill_count} skill policies; no drift")
    else:
        print(f"updated {len(changed)} skill policies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
