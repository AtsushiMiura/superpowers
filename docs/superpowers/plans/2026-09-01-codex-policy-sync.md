# Codex Policy Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a daily-updated `my-codex-policy` branch in `AtsushiMiura/superpowers` where only systematic debugging and verification may be invoked implicitly.

**Architecture:** A dependency-free Python script discovers every skill and creates or updates its `agents/openai.yaml` policy. One GitHub Actions workflow merges upstream into the fork's `main`, regenerates `my-codex-policy`, validates it, and pushes only to the fork.

**Tech Stack:** Python 3 standard library, `unittest`, Git, GitHub Actions

**Spec:** `docs/superpowers/specs/2026-09-01-codex-policy-sync-design.md`

## Global Constraints

- Allow implicit invocation only for `systematic-debugging` and `verification-before-completion`.
- Set every other existing or newly discovered skill to explicit-only.
- Push only to `AtsushiMiura/superpowers`; never modify `obra/superpowers`.
- Keep `obra/superpowers` fetch-only.
- Do not add keepalive commits, state files, third-party Actions, or runtime dependencies.
- Treat `my-codex-policy` as generated output.

---

## File Map

- `scripts/apply-codex-policy.py`: discover skills, minimally edit policy sidecars, and verify final values.
- `tests/codex-policy/test_apply_codex_policy.py`: exercise creation, preservation, idempotence, drift detection, and missing-allowlist failure.
- `.github/workflows/sync-codex-policy.yml`: daily/manual upstream synchronization and generated-branch publication.
- `docs/superpowers/specs/2026-09-01-codex-policy-sync-design.md`: already-created design contract; update only if implementation reveals a contradiction.

### Task 1: Policy Generator

**Files:**
- Create: `scripts/apply-codex-policy.py`
- Create: `tests/codex-policy/test_apply_codex_policy.py`

**Interfaces:**
- Consumes: a repository root containing `skills/<name>/SKILL.md`.
- Produces: `skills/<name>/agents/openai.yaml` with the expected Boolean policy.
- CLI: `python3 scripts/apply-codex-policy.py [--root PATH] [--check]`.
- Exit status: `0` on success; nonzero for missing allowlisted skills, unsupported duplicate policy keys, or policy drift in check mode.

- [ ] **Step 1: Write failing CLI tests**

Create fixtures in temporary directories and invoke the real script as a subprocess. The test module should cover these behaviors:

```python
ALLOWLIST = {"systematic-debugging", "verification-before-completion"}

def make_skill(root: Path, name: str, metadata: str | None = None) -> Path:
    skill = root / "skills" / name
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8")
    if metadata is not None:
        agents = skill / "agents"
        agents.mkdir()
        (agents / "openai.yaml").write_text(metadata, encoding="utf-8")
    return skill
```

Required test cases:

1. Applying to the two allowlisted skills plus `brainstorming` creates `true`, `true`, and `false` sidecars.
2. Existing `interface` metadata and another `policy` key remain present while `allow_implicit_invocation` changes.
3. Applying twice leaves every generated file byte-for-byte unchanged.
4. `--check` fails after manually changing a generated value.
5. Apply and check both fail when either allowlisted skill is absent.

- [ ] **Step 2: Run the tests and verify the expected failure**

Run:

```bash
python3 -m unittest discover -s tests/codex-policy -p 'test_*.py' -v
```

Expected: FAIL because `scripts/apply-codex-policy.py` does not exist.

- [ ] **Step 3: Implement the minimal dependency-free generator**

Implement this constant and these exact function interfaces:

```python
ALLOW_IMPLICIT = frozenset({
    "systematic-debugging",
    "verification-before-completion",
})
```

- `discover_skills(root: Path) -> dict[str, Path]`
- `render_metadata(current: str, allow_implicit: bool) -> str`
- `apply_policy(root: Path, check: bool) -> list[str]`
- `main() -> int`

`render_metadata` must use a narrow line-oriented edit:

- When the file is absent or empty, emit only the `policy` mapping.
- When no top-level `policy:` block exists, append one after a single newline.
- When the block exists, replace or insert its two-space-indented `allow_implicit_invocation` entry.
- Preserve every unrelated line exactly.
- Reject duplicate top-level `policy:` blocks or duplicate invocation entries instead of guessing.
- Preserve a final newline and write only when bytes change.

`apply_policy` must discover skills from `skills/*/SKILL.md`, verify both allowlisted names exist, render the expected content for each sidecar, and either write it or report drift in `--check` mode. After applying, run the same comparison once more so success means every file matches the expected rendering.

- [ ] **Step 4: Run the focused tests**

Run:

```bash
python3 -m unittest discover -s tests/codex-policy -p 'test_*.py' -v
```

Expected: all tests PASS.

- [ ] **Step 5: Exercise the generator against the real checkout**

Use a temporary copy or temporary worktree so the feature branch does not retain generated sidecars:

```bash
tmp_dir="$(mktemp -d)"
git archive HEAD | tar -x -C "$tmp_dir"
python3 scripts/apply-codex-policy.py --root "$tmp_dir"
python3 scripts/apply-codex-policy.py --root "$tmp_dir" --check
```

Expected: both commands succeed; exactly two generated files contain `true`, and all other generated policy files contain `false`.

- [ ] **Step 6: Commit the policy generator**

```bash
git add scripts/apply-codex-policy.py tests/codex-policy/test_apply_codex_policy.py
git commit -m "feat: generate Codex skill invocation policy"
```

### Task 2: Upstream Sync Workflow

**Files:**
- Create: `.github/workflows/sync-codex-policy.yml`

**Interfaces:**
- Consumes: `obra/superpowers:main`, the fork's `main`, and `scripts/apply-codex-policy.py`.
- Produces: an updated fork `main` and generated `my-codex-policy` branch.
- Triggers: daily cron and `workflow_dispatch`.
- Permissions: repository contents write only.

- [ ] **Step 1: Add the workflow with an explicit fork guard**

Use this job shape:

```yaml
name: Sync Codex policy branch

on:
  schedule:
    - cron: "17 3 * * *"
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: sync-codex-policy
  cancel-in-progress: true

jobs:
  sync:
    if: github.repository == 'AtsushiMiura/superpowers'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: main
          fetch-depth: 0
      - name: Configure Git
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
      - name: Test policy generator
        run: python3 -m unittest discover -s tests/codex-policy -p 'test_*.py' -v
      - name: Sync upstream main
        run: |
          git remote add upstream https://github.com/obra/superpowers.git
          git fetch upstream main
          git merge --no-edit upstream/main
          git push origin HEAD:main
      - name: Generate policy branch
        run: |
          git switch -C my-codex-policy main
          python3 scripts/apply-codex-policy.py
          python3 scripts/apply-codex-policy.py --check
          git add skills
      - name: Publish policy branch when its tree changed
        run: |
          generated_tree="$(git write-tree)"
          git fetch origin my-codex-policy:refs/remotes/origin/my-codex-policy || true
          published_tree="$(git rev-parse origin/my-codex-policy^{tree} 2>/dev/null || true)"
          if [ "$generated_tree" = "$published_tree" ]; then
            echo "Policy branch is already current."
            exit 0
          fi
          upstream_short="$(git rev-parse --short main)"
          git commit -m "chore: generate Codex policy for ${upstream_short}"
          git push --force-with-lease origin HEAD:my-codex-policy
```

Do not add marketplace publishing, notifications, keepalive behavior, cache layers, or third-party Actions.

- [ ] **Step 2: Review the workflow statically**

Run:

```bash
git diff --check
git status --short
```

Confirm every `git push` targets `origin`, the job guard names `AtsushiMiura/superpowers`, and the only upstream URL is used by `git fetch`/merge.

- [ ] **Step 3: Run the policy tests again**

Run:

```bash
python3 -m unittest discover -s tests/codex-policy -p 'test_*.py' -v
```

Expected: all tests PASS.

- [ ] **Step 4: Commit the workflow**

```bash
git add .github/workflows/sync-codex-policy.yml
git commit -m "ci: sync upstream and publish Codex policy branch"
```

### Task 3: Fork-Internal Pull Request

**Files:**
- No new files.

**Interfaces:**
- Consumes: completed `feat/codex-policy-sync` branch.
- Produces: a pull request whose repository and base are explicitly the user's fork.

- [ ] **Step 1: Run final local verification**

```bash
python3 -m unittest discover -s tests/codex-policy -p 'test_*.py' -v
git diff --check origin/main...HEAD
git status --short --branch
```

Expected: tests PASS, no whitespace errors, and a clean feature branch.

- [ ] **Step 2: Push only to the fork**

```bash
git push -u origin feat/codex-policy-sync
```

- [ ] **Step 3: Create a fork-internal PR with explicit repository coordinates**

```bash
gh pr create \
  --repo AtsushiMiura/superpowers \
  --base main \
  --head AtsushiMiura:feat/codex-policy-sync \
  --title "Add generated Codex invocation policy branch" \
  --body-file PR_BODY.md
```

The PR body must summarize the two-skill allowlist, daily/manual synchronization, generated `my-codex-policy` branch, local test result, and the fact that no upstream repository changes are requested. Create `PR_BODY.md` in a temporary directory rather than committing it.

- [ ] **Step 4: Stop for PR review**

Do not merge automatically. After review and merge inside `AtsushiMiura/superpowers`, manually run `Sync Codex policy branch` once and verify the generated branch before importing it into Codex Marketplace.
