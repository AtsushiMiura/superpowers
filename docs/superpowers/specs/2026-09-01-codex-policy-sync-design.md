# Codex Policy Sync Design

## Goal

Maintain a public fork of `obra/superpowers` that follows upstream automatically while publishing a Codex Marketplace branch with quiet, predictable skill invocation.

## Branches

- `main`: upstream content plus the small amount of automation maintained by this fork.
- `feat/codex-policy-sync`: initial implementation branch, merged through a pull request inside the fork.
- `my-codex-policy`: generated from `main` and used as the Codex Marketplace source.

`my-codex-policy` is generated output and must not be edited manually.
Future human-authored changes use feature branches and pull requests targeting
`AtsushiMiura/superpowers:main`.

## Invocation Policy

Only these skills allow implicit invocation:

- `systematic-debugging`
- `verification-before-completion`

Every other existing or newly added skill sets:

```yaml
policy:
  allow_implicit_invocation: false
```

The two allowlisted skills set the same value to `true`. Explicit invocation remains available for all skills.

## Components

The fork adds two automation components:

- A policy script that enumerates every `skills/*/SKILL.md`, creates or updates the corresponding `agents/openai.yaml`, and validates the final policy values.
- A GitHub Actions workflow with a daily schedule and manual dispatch.

The upstream source repository does not commit `agents/openai.yaml`; its Codex packaging script seeds that metadata from an official package. This fork therefore creates policy-only sidecars when none exist. If upstream later commits a sidecar, the script preserves its other top-level metadata and changes only `policy.allow_implicit_invocation`.

## Sync Flow

1. Fetch `obra/superpowers` as `upstream`.
2. Merge `upstream/main` into the fork's `main` and push only when it changes.
3. Recreate `my-codex-policy` from the updated `main`.
4. Apply and validate the invocation policy.
5. Commit the generated policy changes and update `my-codex-policy`.

The workflow uses one concurrency group so daily and manual runs cannot update the branches simultaneously.

## Failure Behavior

- Stop before publishing if the upstream merge conflicts.
- Stop if either allowlisted skill is missing.
- Stop if any discovered skill has a missing or incorrect final policy.
- Rely on GitHub Actions logs and normal Git history; do not add audit files, keepalive commits, or custom recovery machinery.

## Upstream Safety

- Treat `obra/superpowers` as fetch-only; its local push URL is disabled.
- Push branches only to `AtsushiMiura/superpowers` (`origin`).
- Create pull requests only inside the fork, with both head and base owned by `AtsushiMiura`.
- Do not create pull requests, issues, comments, or other changes in the upstream repository.
- Automated synchronization pushes only to branches in the fork.

## Verification

The policy script supports a check mode. Local and Actions verification must confirm:

- every directory containing `SKILL.md` has `agents/openai.yaml`;
- the two allowlisted skills are `true`;
- every other skill is `false`;
- a second application produces no additional changes.

## Operational Boundary

Automation covers the GitHub fork, branches, policy generation, and validation. Marketplace import and plugin selection remain a one-time Codex administration step using the `my-codex-policy` branch.
