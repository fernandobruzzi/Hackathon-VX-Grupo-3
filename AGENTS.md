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
| `mcp/vx_materials_mcp/` | MCP server, tools and chatbot, installed as `vx-agent` | Rule-based chat turn over three tools, rest placeholders |
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

Tests, from `back/`, `mcp/` or `api/`:

```bash
uv run pytest
```

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

Rebuild the search index and write proposals to the local database, from the repo root, after `docker compose up`. Search in chat needs this index:

```bash
docker compose run --rm batch
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

The integration smoke exercises the static front and a real MCP chat turn after
building the search index:

```bash
scripts/smoke_test.sh http://localhost:8000 --mode local
```

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
2. **Branch:** create a branch for it from an up-to-date `main`.
3. **Develop:** work [local first](#local-first) and make atomic commits. Run the local checks.
4. **PR:** [update and rebase on `main`](#before-opening-a-pr), then open a pull request, closing the issue.
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

### Before opening a PR

**Required for people and agents. Never open a PR from a branch that isn't rebased on the latest `main`.** Others merge all the time, so this finds conflicts on your branch instead of on `main`.

1. Commit your work, because a rebase needs a clean tree. Then pull `main` and rebase your branch on it, in one command that also works in worktrees:

   ```bash
   git pull --rebase origin main
   ```

2. Resolve conflicts by keeping both sides' intent. If you can't tell what the other change meant, run `git rebase --abort` and ask its author. For lockfiles, follow [Code style and avoiding conflicts](#code-style-and-avoiding-conflicts).
3. Run the local checks again, listed under [Commands](#commands), because the combined code hasn't been tested yet.
4. Push. After a rebase, use `git push --force-with-lease`, on your own branch only.
5. Create the PR.

Never merge `main` into your branch, and never skip these steps to save time.

### Before merging

The author must:

1. Run style and the local checks for each area touched, listed under [Commands](#commands). Docker changes are checked by CI's image builds.
2. Confirm every acceptance criterion of the issue is met.
3. Confirm CI is green.
4. Repeat [the rebase and checks](#before-opening-a-pr) if `main` moved after the PR opened.

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
- Stock price and value are for `metrics:financial` only. MCP tools get the inventory view from `inventory_view(caller)` and never name it directly. The database can't enforce this per user, because MCP has one credential.

## Database on AWS

RDS needs setup that local Postgres doesn't, because `vx-db upgrade` creates roles and the `vector` extension. Run this once as the RDS master user, using a password from Secrets Manager:

```sql
CREATE ROLE migration_user LOGIN CREATEROLE PASSWORD '<from-secrets-manager>';
GRANT rds_superuser TO migration_user;
CREATE DATABASE vx_materiais OWNER migration_user;
```

Then run `vx-db upgrade` followed by `vx-db set-passwords`, with `MIGRATION_DATABASE_URL`, `API_DB_PASSWORD`, `BATCH_DB_PASSWORD` and `MCP_DB_PASSWORD` set. These steps haven't been run on RDS yet, so [#6](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/issues/6) must confirm them and correct this section if needed.

## Attribute extraction

Extraction prefers leaving a field empty to guessing, because a wrong value can cause a wrong merge. Add an alias to its tables only when it's unambiguous. For example, `INOX 316` doesn't map to `ACO INOX FORJADO A182 F316`, since text alone can't say forged or cast. PSI converts to BAR only when it is a whole bar written the kit's way, rounded to 5 PSI (`145PSI` is `10BAR`). Other PSI values, like `150PSI`, stay empty instead of rounding into another item's pressure. Tests hold real base rows with results checked by hand, so add one with each new rule.

## Duplicate proposals

The batch only proposes merges, and people approve them through the API. Default candidates come from exact identity: same required attributes or, in reference classes, same manufacturer and reference, as PDM rule 10 says. `tokens_v1` stays registered but off, because in reviewed pairs only 7 of 23 of its decided suggestions were the same item.

To change the default, measure against `back/tests/fixtures/merge_review.json`. Those pairs were reviewed by reading descriptions during development, so add pairs reviewed by people who know the materials whenever possible.

## Similar material search

`search_similar_materials` combines exact identity and PostgreSQL full-text, then compares attributes. It reads the index the batch builds with `vx-back index`, and refuses an index built with other rules: index and query must share the same version, PDM and algorithms. Changing classification or extraction rules changes that version, so rebuild the index after pulling such a change: `docker compose build batch`, then `docker compose run --rm batch`. `docker compose up --build` doesn't rebuild the batch image. Embeddings are optional, set with `EMBEDDING_REPOSITORY`, and stay off by default. On the 202 pairs the base declares identical, a local model (`ollama_nomic_v1`) found 126 in the top 10 against 124 without embeddings, at three times the cost. Titan on AWS is still to be measured. Compare any change with:

```bash
uv run python -m vx_materials_mcp.evaluation --repository hybrid_embeddings_v1
```

That runs from `mcp/`, needs `DATABASE_URL` and an index built with the same `EMBEDDING_REPOSITORY`. The local model runs with `docker compose --profile embeddings up -d embeddings`.

The index version holds the PDM label and the workbook's SHA-256, each algorithm's name and `revision`, `IDENTITY_RULES_VERSION` and, when set, the embedding model's signature. Bump `revision` when you change a classifier's or extractor's rules or tables, `IDENTITY_RULES_VERSION` when identity rules change, and `INDEX_FORMAT` when the search text or tokens change. After any of these, or a new PDM workbook, search answers "Indice de busca ausente" until you rebuild the index with `docker compose run --rm batch`, or `uv run vx-back index` from `back/` with the `batch_user` connection.

The Agent passes the caller validated from the internal token to the MCP server in `VX_CALLER`, never as a tool parameter. Without it, search returns no stock. The token carries the user's permissions and authorized centers, and stock outside those centers never reaches the chat.

In chat, a complete card is ready to submit only after the search ran, found no item with the same identity, and the requester dismissed every similar item shown. If the search fails, the turn stays `NEEDS_INPUT`, because merging different items costs more than waiting. A verified match shows the active code instead: a blocked item points to its active target, and an obsolete one is never offered.

Similar items without verified identity are listed for the requester to pick one or answer "Nenhum desses é o meu item". The front buttons send a structured `action` (`PICK_CANDIDATE` or `DISMISS_CANDIDATES`), so their label can change freely; typed replies are still read deterministically as a fallback. A dismissal covers only the codes shown: new candidates are asked about again. The API accepts a dismissal or a pick only for codes it stored as offered in an earlier turn of the same session, and answers 422 otherwise.

The API saves the last accepted duplicate check with the card's signature (class and filled attributes). While the card doesn't change, the agent reuses it instead of searching again, so a pick or dismissal holds on later turns. A changed card searches again, and a turn without a search whose card differs from the saved one is never ready to submit. `READY_TO_SUBMIT` registers nothing: submitting and publishing an order belong to the approval flow.

## Correction proposals

The same batch run proposes `PDM_CORRECTION` (description in PDM format, merchandise group of the class) and `UNIT_CORRECTION` (unit spelled as an alias, like `PCA` or `UN` for `PC`), one proposal per type and material. Every change records before, after and rule.

Governança applies an approved merchandise group through the same decision endpoint as merges. The API checks that the group matches the confirmed PDM class, and approves only when the PDM data is complete. It saves the group in `merchandise_group`, and keeps the loaded value in `original_merchandise_group` and in the snapshot. Like any approval, it refuses an NCM outside the class references (`NCM_REFERENCE_MISMATCH`). In the kit, 196 of the 325 group corrections without conflicts can be applied: 113 stop on the NCM and 16 on incomplete PDM data.

Only `ATIVO` materials are corrected, as with merges. Corrections also need a trusted class: classified, and the PDM item name opens the description. A class name found mid-text is usually an attribute of an abbreviated product, such as `PARAFUSO SEXT ... REVESTIMENTO`, so those materials only get a pending reason. The one exception is a unit alias of the same unit, like `PÇ` to `PC`, proposed with the rule `unit.alias_without_class` and never replaced by a class default. Packaging units without a known factor (`CX`, `CT`, `JG`) are never converted. The report counts pending reasons by type. Select the rules with `CORRECTION_REPOSITORY`, default `head_noun_v1`.

Each proposal carries only the pending reasons of its own type as conflicts: an incomplete description doesn't block a unit spelling fix, and a packaging unit without factor doesn't block a description fix. Unknown reasons block every type. An approved `UNIT_CORRECTION` changes only the unit of one active material, and only when the new unit is the normalized spelling of its current unit, so it needs no class or complete PDM and never touches identity, description, NCM or quantities; anything else is `UNIT_NOT_ALIAS`. Approval compares NCM with the class references in normalized form, so `84314390` matches `8431.43.90`.

## Full-base runs

`vx-back sanitize --job-id <id>` runs a job the API created, and resumes from its checkpoint if it stopped. Analysis is saved in chunks of 1,000 materials under `runs/<job_id>/analysis/` in storage, and proposals are saved in batches of 500 in the same transaction as the checkpoint, so a rerun skips finished work and never duplicates a proposal. The job and every analysis chunk record the rules signature, the same PDM hash and revisions the search index uses. Resuming after any of them changed fails the job with the reason and leaves its chunks as they are: create a new job instead. Without `--job-id` the run is in memory, with nothing to resume. Locally, `APP_ENV=local uv run vx-batch-job` (from `api/`, with the `api_user` connection) also creates a job without the screen.

Governança starts jobs on `/batch` (`POST /api/v1/batch/jobs`); locally, sign in with the `GESTOR_CADASTRO` account. The API writes a manifest to `runs/<job_id>/manifest.json`, with no user token, and launches the task through `BATCH_RUNNER`: `local_process` runs `vx-back sanitize` as a subprocess with the `batch_user` connection from `BATCH_DATABASE_URL`, only with `APP_ENV=local`. An ECS RunTask runner joins it for AWS (#6). Each run claims the job with its own worker id in `checkpoint.lease`, and every write requires that lease and status `RUNNING`, so a second worker is refused while the first has a fresh heartbeat. The worker beats every 15 s between checkpoints. A job without a heartbeat for `BATCH_HEARTBEAT_TIMEOUT_SECONDS` (default 120) becomes `FAILED` with `WORKER_TIMEOUT`, or `WORKER_NOT_STARTED` if the task never started, and the old worker stops on its next write. `POST /api/v1/batch/jobs/{id}/resume` puts a failed job back in the queue and the task continues from its checkpoint.

A finished job stores its metrics in `batch_jobs.counts` and `runs/<job_id>/metrics.json`: the contract counts (`proposals`, `merges`, `ncm`, `enrichment`), counts by type, one outcome per material (`PROPOSTA`, `PENDENTE`, `SEM_ALTERACAO` or `ERRO_ANALISE`, always summing to the base), time per stage and attempt, and model usage. The batch doesn't call models yet, so usage is zero and says so.

Merge precision is measured on a random sample of all merge proposals in `back/tests/fixtures/merge_precision_sample.json`, reviewed by reading descriptions. If proposals change, the test asks for a new sample and review.

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
- Files go through `clients/storage.py`, using a local folder by default and S3 with `STORAGE_BACKEND=s3`. Stored files are immutable.
- Data stays in the repo so anyone, judges included, can run the project from a clone. Review this once the database exists.
- Data is synthetic, except that the last 15 base records are real products. Those are the only ones to enrich from public sources, and each value must record its source.

## Keeping this file current

When a PR changes a workflow, command, structure or rule described here, update this file in the same PR. Claude-specific notes go in `CLAUDE.md`, everything else here.
