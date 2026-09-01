from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "apply-codex-policy.py"


class ApplyCodexPolicyTests(unittest.TestCase):
    def make_skill(
        self, root: Path, name: str, metadata: str | None = None
    ) -> Path:
        skill = root / "skills" / name
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            f"---\nname: {name}\n---\n", encoding="utf-8"
        )
        if metadata is not None:
            agents = skill / "agents"
            agents.mkdir()
            (agents / "openai.yaml").write_text(metadata, encoding="utf-8")
        return skill

    def make_complete_fixture(self, root: Path) -> None:
        self.make_skill(root, "systematic-debugging")
        self.make_skill(root, "verification-before-completion")
        self.make_skill(root, "brainstorming")

    def run_script(self, root: Path, *, check: bool = False) -> subprocess.CompletedProcess[str]:
        command = [sys.executable, str(SCRIPT), "--root", str(root)]
        if check:
            command.append("--check")
        return subprocess.run(command, capture_output=True, text=True, check=False)

    def metadata(self, root: Path, skill: str) -> str:
        return (root / "skills" / skill / "agents" / "openai.yaml").read_text(
            encoding="utf-8"
        )

    def test_apply_creates_allowlisted_and_explicit_only_sidecars(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_complete_fixture(root)

            result = self.run_script(root)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                "allow_implicit_invocation: true",
                self.metadata(root, "systematic-debugging"),
            )
            self.assertIn(
                "allow_implicit_invocation: true",
                self.metadata(root, "verification-before-completion"),
            )
            self.assertIn(
                "allow_implicit_invocation: false",
                self.metadata(root, "brainstorming"),
            )

    def test_apply_preserves_unrelated_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_skill(root, "systematic-debugging")
            self.make_skill(root, "verification-before-completion")
            self.make_skill(
                root,
                "brainstorming",
                "interface:\n"
                "  display_name: Brainstorming\n"
                "policy:\n"
                "  another_flag: keep\n"
                "  allow_implicit_invocation: true\n",
            )

            result = self.run_script(root)
            metadata = self.metadata(root, "brainstorming")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("display_name: Brainstorming", metadata)
            self.assertIn("another_flag: keep", metadata)
            self.assertIn("allow_implicit_invocation: false", metadata)

    def test_apply_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_complete_fixture(root)

            first = self.run_script(root)
            before = {
                path: path.read_bytes()
                for path in sorted(root.glob("skills/*/agents/openai.yaml"))
            }
            second = self.run_script(root)
            after = {path: path.read_bytes() for path in before}

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(before, after)

    def test_check_reports_policy_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_complete_fixture(root)
            applied = self.run_script(root)
            self.assertEqual(applied.returncode, 0, applied.stderr)
            metadata_path = root / "skills" / "brainstorming" / "agents" / "openai.yaml"
            metadata_path.write_text(
                metadata_path.read_text(encoding="utf-8").replace("false", "true"),
                encoding="utf-8",
            )

            result = self.run_script(root, check=True)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("brainstorming", result.stderr)

    def test_missing_allowlisted_skill_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_skill(root, "systematic-debugging")

            apply_result = self.run_script(root)
            check_result = self.run_script(root, check=True)

            self.assertNotEqual(apply_result.returncode, 0)
            self.assertNotEqual(check_result.returncode, 0)
            self.assertIn("verification-before-completion", apply_result.stderr)
            self.assertIn("verification-before-completion", check_result.stderr)


if __name__ == "__main__":
    unittest.main()
