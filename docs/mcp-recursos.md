# Resources, prompts e cache de enriquecimento MCP

O servidor stdio registra `enrich_from_trusted_source`, quatro templates de resource e
três prompts v1. A descoberta e as chamadas passam pelo protocolo MCP real.

A tool recebe somente `material_code`, `attributes_requested` e `refresh`. O servidor
consulta `datasets.real_material_codes` pela view `mcp_datasets`, exige um manifesto
com 15 códigos no dataset mais recente e confere o material no mesmo tenant. Nenhuma lista ou URL enviada pelo
modelo pode ampliar esse escopo. A consulta oficial de NCM continuará independente
dessa restrição quando seu serviço estiver integrado.

O preview externo reutiliza o catálogo revisado, o cliente HTTPS, os leitores de
documentos e o extrator registrado da #23/#210. O MCP não chama o produtor batch,
que grava artefatos e propostas. O comportamento é:

| Situação | Resultado |
|---|---|
| Todos os atributos pedidos têm evidência em cache, sem refresh | `EVIDENCE_FOUND`, sem consulta externa |
| Falta cache para algum atributo | Consulta somente os atributos faltantes nas fontes selecionadas pelo servidor |
| `refresh=true` | Consulta os atributos solicitados e conserva todas as evidências persistidas |
| Pesquisa encontra evidência literal do produto exato | Preview com `persisted=false`, `approval_status=PENDING_PUBLICATION`, hash da fonte e confiança calculada pelo mesmo construtor do batch |
| Prazo excedido, fonte recusada/indisponível ou atributo sem evidência | `PENDING`, com `pending_reason` real e cache preservado |
| Código sintético, outro tenant, usuário desativado ou atributo fora da classe | Erro antes da pesquisa externa |

O orçamento de rede de três segundos é único por material e compartilhado por
todas as fontes, incluindo DNS, conexão, TLS, cabeçalhos e corpo. Cada cliente
recebe somente o tempo restante; resultados que chegam depois do prazo são
descartados. HTTP mantém os limites de tamanho, redirecionamento e SSRF da #210.
PDF conserva os limites existentes de bytes, páginas e trabalho de descompressão.
Esse orçamento **não** é uma garantia de três segundos de CPU para analisar PDF.

`SOURCE_QUERY_TIMEOUT`, `SOURCE_UNAVAILABLE`, `EVIDENCE_NOT_FOUND` e
`NO_REVIEWED_EXACT_PRODUCT_SOURCE` distinguem as pendências reais. Não há job,
polling, escrita no banco ou ObjectStore pelo MCP. Preview não vira cache
persistido e seu identificador não garante um resource `evidence://` disponível.
A publicação continua no fluxo separado de enriquecimento com revisão. Bytes
simulados só são aceitos no ambiente local, ficam explícitos na confiança e são
recusados em runtime implantado.

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
`SELECT` para `mcp_reader`; não concede acesso às tabelas nem escrita. O MCP confere
o tenant assinado contra o usuário ativo em cada consulta sensível; mudança de
tenant ou desativação do usuário retira o acesso mesmo se o token interno ainda estiver no prazo.

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
manifesto vigente dos 15, cache/refresh/conflitos, preview com extrator real e bytes
simulados, orçamento compartilhado entre fontes, dataset mais recente por tenant,
centros, campos financeiros, usuário inexistente/desativado/reassociado e
material/evidência conhecidos de outro tenant.
