# Chat de cadastro com Bedrock Sonnet 5

**Objetivo:** atender à #275 usando Sonnet 5 para interpretar a conversa e entrevistar o solicitante.

**Arquitetura:** duas chamadas Converse por turno: interpretação estruturada e redação baseada na ficha validada. O ciclo MCP atual continua calculando validação, duplicidade e prontidão. Sem modelo configurado, permanece o fluxo local por regras. Configuração AWS usa `us.anthropic.claude-sonnet-5`; sem fallback silencioso quando configurado.

**Decisão:** reutilizar boto3 e o ciclo existente, sem outro framework de agentes nem mudanças no fluxo público do frontend. O contrato interno API → Agent inclui a classe/nome da última ficha aceita; seus tipos são regenerados. Não executar um loop livre de ferramentas: isso permitiria pular verificações obrigatórias.

- [x] Testar chamadas SDK, histórico, evidência literal de atributos, classe/nome permitidos, correções e troca de classe.
- [x] Implementar cliente Bedrock e system prompt versionado; validar toda saída e limitar chamadas e tempo de rede.
- [x] Integrar ao endpoint autenticado, preservando botões, ferramentas e estados calculados pelo domínio; sanitizar falhas.
- [x] Configurar exemplo AWS, documentar IAM e ativação, executar suites back/MCP/API e revisão do diff.

**Limites:** não publicar materiais, decidir NCM, autorizar merge nem inventar atributos. Nenhum teste simulado comprova qualidade do modelo ou acesso real na conta AWS. Prazo atual de 20 segundos deve ser homologado com Sonnet 5 na AWS.

## Verificação local

Com `UV_CACHE_DIR=/tmp/vx-uv-cache`:

- `cd back && uv run --locked pytest -q --durations=5`: 1.017 passaram.
- `cd mcp && TEST_DATABASE_URL=postgresql+psycopg://migration_user:local_only_migration@127.0.0.1:5432/vx_sonnet_merge_mcp_test uv run --locked pytest -q --durations=5`: 415 passaram, sem skips.
- `cd api && TEST_DATABASE_URL=postgresql+psycopg://migration_user:local_only_migration@127.0.0.1:5432/vx_opus_merge_api_test uv run --locked pytest -q --durations=5`: 743 passaram, sem skips.
- Verificação final dos ajustes na busca: `uv run --locked --package vx-materials-mcp pytest mcp/tests/test_bedrock_chat.py mcp/tests/test_search_identity_safety.py -q`: 52 passaram.
- Verificação final do erro sem perda de estado: `TEST_DATABASE_URL=postgresql+psycopg://migration_user:local_only_migration@127.0.0.1:5432/vx_opus_fix_uncertain_test uv run --locked --package vx-materials-api pytest api/tests/test_chat.py -q`: 65 passaram.
- `uv run --locked --package vx-materials-back pytest scripts/tests -q`: 67 testes e 31 subtests passaram. Os seis casos de IAM foram observados falhando antes da correção (cinco falhas por falta de acesso e um caso de isolamento já aprovado).
- Em `front/`: `npm run api:check`, `npm run typecheck`, `npm test` e `npm run build`: aprovados; 92 testes.
- `uv run --locked ruff check .`, `uv run --locked ruff format --check .` e `git diff --check`: aprovados.

As regressões reproduzem troca de classe e de item dentro da classe, remoção persistida,
tentativa de restaurar fatos históricos e uma classificação inconclusiva sem perda de estado.
A busca usa só os atributos aceitos; trechos de revisão de peça são preservados pelo mesmo
regex do domínio, para que limpar o histórico da consulta não autorize uma identidade insegura.
Três variantes de revisão foram verificadas com o repositório Hybrid real. A revisão independente
final não encontrou outros bloqueios concretos. Invocação real e aplicação da stack continuam pendentes.
