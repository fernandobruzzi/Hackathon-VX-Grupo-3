@AGENTS.md

## Claude Code

All project rules live in `AGENTS.md`. Add shared rules there, not here.

- This project's no-AI-mentions rule overrides default attribution. Don't add `Co-Authored-By` trailers or "Generated with" lines to commits or PRs.
- Before every `gh pr create`, complete "Before opening a PR" in `AGENTS.md`. Don't open a PR from a branch that isn't rebased on the latest `main`.
- Worktree sessions may start on a `claude/*` branch. Rename it to `<type>/<issue>-<slug>` before the first push.
- For presentations and the pitch, use the `do-fundo-do-poco-interactive-deck` skill in `.claude/skills/`.
