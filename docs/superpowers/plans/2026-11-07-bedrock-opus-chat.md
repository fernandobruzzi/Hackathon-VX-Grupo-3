# Chat de cadastro com Bedrock Opus 5.5

**Objetivo:** atender à #275 usando Opus 5.5 para interpretar a conversa e entrevistar o solicitante.

**Arquitetura:** duas chamadas Converse por turno: interpretação estruturada e redação baseada na ficha validada. O ciclo MCP atual continua calculando validação, duplicidade e prontidão. Sem modelo configurado, permanece o fluxo local por regras. Configuração AWS usa `us.anthropic.claude-opus-5-5`; sem fallback silencioso quando configurado.

**Decisão:** reutilizar boto3 e o ciclo existente, evitando outro framework de agentes ou alterações no contrato do frontend. Não executar um loop livre de ferramentas: isso permitiria pular verificações obrigatórias.

- [x] Testar chamadas SDK, histórico, evidência literal de atributos, classe/nome permitidos, correções e troca de classe.
- [x] Implementar cliente Bedrock e system prompt versionado; validar toda saída e limitar chamadas e tempo de rede.
- [x] Integrar ao endpoint autenticado, preservando botões, ferramentas e estados calculados pelo domínio; sanitizar falhas.
- [x] Configurar exemplo AWS, documentar IAM e ativação, executar suites back/MCP/API e revisão do diff.

**Limites:** não publicar materiais, decidir NCM, autorizar merge nem inventar atributos. Nenhum teste simulado comprova qualidade do modelo ou acesso real na conta AWS. Prazo atual de 20 segundos deve ser homologado com Opus na AWS.

## Verificação local

Com `UV_CACHE_DIR=/tmp/vx-uv-cache`:

- `cd back && uv run --locked pytest -q`: 1.012 passaram.
- `cd mcp && TEST_DATABASE_URL=postgresql+psycopg://migration_user:local_only_migration@127.0.0.1:5432/vx_opus_mcp_test uv run --locked pytest -q`: 397 passaram, sem skips.
- `cd api && TEST_DATABASE_URL=postgresql+psycopg://migration_user:local_only_migration@127.0.0.1:5432/vx_opus_api_test uv run --locked pytest -q`: 734 passaram, sem skips.
- `uv run --locked --package vx-materials-mcp pytest mcp/tests/test_bedrock_chat.py -q`: 25 passaram após as correções da revisão.
- `uv run --locked --package vx-materials-back pytest scripts/tests/test_aws.py scripts/tests/test_ec2.py -q`: 28 testes e 11 subtests passaram.
- `uv run --locked ruff check .`, `uv run --locked ruff format --check .` e `git diff --check`: aprovados.

A revisão independente identificou e verificou a correção de dois casos: valores históricos
normalizados não devem parecer correções novas, e ações de candidatos precisam reconstruir
classes reconhecidas apenas pelo LLM sem alterar a decisão estruturada do usuário.
