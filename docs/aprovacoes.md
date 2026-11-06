# Fila, aprovação e auditoria

A #20 implementa a leitura de propostas persistidas, revisão técnica/fiscal e
aplicação atômica. A produção das propostas usa o batch da #19 e o processamento
com checkpoints da main. Chat e aprovação compartilham a sessão da #7 e a
política de autorização da #9. A homologação Cognito na AWS permanece na #91,
conforme o escopo local primeiro acordado.

## Rodar localmente

Na raiz, com Docker disponível:

```bash
APP_ENV=local ENABLE_LOCAL_TEST_SESSIONS=true NEXT_PUBLIC_DATA_SOURCE=api docker compose up --build -d --wait
```

Abra `http://localhost:8000`, entre como Governança ou Fiscal e abra Saneamento.
O bootstrap carrega os materiais originais. Para gerar propostas, execute:

```bash
APP_ENV=local ENABLE_LOCAL_TEST_SESSIONS=true NEXT_PUBLIC_DATA_SOURCE=api docker compose --profile batch run --rm --build batch
```

O batch grava o contrato `proposal-v1`, incluindo versões, referência PDM e hash
compartilhado com a API. A repetição não duplica propostas. Chat, saneamento e
auditoria usam dados persistidos; pedidos, enriquecimento e dashboard continuam
demonstrativos. O front usa a API por padrão; `NEXT_PUBLIC_DATA_SOURCE=mock`
seleciona explicitamente o protótipo visual.

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
estado final, fontes, conflitos, conversões, mudanças de antes/depois e hashes das evidências.
O identificador persistido inclui o hash desse conteúdo: observações de uma nova
versão geram outra proposta, enquanto repetir o mesmo conteúdo não duplica nada.
O MVP exige um único dataset por empresa para persistir as propostas de batch;
mais de um exige seleção explícita antes de continuar. Propostas incompletas
continuam visíveis na fila com conflitos e podem ser rejeitadas, mas não aplicadas.
Correções de grupo sem persistência suportada e correções sem PDM completo
permanecem bloqueadas. A revisão exibe as alterações e fontes originais; não
descarta campos silenciosamente nem registra uma aplicação parcial como sucesso.
Aplicação do grupo está acompanhada na [#94](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/issues/94);
a resolução de pendências incompletas permanece na #68.

O produtor deve calcular `domain.proposals.proposal_hash(members, changeset,
evidence_ids)`. A API recalcula o mesmo hash, sem depender da ordem das chaves do
JSON. O hash não torna uma sugestão correta: a API ainda valida PDM, identidade,
versões, escopo, principal, fontes e revisões. Scores nunca autorizam unificação.
Para enriquecimento, cada evidência deve existir no banco e coincidir com o hash
de seus fatos, calculado por `schemas.proposals.evidence_hash`.
As conversões de aliases de unidade registram fator 1 e a regra da normalização;
embalagens sem fator continuam bloqueadas. Normalizar o NCM original também
exige revisão fiscal quando muda o valor persistido.

Os estados persistidos dos membros são conferidos contra as interpretações;
fabricantes diferentes, referências diferentes ou atributos contraditórios
bloqueiam a aprovação. Mudanças conhecidas na base fiscal exigem revisão fiscal.
Referências com separadores ou sufixo neutro seguem `domain.identity.reference_key`,
a mesma regra usada pelo batch; a API não mantém um segundo normalizador.
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

Uma nova execução do batch com conteúdo diferente para o mesmo dataset, tipo e
membros substitui a proposta `PENDING` anterior (#115): na mesma transação que
grava a nova, a anterior vira `STALE`, com evento de sistema `PROPOSAL_SUPERSEDED`
que aponta a substituta. Assim a fila mostra um único conjunto pendente por material
e tipo. Propostas `APPLIED` e `REJECTED` nunca mudam.

`Idempotency-Key` é um UUID com escopo por usuário e operação. Repetir chave e
payload retorna a resposta original; mudar o payload retorna 409. A autorização
do recurso é conferida também na repetição. Erros no banco desfazem a aplicação
e a auditoria conjuntamente.

### Correções de unidade e NCM sem pontos (#111)

Uma `UNIT_CORRECTION` aprovada troca só a unidade de um material ativo, e só quando
a nova unidade é a grafia normalizada da unidade atual (`PCA`, `UN`, `PÇ` → `PC`).
Ela não exige classe nem PDM completo, e não altera identidade, descrição, NCM,
canonicidade nem quantidades. Se a unidade atual não for alias da proposta, a
resposta é `422 UNIT_NOT_ALIAS`: conversão entre unidades diferentes exige outra
revisão. Cada proposta do batch leva como conflito só as pendências do próprio tipo.

A checagem `NCM_REFERENCE_MISMATCH` compara o NCM normalizado, porque a base traz
`84314390` ou `8431.4390` e o PDM traz `8431.43.90`. O NCM gravado não muda.

Na base do kit, aprovando cada correção pela API com rollback ao final (o "depois" já inclui
a aplicação de grupo da #94):

| Tipo | Aplicadas antes | Aplicadas depois | Recusadas depois |
|---|---|---|---|
| `UNIT_CORRECTION` (887) | 237 | 870 | 17 `PROPOSAL_CONFLICT`: unidade diferente da classe, como óleo em `UN` numa classe em `L` |
| `PDM_CORRECTION` (7.202) | 3.688 | 6.040 | 697 `PDM_INVALID`, 204 `PROPOSAL_CONFLICT` (descrição incompleta), 261 `NCM_REFERENCE_MISMATCH` real |

Antes, 2.440 propostas paravam em `NCM_REFERENCE_MISMATCH` por grafia e 1.443 em
`PROPOSAL_CONFLICT` por pendência de outro tipo. `PDM_INVALID` subiu de 281 para 697
porque essas propostas agora chegam à validação do PDM, que as recusa com o motivo
certo, por exemplo uma embalagem `CT` que a classe não aceita.

Os saldos originais nunca são atualizados. A migração `0005` cria vínculos entre
cada snapshot original e o principal, com fator, unidade e fonte da conversão.
As views MCP passam a consultar esses vínculos. Quantidades só são somadas na
mesma unidade e centro, com fatores explícitos; o valor original é conservado.
Consolidações posteriores reaproveitam o fator existente, evitando conversão
duplicada. Valor desconhecido continua nulo. Dependentes existentes devem estar
incluídos quando seu principal é consolidado novamente.
Propostas anteriores ao contrato versionado ficam desatualizadas, com evento
de sistema preservando o conteúdo anterior. Executar o batch gera propostas
versionadas novas; propostas sem esse contrato não são expostas à decisão.

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
estoque/valor. Os testes de credenciais usam os logins temporários da main;
uma instância descartável separada também pode ser usada para isolar execuções.

```bash
docker run --name vx-approval-tests --rm -d -p 127.0.0.1:55432:5432 -e POSTGRES_USER=migration_user -e POSTGRES_PASSWORD=local_only_migration pgvector/pgvector:pg16
```

Em `api/`:

```bash
TEST_DATABASE_URL=postgresql+psycopg://migration_user:local_only_migration@127.0.0.1:55432/vx_materials_test uv run pytest
```

Ao terminar, pare apenas o container descartável com `docker stop vx-approval-tests`.
Os testes de integração usam cookies locais reais e verificam os 403 dos três
papéis, a troca de ator e a aplicação de uma proposta produzida pelo batch.
A suíte também cobre o adaptador Cognito com assinaturas RSA e OAuth controlado;
isso não substitui a homologação AWS da #91.
