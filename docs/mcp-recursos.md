# Resources, prompts e cache de enriquecimento MCP

O servidor stdio registra `enrich_from_trusted_source`, quatro templates de resource e
três prompts v1. A descoberta e as chamadas passam pelo protocolo MCP real.

A tool recebe somente `material_code`, `attributes_requested` e `refresh`. O servidor
consulta `datasets.real_material_codes` pela view `mcp_datasets`, exige um manifesto
com 15 códigos e confere o material no mesmo tenant. Nenhuma lista ou URL enviada pelo
modelo pode ampliar esse escopo. A consulta oficial de NCM continuará independente
dessa restrição quando seu serviço estiver integrado.

A pesquisa externa depende da #23, ainda não integrada. O comportamento disponível é:

| Situação | Resultado |
|---|---|
| Todos os atributos pedidos têm evidência em cache | `EVIDENCE_FOUND`, com origem, confiança registrada e situação de aprovação |
| Falta cache para algum atributo | `PENDING`, cache existente e lista `pending_attributes` |
| `refresh=true` | `PENDING`, preserva cache e informa todos os atributos solicitados como pendentes |
| Código sintético, outro tenant ou identidade sem permissão | Erro, sem consultar evidência daquele material |

Toda pendência de pesquisa traz `pending_reason=TRUSTED_SOURCE_SERVICE_UNAVAILABLE`.
Isso **não** significa que uma pesquisa foi agendada: não há job, polling ou escrita
pelo MCP. Não se simula timeout nem se inventa fonte. A integração da #23 deverá
substituir esse motivo pelo estado real da pesquisa, com prazo limitado e fallback
para o mesmo cache. Não foi copiado código de branches ainda não integradas.

Somente evidências `PENDING` e `APPROVED` participam do cache; `REJECTED` não volta
como sugestão. Valores diferentes do mesmo atributo aparecem em `conflicts`; o
servidor preserva as origens e não escolhe um vencedor por confiança. A tool não
altera o cadastro nem a situação de aprovação.

Os resources disponíveis são:

- `pdm://{pdm_version}/classes/{pdm_class_id}` usa o mesmo template e validação de
  versão de `get_pdm_template`. É uma referência pública do kit.
- `material://{material_code}` exige `materials:read` e usuário ativo. O tenant assinado é
  conferido contra o usuário ativo em `mcp_callers`, sem novo parâmetro editável.
  A ficha contém somente campos da view autorizada; estoque exige `inventory:read`,
  filtra centros do usuário e considera somente o dataset mais recente daquele
  tenant. Só inclui preço/valor com `metrics:financial`.
- `evidence://{source_id}` exige o mesmo escopo, inclusive quando alguém conhece o
  UUID de uma evidência de outro tenant. Retorna origem, trecho, valor proposto,
  confiança e situação; não expõe arquivo bruto ou chave de armazenamento.
- `ncm://{ncm_version}/codes/{code}` está registrado, mas retorna erro explícito de
  referência oficial indisponível. Não há registro fiscal nem vigência inventados
  a partir do NCM de um material ou de uma referência PDM. Depende da integração
  do snapshot versionado (#30) e regras fiscais (#22).

A migração `0014_mcp_resource_scope` acrescenta apenas as views de identidade ativa e manifesto, com
`SELECT` para `mcp_reader`; não concede acesso às tabelas nem escrita. O MCP deriva
o tenant novamente em cada consulta sensível, portanto usuário desativado deixa de
ter acesso mesmo se o token interno ainda estiver no prazo.

`interview_material_request_v1`, `explain_identity_decision_v1` e
`explain_ncm_review_v1` contêm instruções versionadas. Contexto JSON é tratado como
dado, não autorização. A entrevista consulta template e validador; explicações
usam diferenças, pendências e evidências existentes. Respostas continuam sujeitas
à validação PDM e revisão fiscal; nenhum prompt publica ou aprova alterações.
Mudanças dessas instruções devem criar outro identificador de versão.

Validação local, com banco descartável exclusivo terminado em `_test`:

```bash
TEST_DATABASE_URL=postgresql+psycopg://migration_user:senha@127.0.0.1:5432/vx35_resources_test uv run pytest mcp/tests
TEST_DATABASE_URL=postgresql+psycopg://migration_user:senha@127.0.0.1:5432/vx35_resources_test uv run pytest api/tests/test_db_schema.py
```

A suíte cobre descoberta, leitura real por stdio, versão do PDM, prompts,
manifesto dos 15, cache/refresh/conflitos, dataset mais recente por tenant, centros, campos financeiros, usuário
inexistente/desativado e material/evidência conhecidos de outro tenant.
