# Fila, aprovação e auditoria

A #20 implementa a leitura de propostas persistidas, revisão técnica/fiscal e
aplicação atômica. A produção das propostas pertence à #19. O login Cognito e a
política completa de autorização pertencem às #7 e #9; esta entrega permanece
em rascunho até a integração dessas dependências.

## Rodar localmente

Na raiz, com Docker disponível:

```bash
APP_ENV=local ENABLE_LOCAL_TEST_SESSIONS=true NEXT_PUBLIC_DATA_SOURCE=api docker compose up --build -d --wait
```

Abra `http://localhost:8000`, entre como Governança ou Fiscal e abra Saneamento.
O bootstrap carrega os materiais originais, mas não fabrica propostas: a fila
fica vazia enquanto o produtor não gravar propostas válidas. Chat, pedidos,
enriquecimento e dashboard continuam demonstrativos, como informa a interface.
Sem `NEXT_PUBLIC_DATA_SOURCE=api` no build, o front usa o protótipo com mocks.

O acesso local usa cookie opaco HttpOnly, expira em uma hora e pode ser revogado
no logout. A criação da sessão exige a origem configurada em `APP_ORIGIN`.
As três personas têm papéis fixos no servidor; decisões não aceitam ator ou papel.
O tenant é o mesmo do bootstrap. A flag de sessão é desligada por padrão e recusa
inicialização fora de `APP_ENV=local`, com origem não loopback ou marcadores AWS.
A publicação local do Compose fica em `127.0.0.1:8000`.

## Contrato do produtor

`api/contracts/fixtures/approval-proposal.json` exemplifica o conteúdo privado
persistido. `members` registra os UUIDs, versões observadas e interpretações PDM.
`changeset` usa `schema_version: proposal-v1`, dataset, versão e SHA-256 do PDM,
estado final, fontes, conflitos, conversões e hashes das evidências.

O produtor deve calcular `domain.proposals.proposal_hash(members, changeset,
evidence_ids)`. A API recalcula o mesmo hash, sem depender da ordem das chaves do
JSON. O hash não torna uma sugestão correta: a API ainda valida PDM, identidade,
versões, escopo, principal, fontes e revisões. Scores nunca autorizam unificação.
Para enriquecimento, cada evidência deve existir no banco e coincidir com o hash
de seus fatos, calculado por `schemas.proposals.evidence_hash`.

Os estados persistidos dos membros são conferidos contra as interpretações;
fabricantes diferentes, referências diferentes ou atributos contraditórios
bloqueiam a aprovação. Mudanças conhecidas na base fiscal exigem revisão fiscal.
Uma correção exclusivamente fiscal não transforma o cadastro em principal
canônico nem altera sua descrição ou estoque.

## Transação e estoque

A decisão recebe versão esperada, área, aprovação/rejeição, justificativa e,
opcionalmente na revisão técnica, o código principal. Não recebe novos valores.
Cookies exigem Origin e CSRF; somente um provedor confiável pode declarar uma
identidade bearer. Governança decide a técnica; Fiscal decide a fiscal.

Uma trava transacional por tenant serializa as decisões; proposta e materiais
também são bloqueados. A aplicação e o evento de auditoria são confirmados no
mesmo commit. Se houver duas revisões, a primeira registra a decisão sem alterar
materiais. A segunda só aplica se o conteúdo aprovado e as versões continuarem
iguais. Propostas desatualizadas recebem `STALE` e resposta 409 persistida.

`Idempotency-Key` é um UUID com escopo por usuário e operação. Repetir chave e
payload retorna a resposta original; mudar o payload retorna 409. A autorização
do recurso é conferida também na repetição. Erros no banco desfazem a aplicação
e a auditoria conjuntamente.

Os saldos originais nunca são atualizados. A migração `0003` cria vínculos entre
cada snapshot original e o principal, com fator, unidade e fonte da conversão.
As views MCP passam a consultar esses vínculos. Quantidades só são somadas na
mesma unidade e centro, com fatores explícitos; o valor original é conservado.
Consolidações posteriores reaproveitam o fator existente, evitando conversão
duplicada. Valor desconhecido continua nulo. Dependentes existentes devem estar
incluídos quando seu principal é consolidado novamente.

## Consultas e interface

A fila e a auditoria paginam com cursor UUID. A leitura e a decisão validam o
tenant e todos os centros envolvidos. Conhecer um UUID não concede acesso.
Dados financeiros só são enviados ao Fiscal, inclusive nos snapshots da
auditoria. A auditoria guarda ator, papel efetivo, justificativa, request ID,
proposta vinculada, antes/depois e fontes utilizadas.

O front usa `/saneamento/revisao/?id=<uuid>`, compatível com export estático e
IDs reais. A tela aguarda a resposta do servidor e atualiza a proposta; não
simula uma aplicação bem-sucedida. A chave de idempotência permanece igual
durante a repetição de uma tentativa com o mesmo conteúdo.

## Verificação

A suíte da API cobre transações reais em PostgreSQL, concorrência, repetição,
rollback, versões, separação de revisões, escopos, evidências e conservação de
estoque/valor. Use uma instância descartável separada para os testes: os testes
existentes de credenciais alteram roles globais do cluster, mesmo quando o banco
tem sufixo `_test` ([#58](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/issues/58)).

```bash
docker run --name vx-approval-tests --rm -d -p 127.0.0.1:55432:5432 -e POSTGRES_USER=migration_user -e POSTGRES_PASSWORD=local_only_migration pgvector/pgvector:pg16
```

Em `api/`:

```bash
TEST_DATABASE_URL=postgresql+psycopg://migration_user:local_only_migration@127.0.0.1:55432/vx_materials_test uv run pytest
```

Ao terminar, pare apenas o container descartável com `docker stop vx-approval-tests`.
Os testes usam um provedor de identidade controlado ou a sessão local; não
comprovam a integração Cognito/RBAC real exigida para fechar a #20.
