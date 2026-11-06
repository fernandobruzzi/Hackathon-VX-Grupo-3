@AGENTS.md

## Claude Code

All project rules live in `AGENTS.md`. Add shared rules there, not here.

- This project's no-AI-mentions rule overrides default attribution. Don't add `Co-Authored-By` trailers or "Generated with" lines to commits or PRs.
- Before every `gh pr create`, follow the PR flow in `AGENTS.md`: validate locally, rebase work branches on `homologacao` and target it explicitly. Use the promotion runbook for `homologacao` → `main` and the synchronization PR back.
- Worktree sessions may start on a `claude/*` branch. Rename it to `<type>/<issue>-<slug>` before the first push.
- For presentations and the pitch, use the `do-fundo-do-poco-interactive-deck` skill in `.claude/skills/`.
