# AGENTS.md

Guide for everyone working in this repository, people and coding agents alike.

Group 3's solution to Hackathon VX, Challenge 01: sanitize a materials master base, standardize new registrations, and enrich missing data with a recorded source. Deliverables: working MVP, market analysis and a five-minute pitch.

## Where things are

| Path | Contents | Status |
|---|---|---|
| `front/` | Next.js static export with mock data ([details](front/README.md)) | Prototype |
| `back/domain/` | Shared rules and contracts, used by batch and MCP | In progress |
| `back/repositories/` | Swappable algorithms and batch persistence | In progress |
| `back/pipelines/`, `matching/`, `enrichment/`, `clients/` | Batch stages and external clients | Classification report and storage implemented; other stages are placeholders |
| `back/cli.py` | Batch command line, installed as `vx-back` | In progress |
| `mcp/vx_materials_mcp/` | MCP server, tools and chatbot, installed as `vx-agent` | Rule-based chat with search/PDM and a shared NCM consistency tool |
| `api/vx_materials_api/` | API, security, services and database, installed as `vx-api` | Chat, BFF sessions, RBAC, approval queue, transactional audit and scoped dashboard metrics |
| `api/contracts/` | OpenAPI source and validated examples ([details](api/contracts/README.md)) | Integration contract |
| `scripts/` | AWS preflight/ECS/EC2 tooling, demo data, policy check and HTTP smoke test | AWS/EC2 tooling tested offline; demo reset implemented |
| `deployment/` | Explicit AWS configuration and deployment runbook | Local preparation; account validation still required |
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

**Required for people and agents before opening any PR for review:** run all three
pytest suites locally and fix failures first. From the repo root:

```bash
(cd back && uv run --locked pytest)
(cd mcp && uv run --locked pytest)
(cd api && uv run --locked pytest)
```

Run focused tests while developing, then the complete suites before the PR.
Run pytest separately per module: a root invocation collects colliding test filenames.
For changes to operational Python scripts, also run
`uv run --locked --package vx-materials-back pytest scripts/tests` from the root.

Record the exact commands, pass/fail results and skipped tests in the PR description.
Changes to persistence, migrations or search also require the PostgreSQL-backed API
and MCP suites with `TEST_DATABASE_URL`, as described below. Skips do not validate
database behavior. If a required check cannot run, report the blocker before opening
the PR for review. Use the PR to review locally validated work, not to discover whether
the tests pass.

Database, from the repo root. The first command starts Postgres on port 5432, and the rest run from `api/`. Tests recreate the `_test` database, and they're skipped without this variable. Roles and passwords are global to the server, so tests never change `api_user`, `batch_user` or `mcp_reader`: they log in through `temporary_login`, a disposable member role dropped at the end. Give each concurrent run its own `_test` database name:

```bash
docker compose up -d --wait db
```

```bash
TEST_DATABASE_URL=postgresql+psycopg://migration_user:local_only_migration@127.0.0.1:5432/vx_materials_test uv run pytest
```

```bash
MIGRATION_DATABASE_URL=postgresql+psycopg://migration_user:local_only_migration@127.0.0.1:5432/vx_materiais uv run vx-db upgrade
```

Load the data kit, from `api/`, with `DATABASE_URL` set to the `api_user` connection. Repeating it duplicates nothing, and `docker compose up` already runs it:

```bash
uv run vx-bootstrap --data-dir ../data/desafio01
```

Schema changes need a new migration in `api/vx_materials_api/db/migrations/versions/`. Tests fail if models and migrations differ.

Reset the demo state before each rehearsal, from the repo root with the stack up. It wipes approvals, audit, chat and orders, reloads the kit and rebuilds proposals, always to the same state. It refuses to run without `DEMO_MODE=true` ([details](docs/demo.md)):

```bash
DEMO_MODE=true scripts/load_demo_data.sh
```

Propose merges and corrections without writing anything, from `back/`:

```bash
uv run vx-back sanitize-report ../data/desafio01/01_base_materiais.csv --pdm-workbook ../data/desafio01/03_padrao_cadastro_PDM.xlsx
```

Rebuild the search index and write proposals to the local database, from the repo root, after `docker compose up`. `docker compose up` already builds the index chat search needs; this also writes proposals. Keep `--build`, since the batch image sits behind a profile and `up --build` doesn't rebuild it:

```bash
docker compose run --rm --build batch
```

Import the kit's 520 registration orders, from the repo root, after the index exists. Repeating it duplicates nothing ([details](docs/pedidos.md)):

```bash
docker compose run --rm bootstrap vx-import-orders
```

Measure attribute extraction on the whole base, from `back/`:

```bash
uv run python -m pipelines.measure_extraction
```

Report, from `back/`:

```bash
uv run python cli.py normalization-report ../data/desafio01/01_base_materiais.csv
```

Classification, from `back/` (details and evaluation limits in
[`docs/classificacao.md`](docs/classificacao.md)):

```bash
uv run vx-back classification-report ../data/desafio01/01_base_materiais.csv --input-kind materials --pdm-workbook ../data/desafio01/03_padrao_cadastro_PDM.xlsx
```

```bash
uv run vx-back classification-evaluate tests/fixtures/classification_review.json --pdm-workbook ../data/desafio01/03_padrao_cadastro_PDM.xlsx
```

Select the algorithm with `CLASSIFICATION_REPOSITORY` or `--repository`; the default, `aliases_v1`, expands unambiguous technical aliases like `VALV ESF` first. Every input
record gets a result with its original values and evidence; reports do not change
the master data. An `OUT_OF_SCOPE` classification can be a false negative and must
not automatically reject an order.

Front, from `front/` (Node 20.9+):

```bash
npm ci
```

```bash
npm run typecheck
```

After changing an API contract, regenerate front types and validate them (from `front/`):

```bash
npm run api:generate
npm run api:check
npm test
```

`api:check`, front tests and API contract tests run in CI. Contract files describe the
integration target; an endpoint is available only after its implementation issue is delivered.

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

`up` runs the one-shot `index` service before the Agent starts: it rebuilds the search
index when the rules changed and skips in seconds otherwise, so a clean clone needs no
AWS account and no extra step for chat search. The integration smoke exercises the
static front and a real MCP chat turn:

```bash
scripts/smoke_test.sh http://localhost:8000 --mode local
```

The full local flow (#47) loads the demo state, then goes through the three local
accounts over HTTP: chat with similar-material search to a ready card, `/materiais`
with scoped stock, a batch job started by Governança, imported orders, a technical
approval applied, a merge that needs Governança and then Fiscal, the three decisions
in the audit, and an after snapshot on the dashboard. It changes the database, so
reset the demo again before a rehearsal:

```bash
DEMO_MODE=true scripts/load_demo_data.sh
```

```bash
scripts/smoke_test.sh http://localhost:8000 --mode flow
```

Nothing in this flow calls Bedrock: chat plans with rules, the batch reports zero
model usage and says so, and embeddings stay off. The only model-backed option,
embeddings, has `simulated_v1`, labeled as simulated and refused outside `APP_ENV=local`.

CI runs the same flow in an isolated Compose project, with cached images that
include the original data kit. `DB_PORT` and `API_BIND_PORT` choose local ports;
published ports bind to loopback. CI also checks branch/commit policy and runs the
installed migration command twice. A newer push to the same PR or to `main` cancels
the older CI run, so the CI workflow must never deploy or migrate anything outside the
runner; real deploys keep their own S3 lock. Operational limits, authenticated smoke usage
and required GitHub admin settings are in [`docs/devops.md`](docs/devops.md).

AWS preparation runs offline without credentials by default:

```bash
scripts/preflight_aws.sh --config deployment/aws.example.json --offline
scripts/deploy_ecs.sh --config deployment/aws.example.json
scripts/deploy_ec2.sh --config deployment/aws.example.json --host 203.0.113.10.nip.io
```

Use `--apply` only with a real workshop configuration. Bootstrap reuses approved
IAM/network/RDS resources; it does not assume permission to create them. The exact
sequence, secret formats, HTTPS/Cognito stages and lock recovery are in
[`deployment/README.md`](deployment/README.md). ECS batch is selectable through
`BATCH_RUNNER=ecs_fargate`, with a fixed task-definition ARN and no API credentials
in task overrides. AWS validation remains part of #6.

The EC2 command renders Compose/Caddy offline by default. Its `--apply` mode runs
on an existing EC2 with an instance profile, fetches per-service secrets and enables
public HTTPS. It keeps API/Agent ports private and does not enable the development
batch subprocess in production. Administrative batch execution and login validation
limits are documented in [`docs/ec2.md`](docs/ec2.md); live validation remains #29.

## Workflow

Each piece of work follows the same path:

1. **Issue:** claim the issue, as described in [Claiming an issue](#claiming-an-issue). If none exists for the work, create one and assign it first. Nothing else starts before this.
2. **Branch:** create a branch for it from an up-to-date `homologacao`, the default branch.
3. **Develop:** work [local first](#local-first) and make atomic commits. Run the local checks.
4. **PR:** [update and rebase on `homologacao`](#before-opening-a-pr), then open a pull request targeting `homologacao`, closing the issue. These PRs run no CI: the local checks are the gate, recorded in the PR.
5. **Merge:** rebase-merge into `homologacao`, then complete [the branch cleanup](#after-merging).
6. **Promote:** when `homologacao` is ready for production, follow [Promoting to main](#promoting-to-main). Only that PR runs the full CI.

`main` is production and keeps its protection: PR only, the eight CI checks with an up-to-date base, linear history and rebase merges. Nobody opens work PRs against `main`.

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

### Before opening a PR

**Required for people and agents. Never open a PR from a branch that isn't rebased on the latest `homologacao`.** Others merge all the time, so this finds conflicts on your branch instead of on `homologacao`.

1. Commit your work, because a rebase needs a clean tree. Then pull `homologacao` and rebase your branch on it, in one command that also works in worktrees:

   ```bash
   git pull --rebase origin homologacao
   ```

2. Resolve conflicts by keeping both sides' intent. If you can't tell what the other change meant, run `git rebase --abort` and ask its author. For lockfiles, follow [Code style and avoiding conflicts](#code-style-and-avoiding-conflicts).
3. Run all three local pytest suites and the other checks listed under [Commands](#commands) again, because the combined code hasn't been tested yet. Include their commands, results and skips in the PR description.
4. Push. After a rebase, use `git push --force-with-lease`, on your own branch only.
5. Create the PR with `--base homologacao`.

Never merge `homologacao` or `main` into your branch, and never skip these steps to save time.

### Before merging

The author must:

1. Run style and the local checks for each area touched, listed under [Commands](#commands). Docker changes are checked by CI's image builds.
2. Confirm every acceptance criterion of the issue is met.
3. Repeat [the rebase and checks](#before-opening-a-pr) if `homologacao` moved after the PR opened.

Authors may merge their own PRs, and reviews are welcome when a change is risky. Merge with rebase, to keep atomic commits on a linear history:

```bash
gh pr merge <n> --rebase
```

Never force-push `main` or a branch someone else is using.

### Promoting to main

`main` receives only promotions of `homologacao`, opened from the same repository. This is the only PR that runs the full CI and the repository policy.

1. Freeze `homologacao`: ask the team not to merge into it until the promotion lands.
2. Run the local checks on `homologacao` itself, including the database-backed suites, and `scripts/smoke_test.sh --mode flow` against a fresh `docker compose up --build`.
3. Open the PR: `gh pr create --base main --head homologacao`, listing the issues it delivers.
4. When the eight checks are green and the base is current, rebase-merge it. `homologacao` is protected from deletion, so it stays.
5. Synchronize: the promoted commits get new hashes on `main`, so an administrator rebases `homologacao` onto `main` and force-pushes it. Commits already promoted drop out and later work is kept:

   ```bash
   git fetch origin && git switch homologacao && git reset --hard origin/homologacao
   git rebase origin/main
   git push --force-with-lease=homologacao:<previous-homologacao-sha> origin homologacao
   ```

6. Unfreeze `homologacao` and tell the team to rebase open work branches on it.

### After merging

**Required for people and agents. Branch cleanup is part of completing the work.**

1. Confirm the PR is `MERGED` into its intended base. A closed PR alone is not proof of integration.
2. Run `git fetch origin --prune` and check each remaining issue branch individually. Its current tip must match the merged PR head, with no later work to preserve. Keep `main`, `homologacao`, and branches serving as the head or base of an open PR.
3. If the remote branch still exists, delete only the verified tip, so a concurrent push cancels the deletion:

   ```bash
   git push --force-with-lease=refs/heads/<branch>:<verified-sha> origin :refs/heads/<branch>
   ```

4. Check `git worktree list` before local cleanup. From a clean checkout on another branch, delete the completed local branch with `git branch -d <branch>`. After a rebase or squash merge, Git may not recognize it as merged: use `-D` only after verifying that all changes are integrated and no local work remains. Preserve branches checked out in another worktree and report the pending cleanup.
5. Run `git fetch origin --prune` again and verify the remote branch and any removable local copy are gone. Report which branches were deleted and why any were kept; cleanup is complete only after this check or an explicit explanation of what remains blocked.

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
- Same item requires the shared decision in `back/domain/identity_decision.py`: same class, noun/qualifier and applicable required attributes; or genuine manufacturer/part reference without contradictory evidence. Equal keys alone never override conflicts. See [`docs/identidade-materiais.md`](docs/identidade-materiais.md) and the glossary in [`CONTEXT.md`](CONTEXT.md).
- Batch, MCP search and transactional approval use that decision. Missing or conflicting identity evidence remains for review, including unconfirmed revisions and reference suffixes. Chat/API search signatures include the item noun; changing it requires a new search.
- Equivalent products from different manufacturers stay separate. Record the equivalence instead of merging.
- `ranking_score` only orders results. It never authorizes a merge.
- Packaging units without a known factor block automatic quantity consolidation.
- Original stock balances are immutable, and total value must be conserved.
- Approved consolidation links original snapshots to their principal, with explicit
  conversion factors and sources. MCP inventory views follow these links.
- NCM changes require fiscal approval.
- Keep the original value and the applied rule on every transformation. Every enriched value records its source.

**Security**

- BFF model: tokens stay on the backend, and the browser only holds an opaque, `HttpOnly` session cookie.
- The API derives identity and roles from the session. Payloads never carry `role`, `actor_id` or `approved_by`, and the front sends no role header.
- Guards check both action and resource. The front hides controls, but the API is the authority.
- Use `security/rbac.py` for action, tenant, center and conversation-owner checks.
  Permissions must belong to both the authenticated identity and its role's matrix.
  Chat cookie writes require Origin and CSRF before reserving a turn or calling the Agent.
- Never commit secrets. Tokens, passwords and secrets never appear in logs.
- Test sessions exist only in local environments.
- Persona switching (`DEMO_MODE`) only moves between real Cognito sessions already signed in on the same browser, for accounts listed in `DEMO_ACCOUNTS` whose token has the persona's role. Choosing a persona never grants a role.
- MCP inventory and the materials API select only the latest dataset per tenant, ordered by `imported_at DESC, id DESC`; historical observations never add to current stock. Approved conversions still follow the original snapshots within that selected dataset.
- Stock price and value are for `metrics:financial` only. MCP tools get the inventory view from `inventory_view(caller)` and never name it directly. The database can't enforce this per user, because MCP has one credential.

## Database on AWS

RDS needs setup that local Postgres doesn't, because `vx-db upgrade` creates roles and the `vector` extension. Run this once as the RDS master user, using a password from Secrets Manager:

```sql
CREATE ROLE migration_user LOGIN CREATEROLE PASSWORD '<from-secrets-manager>';
GRANT rds_superuser TO migration_user;
CREATE DATABASE vx_materiais OWNER migration_user;
```

Then run `vx-db upgrade` followed by `vx-db set-passwords`, with `MIGRATION_DATABASE_URL`, `API_DB_PASSWORD`, `BATCH_DB_PASSWORD` and `MCP_DB_PASSWORD` set. These steps haven't been run on RDS yet, so [#6](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/issues/6) must confirm them and correct this section if needed.

## NCM consistency

`back/domain/ncm_rules.py` and the MCP tool `check_ncm_consistency` evaluate syntax
and PDM coherence without writing materials or approving changes. Without the
official snapshot (#30), existence and validity are unknown, never inferred from
the PDM. Evaluation hashes bind inputs and reference versions. The batch proposes
`NCM_CORRECTION` only with a confirmed class, complete PDM and one resolved code;
the approval payload pins the before/after assessments. The API recomputes the
assessment before each approval, refuses changed fiscal bases and enforces all
required technical/fiscal reviews. See `docs/ncm.md` for behavior and verification.

## Chat order submission

A ready chat card creates no order until the user explicitly submits it through
`POST /api/v1/chat/{session_id}/submit`. The API reads the saved card and center,
checks ownership and version, revalidates the current PDM and duplicate identity,
and creates one order with audit and idempotency in the same transaction.
Persisted history and resumed turns also recheck current center access, including centers
whose inventory appeared in earlier turns; hidden conversations are filtered before pagination.
The original user messages stay separate from the confirmed class, item name and
attributes. Order approvals revalidate that structured card rather than extracting
superseded values from earlier messages. A submitted conversation accepts no new
turns; start a new one for another item. See [`docs/pedidos.md`](docs/pedidos.md).

## Browser session transitions

The frontend serializes login, persona switching and logout. While a transition
is pending, authentication controls are disabled and private screen content is
unmounted. A session revision prevents earlier responses, including stale 401s
and profile refreshes, from changing a newer session. Ambiguous transport failures
are reconciled through `/auth/me`; without a confirmed identity the private UI
stays inaccessible. See [`docs/autenticacao.md`](docs/autenticacao.md).

## Attribute extraction

Extraction prefers leaving a field empty to guessing, because a wrong value can cause a wrong merge. Add an alias to its tables only when it's unambiguous. For example, `INOX 316` doesn't map to `ACO INOX FORJADO A182 F316`, since text alone can't say forged or cast. PSI converts to BAR only when it is a whole bar written the kit's way, rounded to 5 PSI (`145PSI` is `10BAR`). Other PSI values, like `150PSI`, stay empty instead of rounding into another item's pressure. Tests hold real base rows with results checked by hand, so add one with each new rule.

Orders and chat messages arrive as sentences and lines. A value followed by sentence punctuation is read without it (`DIN 933.` is `DIN 933`), while a period followed by a letter or digit stays part of the value (`8.8`, `ASME B18.2.1`, and `DIN 931.1` doesn't match `DIN 931`). A line break, with its bullet, separates items, and so does a period before a new `LABEL:`. A period followed by a space alone doesn't, since `REF. 123` is an abbreviation. Base descriptions have no line breaks or trailing periods, so these rules change orders and chat only.

Reordered words may match a PDM value only when all its words are present; an incomplete value is never completed just because only one PDM option contains it. `FERRO FUNDIDO` does not establish `FERRO FUNDIDO NODULAR`, and `FEMEA BSP` does not establish a straight fitting. Explicit aliases and complete values still work. With shared identity-v3 and sentence/line parsing, #133 uses extraction revision `5`: rebuild the search index through `docker compose up --build` or `docker compose run --rm --build batch` after updating. Development counts, coverage held for review and the unchanged historical labels are recorded in [the extraction measurement](docs/extracao-valores-explicitos.md).

For labels without separators, preserve the remaining attributes after a whole matched prefix. Generic `ZINCADO` stays pending; `ZINCADO BRANCO` supplies the complete finish. Boundary rules, all changed-value evidence, merge reviews and index-only rebuild instructions: [label boundaries](docs/label-boundaries.md).

## Duplicate proposals

The batch only proposes merges, and people approve them through the API. Default candidates come from exact identity: same required attributes or, in reference classes, same manufacturer and reference, as PDM rule 10 says. `tokens_v1` stays registered but off, because in reviewed pairs only 7 of 23 of its decided suggestions were the same item.

Identity rules `identity-v2` also separate manufacturers in technical classes, even when the PDM has no manufacturer attribute. Unknown manufacturers never bridge named manufacturers. Different item names, equipment models used as part numbers, and unconfirmed part revisions cannot produce a merge. Revision markers such as `REV A` are preserved and sent to manual review, rather than stripped as noise.

`sanitize-report` includes `identity_review`: technical equivalence candidates and manual review evidence, separate from applicable proposals. `sanitize` stores this report immutably through the storage client and returns `identity_review_key`. Equivalence is not approval to substitute or consolidate. See [the rules and measured limits](docs/identidade.md).

After changing identity rules, rebuild the search index with `vx-back index`; an old index is refused. Re-evaluate the fixed reviewed cohort, from `back/`, with:

```bash
uv run python -m pipelines.measure_merge_identity ../data/desafio01/01_base_materiais.csv --pdm-workbook ../data/desafio01/03_padrao_cadastro_PDM.xlsx
```

To change the default, measure against `back/tests/fixtures/merge_review.json`. Those pairs were reviewed by reading descriptions during development, so add pairs reviewed by people who know the materials whenever possible.

## Similar material search

`search_similar_materials` combines exact identity and PostgreSQL full-text, then compares attributes. It reads the index the batch builds with `vx-back index`, and refuses an index built with other rules: index and query must share the same version, PDM and algorithms. Changing classification or extraction rules changes that version, so rebuild the index after pulling such a change: `docker compose up --build` does it through the `index` service, which skips when the current version already covers every material (`vx-back index --if-stale`). It only checks version and coverage, so after approvals change material content, `docker compose run --rm --build batch` reindexes everything. Embeddings are optional, set with `EMBEDDING_REPOSITORY`, and stay off by default. On the 202 pairs the base declares identical, a local model (`ollama_nomic_v1`) found 126 in the top 10 against 124 without embeddings, at three times the cost. Titan on AWS is still to be measured. Compare any change with:

```bash
uv run python -m vx_materials_mcp.evaluation --repository hybrid_embeddings_v1 --tenant-id <tenant-uuid>
```

That runs from `mcp/`, needs `DATABASE_URL` and an index built with the same `EMBEDDING_REPOSITORY`. The local model runs with `docker compose --profile embeddings up -d embeddings`.

The index version holds the PDM label and the workbook's SHA-256, each algorithm's name and `revision`, `IDENTITY_RULES_VERSION` and, when set, the embedding model's signature. Bump `revision` when you change a classifier's or extractor's rules or tables, `IDENTITY_RULES_VERSION` when identity rules change, and `INDEX_FORMAT` when the search text or tokens change. After any of these, or a new PDM workbook, search answers "Indice de busca ausente" until you rebuild the index with `docker compose up --build`, `docker compose run --rm --build batch`, or `uv run vx-back index` from `back/` with the `batch_user` connection.

The Agent passes the caller validated from the internal token to the MCP server in `VX_CALLER`, never as a tool parameter. Without it, search returns no stock. Search requires the signed tenant, also bound to `VX_CALLER`; missing or invalid tenants are refused. Every catalog, index, target and inventory read is restricted to that tenant. The token carries the user's tenant, permissions and authorized centers, and stock outside those centers never reaches the chat.

In chat, a complete card is ready to submit only after the search ran, found no item with the same identity, and the requester dismissed every similar item shown. If the search fails, the turn stays `NEEDS_INPUT`, because merging different items costs more than waiting. Existence is decided before the display limit, and verified reusable identities are shown before non-reusable candidates. A verified match shows the active code instead: a blocked item points to its active target, and an obsolete one is never offered.

Similar items without verified identity are listed for the requester to pick one or answer "Nenhum desses é o meu item". The front buttons send a structured `action` (`PICK_CANDIDATE` or `DISMISS_CANDIDATES`), so their label can change freely; typed replies are still read deterministically as a fallback. A dismissal covers only the codes shown: new candidates are asked about again. The API accepts a dismissal or a pick only for codes it stored as offered in an earlier turn of the same session, and answers 422 otherwise.

The API saves the last accepted duplicate check with the card's signature (class and filled attributes). While the card doesn't change, the agent reuses it instead of searching again, so a pick or dismissal holds on later turns. A changed card searches again, and a turn without a search whose card differs from the saved one is never ready to submit. `READY_TO_SUBMIT` registers nothing: submitting and publishing an order belong to the approval flow.

## Correction proposals

The same batch run proposes `PDM_CORRECTION` (description in PDM format, merchandise group of the class) and `UNIT_CORRECTION` (unit spelled as an alias, like `PCA` or `UN` for `PC`), one proposal per type and material. Every change records before, after and rule.

Governança applies an approved merchandise group through the same decision endpoint as merges. The API checks that the group matches the confirmed PDM class, and approves only when the PDM data is complete. It saves the group in `merchandise_group`, and keeps the loaded value in `original_merchandise_group` and in the snapshot. Like any approval, it refuses an NCM outside the class references (`NCM_REFERENCE_MISMATCH`). In the kit, 196 of the 325 group corrections without conflicts can be applied: 113 stop on the NCM and 16 on incomplete PDM data.

Only `ATIVO` materials are corrected, as with merges. Corrections also need a trusted class: classified, and the PDM item name opens the description. A class name found mid-text is usually an attribute of an abbreviated product, such as `PARAFUSO SEXT ... REVESTIMENTO`, so those materials only get a pending reason. The one exception is a unit alias of the same unit, like `PÇ` to `PC`, proposed with the rule `unit.alias_without_class` and never replaced by a class default. Packaging units without a known factor (`CX`, `CT`, `JG`) are never converted. The report counts pending reasons by type. Select the rules with `CORRECTION_REPOSITORY`, default `head_noun_v1`.

The queue never offers what the approval would refuse. Batch, queue and approval share one PDM check (`domain.proposal_validation`): the result must meet the PDM, unit included, and in a merge every member must meet it on its own. A proposal that fails gets a `PDM_INVALIDO` conflict naming the member and the missing or invalid attributes, so it shows its reason and has no approve action. In the kit this marks 206 merges, mostly manufacturer-reference classes where one member lacks a required attribute such as `MODELO EQUIPAMENTO`, and 697 description corrections of materials whose unit is not the class default, such as packaging units.

Each correction also carries `review_lane` in its changeset (`tier`, `lot_key` as type|rule|class, `reasons`), following the decision in #36. Tier 1 is a unit alias with a trusted class and no unit pending reason. Tier 2 is a description or group in PDM format with a trusted class, no pending reason and no text loss. Everything else is tier 3, including any proposal with a conflict such as `PDM_INVALIDO`, reviewed item by item, with `UNTRUSTED_CLASS`, `CONFLICT` or `TEXT_LOSS`. Tiers only say how a person reviews: nothing is applied without approval, and the API builds lots of 20 or more. `TEXT_LOSS` means a meaningful term of the original that the extraction left unresolved is missing from the proposed description, such as `TAMPA MOLA` becoming `TAMPA` or `ACO ESPECIAL` disappearing. Spelling the extraction converts, labels, the manufacturer field and the noise phrases the extraction drops (`REV A`, `VER DESENHO`) don't count. Select the rule with `TEXT_LOSS_REPOSITORY`, default `unresolved_terms_v1`. Merges never get a lane.

Each proposal carries only the pending reasons of its own type as conflicts: an incomplete description doesn't block a unit spelling fix, and a packaging unit without factor doesn't block a description fix. Unknown reasons block every type. An approved `UNIT_CORRECTION` changes only the unit of one active material, and only when the new unit is the normalized spelling of its current unit, so it needs no class or complete PDM and never touches identity, description, NCM or quantities; anything else is `UNIT_NOT_ALIAS`. Approval compares NCM with the class references in normalized form, so `84314390` matches `8431.43.90`.

## Lot approval

Nothing reaches the master data without a person approving it; form corrections are approved in lots after a sample review (#36). The batch writes `review_lane` (`tier`, `lot_key`, `reasons`) in each correction's changeset (#119). A lot is the `PENDING` corrections with the same `lot_key` and tier 1 or 2, technical review pending, no fiscal review, and at least 20 items. Proposals without `review_lane` or with tier 3 never enter a lot, and `MERGE` and NCM never do.

Opening a lot review (`/saneamento/lotes/`) freezes its proposals and versions and draws the sample on the server: 10 items for tier 1 and 20 for tier 2, stored in `lot_reviews` and the same on every read. Governança must mark every sample item. Zero errors applies each proposal through the normal decision service, each in its own savepoint and with its own audit event pointing to the lot review and sample. Items that changed, were decided apart or no longer pass the PDM are reported as `STALE` or `SKIPPED` and don't block the rest. Any wrong item applies nothing, records the rule, and sends the whole lot back to individual review.

## Full-base runs

`vx-back sanitize --job-id <id>` runs a job the API created, and resumes from its checkpoint if it stopped. Analysis is saved in chunks of 1,000 materials under `runs/<job_id>/analysis/` in storage, and proposals are saved in batches of 500 in the same transaction as the checkpoint, so a rerun skips finished work and never duplicates a proposal. The job and every analysis chunk record the rules signature, the same PDM hash and revisions the search index uses. Resuming after any of them changed fails the job with the reason and leaves its chunks as they are: create a new job instead. Without `--job-id` the run is in memory, with nothing to resume. Locally, `APP_ENV=local uv run vx-batch-job` (from `api/`, with the `api_user` connection) also creates a job without the screen.

Batch requests must include all three statuses (`ATIVO`, `BLOQUEADO`, `OBSOLETO`); subsets and empty status lists receive `422 SCOPE_NOT_SUPPORTED` before any job, manifest or task is created. Resume preserves the full-base scope. Governança starts jobs on `/batch` (`POST /api/v1/batch/jobs`); locally, sign in with the `GESTOR_CADASTRO` account. The API writes a manifest to `runs/<job_id>/manifest.json`, with no user token, and launches the task through `BATCH_RUNNER`: `local_process` runs `vx-back sanitize` as a subprocess with the `batch_user` connection from `BATCH_DATABASE_URL`, only with `APP_ENV=local`. An ECS RunTask runner joins it for AWS (#6). Each run claims the job with its own worker id in `checkpoint.lease`, and every write requires that lease and status `RUNNING`, so a second worker is refused while the first has a fresh heartbeat. The worker beats every 15 s between checkpoints. A job without a heartbeat for `BATCH_HEARTBEAT_TIMEOUT_SECONDS` (default 120) becomes `FAILED` with `WORKER_TIMEOUT`, or `WORKER_NOT_STARTED` if the task never started, and the old worker stops on its next write. `POST /api/v1/batch/jobs/{id}/resume` puts a failed job back in the queue and the task continues from its checkpoint.

A finished job stores its metrics in `batch_jobs.counts` and `runs/<job_id>/metrics.json`: the contract counts (`proposals`, `merges`, `ncm`, `enrichment`), counts by type, one outcome per material (`PROPOSTA`, `PENDENTE`, `SEM_ALTERACAO` or `ERRO_ANALISE`, always summing to the base), time per stage and attempt, and model usage. The batch doesn't call models yet, so usage is zero and says so.

A proposal's id comes from its content, so a rerun with the same content inserts nothing. When rules change, the new proposal for the same dataset, type and members replaces the earlier `PENDING` one: in the same transaction, the batch calls `supersede_proposals`, which marks it `STALE` with a `SYSTEM` audit event (`PROPOSAL_SUPERSEDED`, pointing to its replacement). `APPLIED` and `REJECTED` proposals never change. `batch_user` still has no access to `audit_logs`: the function runs with the migration owner's rights and does only this.

The audit list includes authorized order submissions/decisions/publications and `SYSTEM` proposal supersessions. It checks the resource tenant and centers before collecting a page. System events have `actor_type=SYSTEM`, actor `Sistema` and no effective human role; the replacement is recorded in `after.superseded_by`. Only Fiscal receives financial snapshot fields. Existing events are projected without inserting duplicate audit records.

Sanitization evaluation uses frozen development cohorts packaged in
`back/pipelines/evaluation_data/`. Never replace old labels or cohorts when
candidates change: report changed/withdrawn groups and add a new version with
review authors and evidence. Unknown labels and conflicting reviews stay
inconclusive. The report distinguishes pair/group precision, coverage, abstention
and recovery of known positives; none authorizes a merge. See
[`docs/avaliacao-saneamento.md`](docs/avaliacao-saneamento.md).

From the repo root, without a database or AWS:

```bash
uv run vx-back sanitization-evaluate data/desafio01/01_base_materiais.csv --pdm-workbook data/desafio01/03_padrao_cadastro_PDM.xlsx
```

The dashboard must not publish development precision as an independent product
metric. Technical corpus labels cover only the explicitly reviewed fields;
PDM-valid values are not necessarily correct values for a product.
For a frozen preparation packet with original records and blank review forms,
use `vx-back review-handoff` as described in [revisao-independente.md](docs/revisao-independente.md).
Independent technical review and dashboard/pitch acceptance remain separate human decisions.

## Local first

Authentication defaults to server sessions in the frontend. Compose enables the
three local test accounts; use `AUTH_BACKEND=cognito` with both local-session flags
disabled to connect Cognito without code changes. See [`docs/autenticacao.md`](docs/autenticacao.md).
The local chat also requires login now: no anonymous test identity is injected.
The standard smoke test in local mode creates and revokes an opaque test session.
It also checks the three forbidden approval actions with authenticated local accounts.
Local HTTP cookies are HttpOnly and SameSite=Lax; Cognito cookies are also Secure.
Never enable local sessions in a deployed environment; runtime guards refuse AWS markers.
For the persisted approval queue and producer contract, see [`docs/aprovacoes.md`](docs/aprovacoes.md).
Local Python copies with numbered suffixes (such as ` 2.py`) are excluded from images so duplicate
migration revisions cannot enter a build; these untracked files are not project inputs.

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
- The local test session is the Solicitante persona, enabled with `LOCAL_TEST_SESSION=true`. The API refuses to start with it unless `APP_ENV=local`, and `docker compose` turns it on. Real login (#7) replaces it.
- Agent concurrency is bounded by `AGENT_MAX_CONCURRENT_TURNS` (default 2 per worker).
  Excess turns receive 503 `AGENT_BUSY` before starting MCP. A slot stays reserved
  through cancellation cleanup. `vx-agent` runs one worker; replicas multiply the
  total capacity. Compose defaults to 1 CPU, 512 MiB and 64 PIDs, configured through
  `AGENT_CPUS`, `AGENT_MEMORY_LIMIT` and `AGENT_PIDS_LIMIT`. Keep init enabled and
  at least 15 seconds of shutdown grace.
  Measurement command, results and cancellation behavior: [`docs/agent-concurrency.md`](docs/agent-concurrency.md).
- API and Agent share `AGENT_INTERNAL_TOKEN_SECRET`. The API signs a 60-second token per chat turn, and the Agent rejects anything else.
- Cognito and Bedrock have no faithful local version, so test them on real AWS before their milestones close.

## Swappable algorithms

Any algorithm whose results may disappoint, such as preprocessing, extraction, classification or matching, goes behind a repository. To try another approach, add a new repository and select it, without removing the first one.

1. Define the protocol in `back/domain/contracts.py`.
2. Implement it in `back/repositories/<topic>/<name>.py`.
3. Register it in `REPOSITORIES`, selectable through an environment variable.
4. Parametrize contract tests over every registered repository, so new ones meet the same bar.

`back/repositories/normalization/` and `back/repositories/extraction/` are reference examples. Deterministic parsing with one correct answer, like the PDM loader, doesn't need this.

## Dashboard

`GET /api/v1/dashboard/metrics` reads the original inventory snapshots and the
persisted proposal funnel, scoped by tenant, dataset and authorized centers.
Quality requires `metrics:quality`; executive values require `metrics:financial`.
The quality view never returns financial values. Missing evaluations, savings or
approved after snapshots stay unavailable; applying proposals does not imply
savings or an independent accuracy measurement. See [`docs/dashboard.md`](docs/dashboard.md).

## Frontend

Navigation badges must never use mock counts in API mode. Without a reliable,
authorized total, omit the badge rather than showing zero or the first page size.
Mock-mode badges identify their counts as simulated.

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
- `vx-bootstrap` loads values exactly as they came, and copies the original files to storage. Corrections only happen later, through approved proposals.
- Files go through `clients/storage.py`, using a local folder by default and S3 with `STORAGE_BACKEND=s3`. Stored files are immutable, including concurrent writes: local files are published complete with an atomic hard link; S3 creates with `If-None-Match: *`. Repeating the same content reuses the winner and its version; different content raises a conflict.
- Data stays in the repo so anyone, judges included, can run the project from a clone. Review this once the database exists.
- Data is synthetic, except that the last 15 base records are real products. Those are the only ones to enrich from public sources, and each value must record its source.

## Keeping this file current

When a PR changes a workflow, command, structure or rule described here, update this file in the same PR. Claude-specific notes go in `CLAUDE.md`, everything else here.
