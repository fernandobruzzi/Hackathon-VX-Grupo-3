# AGENTS.md

Guide for everyone working in this repository, people and coding agents alike.

Group 3's solution to Hackathon VX, Challenge 01: sanitize a materials master base, standardize new registrations, and enrich missing data with a recorded source. Deliverables: working MVP, market analysis and a five-minute pitch.

## Where things are

| Path | Contents | Status |
|---|---|---|
| `front/` | Next.js static export with mock data ([details](front/README.md)) | Prototype |
| `back/domain/` | Shared rules and contracts, used by batch and MCP | In progress |
| `back/repositories/` | Swappable algorithms and batch persistence | In progress |
| `back/pipelines/`, `matching/`, `enrichment/`, `clients/` | Batch stages and external clients | Placeholders |
| `back/cli.py` | Batch command line, installed as `vx-back` | In progress |
| `mcp/vx_materials_mcp/` | MCP server, tools and chatbot, installed as `vx-agent` | Health check and placeholders |
| `api/vx_materials_api/` | API, security, services and database, installed as `vx-api` | Health check and placeholders |
| `api/contracts/` | OpenAPI and fixtures | Empty contract |
| `scripts/` | Deploy, demo data and smoke test | Placeholders, except `smoke_test.sh` |
| `front/pitch/` | Market analysis, ROI assumptions and script | Placeholders |
| `design/` | Presentation template and design system, source for brand values | Reference |
| `Dockerfile`, `docker-compose.yml`, `.env.example` | Images `api`, `agent`, `batch`, and local setup | Ready for integration |
| `data/` | Challenge data kit ([details](data/README.md)) | Read-only input |
| `docs/arquitetura.md` | Full architecture and JSON contracts | Reference |
| `docs/brainstorm.md` | Product reasoning | Reference |

Placeholder modules hold only a docstring naming their issue. Replace them as you take that issue, and don't add stubs that pretend to work.

Read the relevant section of [`docs/arquitetura.md`](docs/arquitetura.md) before working on an area. When code and that document disagree, the note at its top lists known differences. Otherwise raise it on the issue instead of guessing.

## Commands

Setup, once from the repo root (Python 3.12, [uv](https://docs.astral.sh/uv/)):

```bash
uv sync --all-packages
```

```bash
uv run pre-commit install
```

Style, from the repo root:

```bash
uv run ruff check --fix .
```

```bash
uv run ruff format .
```

Tests, from `back/`, `mcp/` or `api/`:

```bash
uv run pytest
```

Report, from `back/`:

```bash
uv run python cli.py normalization-report ../data/desafio01/01_base_materiais.csv
```

Front, from `front/` (Node 20.9+):

```bash
npm ci
```

```bash
npm run typecheck
```

```bash
npm run build
```

```bash
npm run format
```

```bash
npm run dev
```

Everything together, from the repo root (needs Docker):

```bash
docker compose up --build
```

```bash
scripts/smoke_test.sh
```

## Workflow

Each piece of work follows the same path:

1. **Issue:** claim the issue, as described in [Claiming an issue](#claiming-an-issue). If none exists for the work, create one and assign it first. Nothing else starts before this.
2. **Branch:** create a branch for it from an up-to-date `main`.
3. **Develop:** work [local first](#local-first) and make atomic commits. Run the local checks.
4. **PR:** open a pull request to `main`, closing the issue.
5. **Merge:** rebase-merge once checks pass, and delete the branch.

## Issues and milestones

The team plans in advance on [GitHub](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/issues), so anyone can see where to help.

### Picking work

- Anyone can work on any area.
- Choose the highest-priority unassigned issue whose "Bloqueado por" list is finished.

### Claiming an issue

**Required for people and agents.** Claim the issue before creating a branch, editing files or writing a plan for it. This keeps two people from doing the same work. Agents assign the person they are working for, which is the authenticated `gh` user. Assigning is part of starting, so don't wait for separate permission.

1. Check who has it:

   ```bash
   gh issue view <n> --json state,assignees --jq '{state, assignees: [.assignees[].login]}'
   ```

2. If it's closed or assigned to someone else, **stop and tell the person you work for.** Continue only if they confirm the current assignee agreed, and never remove someone's assignment on your own.
3. If it's unassigned or already yours, assign yourself:

   ```bash
   gh issue edit <n> --add-assignee "@me"
   ```

4. Repeat step 1. If anyone else now appears, stop as in step 2: GitHub doesn't lock issues, so two people can claim one at the same moment.

Repeat the check when resuming work on an issue. If you stop working on one, unassign yourself with `--remove-assignee "@me"` and comment on where it stands.

### Creating issues

- New work gets an issue before it starts. Also add issues for work you discover but won't do now.
- Write them in Portuguese with these sections: `## O que construir`, `## Critérios de aceite` (checkboxes), `## Bloqueado por`.
- Describe behavior and how to verify it. Avoid file paths, which go stale.
- Apply one milestone, at least one `area:*` label, one priority and one size.
- If you'll work on it right away, create it with `--assignee "@me"`. Otherwise leave it unassigned, so others can take it.

| Label | Meaning |
|---|---|
| `area:back`, `area:mcp`, `area:api`, `area:front`, `area:pitch` | Where the work happens |
| `P0` | Main demo doesn't work without it |
| `P1` | Strengthens the demo; can shrink if time runs short |
| `P2` | Only if time remains |
| `size:S`, `size:M`, `size:L` | Estimated effort |

### Milestones

Milestones match integration checkpoints, in BRT:

| Milestone | Checkpoint | Goal |
|---|---|---|
| M1: Login e personas | Sat 7 Nov, 11h | HTTPS, Cognito, `/auth/me`, three personas |
| M2: Dados reais | Sat, 13h | Database migrated, data loaded, API reachable from front |
| M3: Chat com MCP real | Sat, 15h | Chat calls a real MCP tool and returns a PDM gap |
| M4: Da proposta à auditoria | Sat, 17h | Batch proposes, Governance approves, audit records |
| M5: Enriquecimento, fiscal e dashboard | Sat, 20h | Real products enriched, fiscal review, dashboard |
| M6: Demo e pitch | Sun 8 Nov, 11h | MVP criteria verified, analysis and pitch ready |

Finish `P0` issues first. If scope changes or an issue is blocked, comment on it so others can see.

## Branches

- Branch from an up-to-date `main`, one branch per issue: `<type>/<issue>-<slug>`.
- `<type>` is a Conventional Commit type. Example: `feat/13-pdm-validator`.
- Never commit directly to `main`.
- Never put an AI agent's name in a branch name. Rename any tool-generated branch, such as `claude/*`, before pushing.

## Commits

- **Atomic:** one logical change per commit, and tests pass at each commit that changes behavior.
- **[Conventional Commits](https://www.conventionalcommits.org/):** `type(scope): subject`, in English and imperative mood.
- **Scopes:** `front`, `back`, `mcp`, `api`, `data`, `design`, `docs`, `ci`.
- **Body:** explain why when it isn't obvious from the subject.
- **No AI mentions:** never cite AI coding agents in commit messages, trailers, branch names, PRs, issues or comments. That means no `Co-Authored-By` for agents and no "Generated with" lines.

```
feat(back): add PDM loader

Compile the PDM workbook into a typed catalog. Map applicability text
through an explicit table and reject unknown or inconsistent content.
```

## Pull requests

- One issue per PR.
- **Title:** same format as a commit, in English.
- **Description:** in Portuguese, covering what changed, how you verified it, and `Closes #<n>`.

**Before merging**, the author must:

1. Run style and the local checks for each area touched, listed under [Commands](#commands). Docker changes are checked by CI's image builds.
2. Confirm every acceptance criterion of the issue is met.
3. Confirm CI is green.
4. Rebase on `main` if it moved: `git fetch origin && git rebase origin/main`, then `git push --force-with-lease` on your own branch only.

Authors may merge their own PRs, and reviews are welcome when a change is risky. Merge with rebase, to keep atomic commits on a linear `main`:

```bash
gh pr merge <n> --rebase --delete-branch
```

Never force-push `main` or a branch someone else is using.

## Code style and avoiding conflicts

Formatting is automatic, so style never causes a conflict. CI rejects unformatted code.

- **Python:** Ruff, configured in the root `pyproject.toml`.
- **Front:** Prettier, which also sorts Tailwind classes.
- **All files:** `.editorconfig` and `.gitattributes` fix UTF-8 and LF line endings.
- **Commit hook:** `pre-commit` formats staged files. Install it once, as shown in [Commands](#commands).

To keep conflicts rare:

- Keep PRs small and rebase on `main` often, at least before you start each day and before merging.
- Check who is assigned to neighbouring issues before touching shared files.
- Add new behavior in new modules, and keep registration lists sorted, one entry per line.
- Never mix reformatting or unrelated renames into a feature PR.

Lockfiles are generated, so never merge them by hand. On conflict, take `main`'s version and regenerate:

```bash
git checkout origin/main -- uv.lock && uv lock
```

```bash
git checkout origin/main -- front/package-lock.json && (cd front && npm install)
```

During a rebase, `origin/main` is still the right source, then continue with `git add` and `git rebase --continue`.

## Language

| Text | Language |
|---|---|
| `AGENTS.md`, `CLAUDE.md`, commits, PR titles, identifiers | English |
| Issues, PR descriptions, READMEs, `docs/`, UI text, code comments | Portuguese |

Domain terms keep their PDM spelling: uppercase, no accents, as in `CLASSE RESISTENCIA`.

## Architecture

The Python modules form one uv workspace with a single `uv.lock` at the root. `mcp` depends on `back` for shared rules. `mcp` and `api` use the namespaces `vx_materials_mcp` and `vx_materials_api`, so nothing collides with the official `mcp` package. Never import from repo-root paths.

```
Browser → API (FastAPI, serves front build) → RDS PostgreSQL + pgvector
              ├─ internal HTTP → Agent (/mcp/chatbot) ─ MCP stdio → MCP server → Bedrock
              └─ ECS RunTask → Batch (/back) → S3, proposals
```

AWS: ECS Fargate Express Mode, RDS, S3, Cognito, Bedrock, Secrets Manager, CloudWatch. Plan B is EC2 with Docker Compose.

**Rules that keep the system correct**

- **One rule engine:** `back/domain` holds identity, normalization, PDM and NCM rules. Batch and chat both import it. The LLM chooses queries and wording, and the domain engine validates data.
- **Proposals, never direct edits:** batch and chat propose changes. Only the API applies them, in one transaction with audit, optimistic version checks and idempotency.
- **Chat doesn't publish:** validating an order in chat never registers a material. The agent has no write credentials on the master base.
- **Contracts first:** OpenAPI in `api/contracts` is the source for front types. Contract changes update the schema and an example in the same PR.

**Domain rules** (PDM general rules and architecture)

- Wrongly merging different items costs more than missing a duplicate. Prefer precision, and send doubt to review.
- Same item means same class, noun and qualifier, and same required attributes; or, in manufacturer-reference classes, same manufacturer and reference.
- Equivalent products from different manufacturers stay separate. Record the equivalence instead of merging.
- `ranking_score` only orders results. It never authorizes a merge.
- Packaging units without a known factor block automatic quantity consolidation.
- Original stock balances are immutable, and total value must be conserved.
- NCM changes require fiscal approval.
- Keep the original value and the applied rule on every transformation. Every enriched value records its source.

**Security**

- BFF model: tokens stay on the backend, and the browser only holds an opaque, `HttpOnly` session cookie.
- The API derives identity and roles from the session. Payloads never carry `role`, `actor_id` or `approved_by`, and the front sends no role header.
- Guards check both action and resource. The front hides controls, but the API is the authority.
- Never commit secrets. Tokens, passwords and secrets never appear in logs.
- Test sessions exist only in local environments.

## Local first

Every feature must run and pass its tests locally with `docker compose up`, without an AWS account. AWS deployment proceeds in parallel, to surface its problems early, but doesn't block local work.

| Need | Local | AWS |
|---|---|---|
| Services | Docker Compose | ECS Express |
| Database | Postgres + pgvector container | RDS, with the same migrations |
| Files | S3-compatible container or local folder | S3 |
| Login | Local test session | Cognito |
| Models | Simulated responses, or real Bedrock when needed | Bedrock |

- What carries over to AWS is the same images, migrations and environment variables. Don't fork code by environment.
- Code reaches external services through small clients selected by environment variable, like [swappable algorithms](#swappable-algorithms).
- Local shortcuts must be impossible to enable in deployed environments: the application refuses to start if they are on there.
- Simulated results are always labeled as simulated.
- Cognito and Bedrock have no faithful local version, so test them on real AWS before their milestones close.

## Swappable algorithms

Any algorithm whose results may disappoint, such as preprocessing, extraction, classification or matching, goes behind a repository. To try another approach, add a new repository and select it, without removing the first one.

1. Define the protocol in `back/domain/contracts.py`.
2. Implement it in `back/repositories/<topic>/<name>.py`.
3. Register it in `REPOSITORIES`, selectable through an environment variable.
4. Parametrize contract tests over every registered repository, so new ones meet the same bar.

`back/repositories/normalization/` is the reference example. Deterministic parsing with one correct answer, like the PDM loader, doesn't need this.

## Frontend

The API serves the static build from the same origin, so there's no SSR, route handlers or middleware, and anything calling the API is a client component. Dynamic routes must keep working in the static export once ids are real.

**Design tokens** live in `front/src/app/globals.css` (identity "Ascensão"), for light and dark through `data-theme`, and are exposed to Tailwind with `@theme inline`. Use tokens instead of raw colors.

| Token | Tailwind | Use |
|---|---|---|
| `--ink`, `--surface`, `--surface-2` | `bg-ink`, `bg-surface`, `bg-surface-2` | Page and card backgrounds |
| `--text`, `--text-muted` | `text-text`, `text-muted` | Text |
| `--verde`, `--verde-glow` | `text-verde`, `text-verde-glow` | Green as text |
| `--esmeralda`, `--on-esmeralda` | `bg-esmeralda`, `text-on-esmeralda` | Shapes and CTA |
| `--profundo`, `--apoio`, `--on-profundo` | `bg-profundo`, `bg-apoio`, `text-on-profundo` | Highlight blocks |
| `--alerta`, `--aviso`, `--info` | `text-alerta`, `text-aviso`, `text-info` | Status |
| `--serie-1` | `bg-serie-1` | Chart series |
| `--focus` | Applied globally | Focus outline |

- Radius: `rounded-sm` (6px), `rounded-md` (12px), `rounded-lg` (24px).
- Fonts: Montserrat for text, IBM Plex Mono for code, both local through `next/font/local`.
- `esmeralda` is for shapes such as arrows, bars and CTAs. Green text is `text-verde`.
- CTA is `bg-esmeralda text-on-esmeralda` in both themes, never white text.
- One `bg-profundo` block per screen for what matters most. Cards have no border or shadow.
- Section labels use `<Eyebrow n="01">`, rendering `01 / RÓTULO` with the emerald bar.
- Reuse `components/ui` before adding a component.

## Data

- `data/desafio01/` is original input. Never edit it.
- Data stays in the repo so anyone, judges included, can run the project from a clone. Review this once the database exists.
- Data is synthetic, except that the last 15 base records are real products. Those are the only ones to enrich from public sources, and each value must record its source.

## Keeping this file current

When a PR changes a workflow, command, structure or rule described here, update this file in the same PR. Claude-specific notes go in `CLAUDE.md`, everything else here.
