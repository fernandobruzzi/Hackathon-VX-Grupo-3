# Solicitação de material: modelo e regras de atendimento

Modelo operacional da jornada do solicitante (M7, #236). Este documento é a referência para
as issues #237 a #251. As decisões D1–D8 foram **aprovadas por Bernardo Pozzato (@bepo7) em 07/11/2026**,
com [validação registrada na #236](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/issues/236#issuecomment-6713442484).
Este é o modelo aprovado para as implementações dependentes. O documento, por si só, não
implementa solicitações nem movimentações de estoque.

## 1. Objetivo

A pessoa que precisa de um material quer recebê-lo, não criar um cadastro. Exemplo: “preciso de
10 unidades da caneta X para o centro 1200”. A solicitação de material registra essa
necessidade e a acompanha até a entrega pelo estoque, o encaminhamento para compras ou o
cancelamento.

Cadastro, PDM, identidade, revisões técnica e fiscal, permissões e auditoria continuam como
estão e passam a apoiar a jornada. Nenhuma regra de identidade muda: semelhança nunca autoriza
unificação nem substituição.

## 2. Conceitos

| Conceito | O que é | O que não é |
|---|---|---|
| Solicitação de material | Necessidade de uma pessoa ou equipe: material, quantidade, unidade, centro | Não é pedido de cadastro nem compra |
| Pedido de cadastro | Trabalho de criar ou completar a identificação de um material (fluxo existente em [pedidos.md](pedidos.md)) | Não entrega nem compra nada |
| Reserva | Compromisso de saldo de um centro para uma solicitação | Não é saída física |
| Entrega | Saída física confirmada de uma quantidade reservada | Não desconta saldo uma segunda vez |
| Reversão | Movimento compensatório de uma entrega | Não apaga nem edita a entrega original |
| Encaminhamento para compras | Demanda registrada para Compras obter uma quantidade | Não comprova pedido ao fornecedor, recebimento ou entrega |
| Mesmo material sob outro código | Identidade comprovada pela decisão compartilhada de identidade | Equivalência técnica não basta |
| Equivalente autorizado | Material distinto com equivalência técnica registrada e aprovada | Não é o mesmo material; saldos nunca se somam |

## 3. Entidades

Os nomes de tabela e campo são definidos na #237; aqui fica o conteúdo mínimo.

- **Solicitação:** protocolo legível, tenant, solicitante, centro de destino, texto original,
  material resolvido (opcional até a identificação), quantidade solicitada, unidade, estado,
  motivo de encerramento e versão para controle otimista. Vínculos com conversa e pedido de
  cadastro.
- **Reserva:** solicitação, material principal, centro, quantidade, estado (`ATIVA`,
  `CONSUMIDA`, `CANCELADA`), dataset de referência do saldo.
- **Movimento:** reserva, tipo (`ENTREGA`, `REVERSAO`), quantidade sempre positiva,
  referência ao movimento revertido quando houver. Movimentos são somente inserção.
- **Encaminhamento para compras:** solicitação, material (código existente ou publicado),
  quantidade, unidade, centro, estado (`ENCAMINHADO`, `ACEITO`, `DEVOLVIDO`, `CANCELADO`) e
  motivo.

Os snapshots de estoque importados (`material_inventory_snapshots`) nunca são alterados por
nenhuma dessas entidades.

## 4. Quantidades

### 4.1 Saldo de um material em um centro

| Termo | Definição |
|---|---|
| Saldo importado (`S`) | Soma dos snapshots do dataset vigente do tenant para o material principal no centro, seguindo as consolidações aprovadas, como a consulta de estoque atual |
| Reservado (`R`) | Soma das reservas `ATIVA` do material no centro |
| Saídas (`E`) | Entregas menos reversões registradas contra o mesmo dataset vigente |
| Disponível (`D`) | `S − R − E` |

Consultar `D` não cria registro algum. Reservar exige `quantidade ≤ D` no momento da
transação. Entregar converte reserva em saída: `R` diminui e `E` aumenta na mesma quantidade,
então `D` não muda na entrega.

### 4.2 Atendimento de uma solicitação

| Termo | Definição |
|---|---|
| Solicitado (`Q`) | Quantidade pedida, na unidade do material |
| Reservado da solicitação (`r`) | Reservas `ATIVA` da solicitação |
| Entregue da solicitação (`e`) | Entregas menos reversões da solicitação |
| Encaminhado (`c`) | Encaminhamentos para compras não cancelados nem devolvidos |
| Pendente (`p`) | `Q − r − e − c` |

**Invariante:** `r + e + c ≤ Q` e `p ≥ 0` em qualquer momento e após qualquer sequência de
operações. A mesma unidade nunca é contada em duas parcelas.

### 4.3 Exemplo numérico

Centro 1200, caneta X, `S = 6`, sem reservas. A solicitação pede `Q = 10`.

| Passo | `D` do centro | `r` | `e` | `c` | `p` |
|---|---|---|---|---|---|
| Solicitação criada | 6 | 0 | 0 | 0 | 10 |
| Reserva de 6 | 0 | 6 | 0 | 0 | 4 |
| Encaminhamento de 4 | 0 | 6 | 0 | 4 | 0 |
| Entrega de 6 | 0 | 0 | 6 | 4 | 0 |
| Reversão de 1 entrega | 1 | 0 | 5 | 4 | 1 |

Uma segunda solicitação no mesmo centro, durante a reserva, vê `D = 0`.

### 4.4 Troca de dataset de estoque (D4)

O snapshot novo já incorpora as saídas anteriores. Uma entrega registrada contra o dataset
anterior não pode ser descontada novamente do saldo novo. Isso é uma premissa operacional
aprovada, não algo que o sistema pode presumir de qualquer arquivo importado.

As reservas ativas não desaparecem com a seleção do dataset mais recente. Na troca, é
necessário reconciliá-las com o saldo novo, preservando quantidade, solicitação, centro e
rastreabilidade do dataset anterior. Até concluir essa revisão, novas reservas dos materiais
e centros afetados ficam bloqueadas. Saldo insuficiente ou origem não confirmada fica para
revisão, sem liberar reservas silenciosamente nem produzir disponibilidade negativa. Os
snapshots originais permanecem imutáveis.

### 4.5 Unidades

A quantidade é registrada na unidade do material. Unidades de embalagem sem fator conhecido
(`CX`, `CT`, `JG`) bloqueiam conversão, como no saneamento: a solicitação pede a unidade do
material ou fica pendente de revisão.

## 5. Estados da solicitação

O estado descreve o processo; as quantidades da seção 4 descrevem o progresso.

| Estado | Significado | Quem age |
|---|---|---|
| `EM_IDENTIFICACAO` | Material ainda não resolvido: identificação inconclusiva em revisão | Cadastro |
| `AGUARDANDO_CADASTRO` | Material inexistente; pedido de cadastro vinculado em andamento | Cadastro, Fiscal |
| `EM_ATENDIMENTO` | Material resolvido; quantidades sendo reservadas, entregues ou encaminhadas | Almoxarifado, Compras |
| `ENCERRADA` | Sem pendência nem reserva ativa, ou cancelada; tem motivo | — |

Motivos de encerramento: `ATENDIDA_ESTOQUE` (`e = Q`), `ATENDIDA_PARCIAL_COMPRAS`
(`e > 0`, `c > 0`), `ENCAMINHADA_COMPRAS` (`e = 0`, `c = Q`), `CANCELADA`,
`CADASTRO_REJEITADO`.

| De | Para | Gatilho |
|---|---|---|
| (criação) | `EM_ATENDIMENTO` | Material identificado, inclusive sob outro código (código ativo) |
| (criação) | `AGUARDANDO_CADASTRO` | Material inexistente, confirmado pelo solicitante; cria o pedido de cadastro |
| (criação) | `EM_IDENTIFICACAO` | Identificação inconclusiva |
| `EM_IDENTIFICACAO` | `EM_ATENDIMENTO` | Cadastro resolve para um material existente |
| `EM_IDENTIFICACAO` | `AGUARDANDO_CADASTRO` | Cadastro conclui que o material não existe |
| `AGUARDANDO_CADASTRO` | `EM_ATENDIMENTO` | Pedido `REGISTERED` (usa o novo código) ou `EXISTING` (usa o código ativo encontrado) |
| `AGUARDANDO_CADASTRO` | `ENCERRADA` | Pedido `REJECTED` (`CADASTRO_REJEITADO`, com o motivo) |
| `EM_ATENDIMENTO` | `ENCERRADA` | `p = 0` e `r = 0` |
| qualquer não encerrado | `ENCERRADA` | Cancelamento pelo solicitante (`CANCELADA`, D8) |

Somente o solicitante cancela a solicitação inteira. Almoxarifado e Compras podem
devolver suas próprias parcelas com motivo, sem cancelar a solicitação inteira.
Ao cancelar, reservas ativas são canceladas e encaminhamentos `ENCAMINHADO` são cancelados.
Entregas já feitas permanecem; revertê-las é uma operação separada. Uma solicitação encerrada
não reabre: o solicitante cria outra.

## 6. Caminhos de atendimento

1. **Identificado com saldo suficiente:** reserva de `Q`, depois entrega.
2. **Identificado sem saldo:** encaminhamento de `Q` para compras com o código existente; nenhum
   pedido de cadastro.
3. **Atendimento parcial (D1):** o solicitante escolhe entre reservar o disponível e encaminhar
   o restante para compras, ou encaminhar toda a quantidade para compras. A opção padrão é
   parcial; consultar o saldo ou selecionar o padrão não executa a operação. Ao confirmar
   parcial, reserva-se até `D` e encaminha-se o restante. Se `D` mudar entre a consulta e a
   reserva, a divisão é recalculada na transação; nunca se reserva mais que o disponível nem
   se encaminha uma quantidade já reservada. Na opção integral por compras, não há reserva.
4. **Inexistente:** pedido de cadastro vinculado; após `REGISTERED`, segue para o caminho 2
   (o material novo não tem saldo).
5. **Inconclusivo:** revisão pelo Cadastro. O sistema não presume inexistência, não cria
   pedido de cadastro automaticamente e não oferece substituto.
6. **Apenas semelhante:** nunca vira o material da solicitação sem confirmação explícita do
   solicitante. Substituição só por equivalente autorizado (#246) e com registro na solicitação.

Material bloqueado ou obsoleto segue a indicação de código ativo existente; um obsoleto nunca é
reservado nem encaminhado.

## 7. Reserva, entrega, cancelamento e reversão

- **Reserva:** uma transação lê `D` com bloqueio por material principal e centro, insere a
  reserva e grava auditoria. Duas reservas concorrentes acima de `D` resultam em uma aceita e
  outra recusada (`409`).
- **Entrega:** consome total ou parcialmente uma reserva `ATIVA`. Parte não entregue continua
  reservada. A reserva vira `CONSUMIDA` quando toda a quantidade foi entregue.
- **Cancelamento de reserva:** libera apenas a quantidade reservada e não entregue.
- **Reversão de entrega:** insere um movimento `REVERSAO` apontando a entrega, limitado à
  quantidade ainda não revertida. Devolve a quantidade a `D` e a `p`.

Todas as operações exigem `Idempotency-Key`, versão esperada da solicitação, autorização por
ação e centro e auditoria na mesma transação, como as aprovações atuais.

## 8. Encaminhamento para compras

O encaminhamento leva código, quantidade, unidade, centro e solicitação de origem. Compras
aceita ou devolve com motivo; devolver retorna a quantidade a `p`. A interface nunca o
apresenta como compra realizada ou material recebido. Acompanhar pedido ao fornecedor e
recebimento fica fora deste modelo (ver decisão D7).

## 9. Papéis e permissões

Os papéis entram na matriz existente (`security/permissions.py`), validados no servidor, com
escopo de tenant e centro.

| Ação | Solicitante | Cadastro (Governança) | Fiscal | Almoxarifado | Compras |
|---|---|---|---|---|---|
| Criar e acompanhar a própria solicitação | Sim | Sim | Sim | Sim | Sim |
| Cancelar a própria solicitação | Sim | Sim | Sim | Sim | Sim |
| Resolver identificação inconclusiva | Não | Sim | Não | Não | Não |
| Reservar, entregar, cancelar reserva | Não | Não | Não | Sim | Não |
| Reverter entrega | Não | Não | Não | Sim | Não |
| Ler e tratar encaminhamentos | Não | Não | Não | Não | Sim |
| Aprovar cadastro, NCM ou unificação | Não | Como hoje | Como hoje | Não | Não |

Permissões propostas: `requests:create`, `requests:read_own`, `requests:cancel_own`,
`requests:identify`, `stock:reserve`, `stock:deliver`, `stock:reverse`, `purchasing:read`,
`purchasing:handle`. Papéis novos: `ROLE_ALMOXARIFADO` e `ROLE_COMPRAS` (#244).

## 10. Decisões aprovadas com a operação

**Responsável:** Bernardo Pozzato (@bepo7). **Data:** 07/11/2026. Após receber as propostas
D1–D8, inclusive o destaque sobre a premissa dos snapshots, confirmou: “Aprovo tudo, mas faz
com cuidado”. O [registro de validação na #236](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/issues/236#issuecomment-6713442484)
identifica quem decidiu e as oito decisões aprovadas.

- [x] **D1. Atendimento parcial:** o solicitante escolhe entre parcial ou encaminhar tudo para
      compras; padrão parcial.
- [x] **D2. Expiração de reserva:** sem expiração automática no MVP; Almoxarifado cancela
      manualmente.
- [x] **D3. Quem confirma a entrega:** Almoxarifado confirma; o solicitante acompanha.
- [x] **D4. Novo dataset de estoque:** o snapshot mais recente já inclui as saídas anteriores;
      saídas são vinculadas ao dataset de origem e reservas ativas são revisadas na troca de
      dataset, sem desconto duplicado nem perda de reservas (seção 4.4).
- [x] **D5. Janela de reversão:** sem prazo limite, sempre com motivo e movimento compensatório
      auditado.
- [x] **D6. Transferência entre centros:** saldo em outro centro é informativo no MVP (#251);
      transferências ficam fora deste modelo.
- [x] **D7. Acompanhamento de compras:** pedido ao fornecedor e recebimento fora do MVP;
      o encaminhamento termina em `ACEITO` ou `DEVOLVIDO`, este último com motivo.
- [x] **D8. Quem pode cancelar:** somente o solicitante cancela a solicitação inteira;
      responsáveis devolvem suas próprias parcelas com motivo.

## 11. Invariantes para os testes

Toda implementação da M7 deve manter, com testes no PostgreSQL:

1. `r + e + c ≤ Q` e `p ≥ 0` após qualquer sequência de operações.
2. `D ≥ 0` para todo material e centro, inclusive com reservas concorrentes.
3. Consultar disponibilidade não insere registros.
4. Entregar não altera `D`; reverter aumenta `D` exatamente na quantidade revertida.
5. Snapshots importados e saldos originais nunca são alterados.
6. Movimentos não são editados nem apagados; correções são novos movimentos.
7. Toda transição tem auditoria com ator, papel efetivo, antes e depois.
8. Repetir uma operação com a mesma `Idempotency-Key` não duplica efeito nem auditoria.
9. Semelhança sem identidade comprovada nunca define o material da solicitação.
10. Trocar o dataset não desconta saídas anteriores novamente nem descarta reservas ativas;
    sem reconciliação concluída, novas reservas dos materiais e centros afetados são bloqueadas.
11. Somente o solicitante cancela a solicitação inteira; tratar uma parcela não concede essa
    permissão ao Almoxarifado ou a Compras.

## 12. Issues da M7

| Issue | Parte deste modelo |
|---|---|
| #237 | Seção 3 (solicitação), estados da seção 5 |
| #238 | Caminhos 1, 4, 5 e 6 da seção 6 a partir do chat |
| #239 | Seções 4.1 e 7 (reserva) |
| #240 | Seção 7 (entrega, cancelamento, reversão) |
| #241 | Caminho 2 e seção 8 |
| #242 | Caminho 3 e decisão D1 |
| #243 | Transição `AGUARDANDO_CADASTRO` → `EM_ATENDIMENTO` |
| #244 | Seção 9 |
| #245 | Estados e quantidades visíveis ao solicitante |
| #246 | Caminho 6, equivalentes autorizados |
| #248 a #251 | Avisos, notificações, indicadores e decisão D6 |

## 13. Base persistida da solicitação (#237)

A API implementa a criação e a leitura em `/api/v1/material-requests`, o detalhe por UUID e
`POST /api/v1/material-requests/{id}/cancel`. A criação recebe `original_text`, `quantity`
(string decimal positiva, até 18 casas inteiras e seis decimais), `unit`, `center_code` e,
opcionalmente, `material_id`, `chat_session_id` e `registration_order_id`. Preserva o texto
original e não arredonda quantidades. O protocolo `SM-00000001` vem de uma sequência do banco:
lacunas por rollback são possíveis, duplicação de protocolo não.

O servidor deriva solicitante, tenant e estado: material ativo identificado leva a
`EM_ATENDIMENTO`; pedido de cadastro próprio em andamento leva a `AGUARDANDO_CADASTRO`;
sem identificação nem pedido, fica `EM_IDENTIFICACAO`. Uma referência a material de outro
tenant, uma conversa de outra pessoa ou um pedido de outro dono/centro não é aceito.
A unidade precisa coincidir com a do material; não há conversão presumida de embalagens.

Todas as leituras exigem tenant e centro autorizados. O solicitante vê somente as próprias
solicitações; Governança também vê pendências de identificação/cadastro nos seus centros,
por `requests:read_queue`. Fiscal vê apenas as solicitações vinculadas a pedidos em
`PENDING_FISCAL`, por `requests:read_fiscal`. `mine=true` restringe a listagem e o detalhe ao próprio usuário. Os novos papéis
e filas de Almoxarifado e Compras continuam na #244.

Criação e cancelamento exigem autenticação, Origin/CSRF nas sessões de navegador e
`Idempotency-Key`. A mesma chave e conteúdo recuperam a resposta; conteúdo diferente recebe
`409`. O cancelamento exige `expected_version` e motivo, e somente o dono pode executá-lo.
Cada criação/transição gera auditoria na mesma transação; o detalhe expõe o histórico em
ordem de versão. Replay não cria outro evento e revalida o escopo atual.

Esta base não entrega nem encaminha para compras. Os vínculos de conversa e pedido
já possuem chaves estrangeiras; reservas, movimentos e encaminhamentos referenciam
a solicitação nas respectivas issues, sem inventar identificadores de entidades inexistentes.
O reset explícito da demo inclui as solicitações, reservas, movimentos e encaminhamentos operacionais.

## 14. Disponibilidade e reserva (#239)

**Tabelas.** `stock_reservations` guarda solicitação, material principal, centro, quantidade
(`NUMERIC(24,6)`), unidade, estado (`ATIVA`, `CONSUMIDA`, `CANCELADA`), dataset de estoque vigente
no momento da reserva, autor e versão. `stock_movements` já existe para a fórmula, mas só a #240
grava nela: reserva, tipo (`ENTREGA`, `REVERSAO`), quantidade positiva, movimento revertido
(obrigatório só na reversão) e dataset de origem. A credencial da API tem `SELECT, INSERT, UPDATE`
nas reservas e apenas `SELECT, INSERT` nos movimentos; `batch_user` e `mcp_reader` não leem
nenhuma das duas. Os snapshots importados continuam sem `UPDATE` nem `DELETE`.

**Disponibilidade.** `GET /api/v1/stock/availability?material_id=…&center_code=…` exige
`inventory:read` e centro autorizado e só lê. Devolve, sem preço nem valor:

- `imported` (`S`): soma dos snapshots do dataset vigente do tenant no centro, seguindo as
  consolidações aprovadas, pela mesma consulta da busca de materiais. Só entram linhas na unidade
  do material; outras unidades aparecem em `unconverted_units` e não são convertidas.
- `reserved` (`R`): reservas `ATIVA` do material principal no centro, de qualquer dataset.
- `delivered` (`E`): entregas menos reversões registradas contra o dataset vigente (D4).
- `available` (`D`): `S − R − E`, nunca exibido abaixo de zero.
- `reservable` e `blocked_reason`: `INACTIVE_MATERIAL`, `MATERIAL_WITHOUT_UNIT`,
  `NO_INVENTORY_DATASET` ou `RECONCILIATION_REQUIRED`, quando há reserva `ATIVA` feita contra um
  dataset anterior. Até a reconciliação da seção 4.4, novas reservas desse material e centro ficam
  bloqueadas, e as antigas continuam contando em `R`.

**Reserva.** `POST /api/v1/material-requests/{id}/reservations` com `expected_version` e
`quantity` exige `stock:reserve` (Almoxarifado) pelo `require_stock_action`, centro autorizado,
Origin/CSRF em sessões de navegador e `Idempotency-Key`. Uma solicitação fora dos centros do
usuário responde `404`, e a consulta de outro centro, `403`. A transação:

1. bloqueia a linha da solicitação e confere versão, estado `EM_ATENDIMENTO`, material ativo e
   unidade;
2. obtém `pg_advisory_xact_lock` por tenant, material principal e centro, e só então lê `D`;
3. recusa com `409 INSUFFICIENT_STOCK` acima de `D` e com `409 QUANTITY_EXCEEDS_PENDING` acima do
   pendente da solicitação (`Q − r − e − c`, seção 16);
4. insere a reserva, incrementa a versão da solicitação e grava `STOCK_RESERVED` em `audit_logs`
   com papel efetivo, disponível antes e depois.

Duas reservas concorrentes acima do disponível resultam em uma aceita e uma recusada: a segunda
espera o bloqueio e lê as reservas já confirmadas. A mesma chave com o mesmo conteúdo devolve a
resposta original, revalidando tenant e centro; conteúdo diferente recebe `409`.
`GET /api/v1/material-requests/{id}/reservations` lista as reservas e as parcelas
(`requested`, `reserved`, `delivered`, `forwarded`, `pending`) para o próprio solicitante ou para quem reserva
no centro.

**Cancelamento.** Cancelar a solicitação muda as reservas `ATIVA` para `CANCELADA` na mesma
transação, com um evento `STOCK_RESERVATION_CANCELLED` por reserva. Movimentos já feitos ficam.

**Pontos de integração.** A #240 (seção 17) grava `stock_movements` com o dataset vigente, muda
reservas para `CONSUMIDA` e cancela reservas avulsas, usando o mesmo bloqueio por material e
centro; a fórmula de `D` e as parcelas da solicitação já contam esses movimentos. A reversão deve apontar
uma entrega do mesmo dataset, para que `E` nunca fique negativo. Os encaminhamentos
da #241 (`c`) já entram no pendente de `stock_service.fulfillment` (seção 16). A reconciliação de reservas na
troca de dataset (seção 4.4) ainda não existe: até lá, o bloqueio `RECONCILIATION_REQUIRED`
impede novas reservas afetadas.

## 15. Aviso de solicitação aberta do mesmo material e centro (#248)

Ao criar uma solicitação com material resolvido, a API procura solicitações não encerradas
(`EM_IDENTIFICACAO`, `AGUARDANDO_CADASTRO`, `EM_ATENDIMENTO`) do mesmo tenant, material e
centro de destino. Se houver alguma e o corpo não trouxer `acknowledge_open_requests: true`,
a criação responde `409 OPEN_REQUESTS_EXIST` e não grava nada: nem solicitação, nem auditoria,
nem resposta idempotente. O cliente mostra o aviso e, se o solicitante confirmar, reenvia o
mesmo corpo com `acknowledge_open_requests: true`, com a mesma `Idempotency-Key` ou outra.
O aviso não bloqueia: necessidades diferentes podem coexistir.

O `details` do aviso traz `total_count`, `hidden_count` e `open_requests`. A lista contém
apenas as solicitações que o usuário já pode ler pela regra de escopo da seção 13 (protocolo,
estado, quantidade, unidade e data). As demais entram somente em `hidden_count`, sem
solicitante, texto, quantidade ou identificador.

A confirmação fica na auditoria da criação: `after_json.open_request_acknowledgement` registra
o total, as ocultas e os identificadores visíveis no momento, e o motivo do evento, exibido no
histórico, informa só a quantidade confirmada. Uma confirmação sem solicitação aberta cria
normalmente, sem esse registro. Solicitações encerradas, por cancelamento ou atendimento, não
geram aviso, assim como solicitações sem material resolvido ou de outro centro. O campo só
entra no hash de idempotência quando é `true`, então chaves gravadas antes dele continuam
válidas.

A verificação usa um bloqueio transacional por tenant, material e centro: duas criações
simultâneas não passam ambas sem aviso. Toda reserva ativa (#239) pertence a uma solicitação
não encerrada, então o critério também cobre reservas sem consultar a tabela delas. Se uma
reserva puder existir sem solicitação aberta, esta consulta precisa incluí-la. Ainda não há
tela de criação de solicitação no front; o contrato descreve o aviso para quando ela existir.

## 16. Encaminhamento para compras sem saldo (#241)

`POST /api/v1/material-requests/{id}/purchase-forwards` implementa o caminho 2. O dono da
solicitação envia `expected_version`; o servidor encaminha toda a quantidade pendente
`p = Q − r − e − c` com o código já cadastrado, sem criar pedido de cadastro e sem tocar nos
snapshots de estoque. O encaminhamento (`purchase_forwards`) guarda solicitação de origem,
material, quantidade, unidade, centro, quem encaminhou e, depois, quem tratou em Compras.

A transação segue a mesma ordem da reserva (seção 14): bloqueia a linha da solicitação, confere
dono, versão, estado `EM_ATENDIMENTO`, material ativo e unidade, obtém o bloqueio consultivo por
tenant, material principal e centro e só então lê as parcelas e o disponível, pelas mesmas
funções `stock_service.fulfillment` e `stock_service.compute_availability`. Recusa com:

- `409 NOTHING_PENDING` quando `p = 0`;
- `409 STOCK_AVAILABLE` quando `D ≥ p`: o atendimento é por reserva. Com `0 < D < p`, encaminhar
  tudo é a opção integral da D1; a divisão entre reserva e compras está na seção 19;
- o `blocked_reason` da disponibilidade (`NO_INVENTORY_DATASET`, `RECONCILIATION_REQUIRED`),
  porque sem saldo confiável a falta não pode ser confirmada;
- `409 STOCK_UNIT_UNRESOLVED` quando o centro tem saldo em outra unidade (`unconverted_units`),
  sem conversão presumida.

Cada parcela é única por versão da solicitação (`material_request_id`, `request_version`), e o
encaminhamento incrementa a versão. Repetir com a mesma `Idempotency-Key` devolve a resposta
salva; outra chave com a mesma versão recebe `409 VERSION_CONFLICT`. A parcela nunca duplica.
Como o pendente da reserva também desconta `c`, uma reserva acima do que sobrou recebe
`409 QUANTITY_EXCEEDS_PENDING`, e `r + e + c ≤ Q` vale entre as duas operações.

A fila de Compras fica em `GET /api/v1/purchase-forwards` (filtros `status` e `center_code`) e
`GET /api/v1/purchase-forwards/{id}`, com `purchasing:read` e somente nos centros autorizados.
`POST .../{id}/accept` e `POST .../{id}/return` (motivo obrigatório) exigem `purchasing:handle`
pelo `require_purchasing_action`, versão do encaminhamento, Origin/CSRF e `Idempotency-Key`. Os
demais papéis recebem `403`; um encaminhamento de centro fora do escopo não aparece (`404`). O
detalhe da solicitação mostra `pending_quantity`, `forwarded_quantity`, os encaminhamentos e a
ação de cada evento do histórico.

Estados e solicitação:

- `ACEITO` termina o encaminhamento (D7). Quando não resta pendência, reserva `ATIVA` nem
  encaminhamento aguardando Compras, a solicitação encerra com `ENCAMINHADA_COMPRAS` (ou
  `ATENDIDA_PARCIAL_COMPRAS` se houver entregas). Enquanto Compras não decide, a solicitação
  continua aberta, porque uma devolução precisa voltar a `p` e uma solicitação encerrada não reabre.
  O encerramento é o mesmo da entrega (`stock_service.close_if_fulfilled`, seção 17).
- `DEVOLVIDO` retorna a quantidade a `p`, incrementa a versão da solicitação e permite reservar
  ou encaminhar de novo.
- O cancelamento pelo solicitante cancela os encaminhamentos `ENCAMINHADO` com o mesmo motivo,
  junto com as reservas `ATIVA`; os encaminhamentos já aceitos permanecem.

Toda criação e transição grava auditoria na mesma transação, para o encaminhamento
(`purchase_forward`) e para a solicitação quando a versão dela muda. A tela `/compras/` mostra a
fila com o aviso de que o encaminhamento é a demanda para Compras e não confirma pedido ao
fornecedor, compra realizada nem recebimento. A divisão parcial da #242 (seção 19) reserva até
`D` e encaminha o restante na mesma transação, reaproveitando essas verificações e a unicidade
por versão.

## 17. Entrega, cancelamento de reserva e reversão (#240)

Nenhuma tabela nova nem migração: as operações gravam em `stock_movements` (somente inserção) e
mudam o estado de `stock_reservations`. Os snapshots importados não são tocados.

**Parte aberta da reserva.** A quantidade da reserva nunca é editada. A parte ainda não entregue
é `quantidade − entregas` da reserva, sem descontar reversões: o que é revertido volta a `D` e a
`p`, não à reserva (exemplo da seção 4.3). `R` (disponibilidade) e `r` (parcelas da solicitação)
somam só essa parte das reservas `ATIVA`, e `e` continua sendo entregas menos reversões. Assim
`r + e + c + p = Q` e `S = D + R + E` depois de qualquer operação. A reserva expõe `quantity`
(original), `delivered_quantity` (entregas brutas) e `open_quantity` (zero quando não está
`ATIVA`); a listagem de reservas da solicitação também traz `movements`, com
`reversed_quantity` em cada entrega.

**Endpoints.** Todos exigem `Idempotency-Key`, Origin/CSRF em sessões de navegador e
`expected_version` **da solicitação**, como as demais operações da seção 7; cada operação aceita
incrementa essa versão. Reserva ou movimento fora do tenant ou dos centros do usuário responde
`404`; papel sem a ação responde `403` (`require_stock_action`).

| Operação | Rota | Permissão | Resultado |
|---|---|---|---|
| Confirmar entrega | `POST /api/v1/stock/reservations/{id}/deliveries` com `quantity` | `stock:deliver` | `201`, movimento `ENTREGA` |
| Cancelar reserva | `POST /api/v1/stock/reservations/{id}/cancel` com `reason` | `stock:reserve` (seção 9: “reservar, entregar, cancelar reserva”) | `200`, reserva `CANCELADA` |
| Reverter entrega | `POST /api/v1/stock/movements/{id}/reversal` com `quantity` e `reason` | `stock:reverse` | `201`, movimento `REVERSAO` |

Cada transação bloqueia a linha da solicitação (`FOR UPDATE`), depois a reserva, e só então o
`pg_advisory_xact_lock` por tenant, material principal e centro, na mesma ordem da reserva.

- **Entrega:** só reserva `ATIVA` de solicitação `EM_ATENDIMENTO`; recusa com
  `409 QUANTITY_EXCEEDS_RESERVATION` acima da parte aberta. O movimento leva o dataset vigente
  (D4). `R` diminui e `E` aumenta na mesma quantidade, então `D` não muda. A reserva vira
  `CONSUMIDA` quando a parte aberta chega a zero; entrega parcial a mantém `ATIVA` com o
  restante. Depois da entrega, a solicitação passa pelo encerramento único descrito abaixo.
- **Cancelamento de reserva:** só reserva `ATIVA`; libera apenas a parte aberta, registrada como
  `released_quantity` no evento `STOCK_RESERVATION_CANCELLED`, com o motivo. Entregas já feitas
  permanecem, e a solicitação continua em atendimento com o pendente de volta.
- **Reversão:** só de movimento `ENTREGA` (`409 MOVEMENT_NOT_DELIVERY` para uma reversão),
  limitada ao que ainda não foi revertido (`409 QUANTITY_EXCEEDS_REVERSIBLE`). O movimento
  `REVERSAO` aponta a entrega e usa o mesmo dataset dela. Uma entrega de dataset anterior é
  recusada com `409 MOVEMENT_FROM_PREVIOUS_DATASET`, porque o snapshot novo já a incorpora e
  `E` do dataset vigente ficaria negativo; isso fica para a reconciliação da seção 4.4.
  Não há prazo (D5), e o motivo é obrigatório.

**Encerramento único.** `stock_service.close_if_fulfilled` é o único ponto que encerra uma
solicitação por atendimento, chamado depois de cada entrega e de cada aceite de Compras (seção 16).
Segue a seção 5: `EM_ATENDIMENTO` passa a `ENCERRADA` só com `p = 0`, `r = 0` e nenhum
encaminhamento `ENCAMINHADO` aguardando Compras. Então `e + c = Q`, e o motivo é
`ATENDIDA_ESTOQUE` (`e = Q`), `ATENDIDA_PARCIAL_COMPRAS` (`e > 0` e `c > 0`) ou
`ENCAMINHADA_COMPRAS` (`e = 0` e `c = Q`). Assim, entregar 6 e encaminhar 4 de uma solicitação de 10
encerra no aceite de Compras ou na última entrega, o que vier por último. O encerramento é uma
transição própria: incrementa a versão da solicitação e grava `MATERIAL_REQUEST_CLOSED` no
histórico, na mesma transação da operação que o causou.

**Cancelamento da solicitação inteira.** Cancela as reservas `ATIVA` (uma vez cada: só reservas
ainda `ATIVA` mudam, e o cancelamento avulso de uma reserva já cancelada recebe
`409 RESERVATION_NOT_ACTIVE`) e os encaminhamentos `ENCAMINHADO`. O evento de cada reserva registra
`released_quantity`, a parte não entregue; entregas feitas continuam em `e` e `E`.

**Reversão em solicitação encerrada.** É aceita, porque a seção 5 trata a reversão como
operação separada, inclusive após o cancelamento. A solicitação não reabre: continua
`ENCERRADA` com o motivo original, e a quantidade revertida volta ao disponível do centro.
O `pending` dessa solicitação passa a mostrar o que ficou sem atendimento, mas nenhuma operação
nova a atende; o solicitante cria outra solicitação. O evento `STOCK_DELIVERY_REVERSED`
registra o estado da solicitação naquele momento.

**Auditoria.** `STOCK_DELIVERED` e `STOCK_DELIVERY_REVERSED` (entidade `stock_movement`) e
`STOCK_RESERVATION_CANCELLED` (entidade `stock_reservation`) gravam ator, papel efetivo, antes e
depois (reserva ou entrega, parcelas, versão da solicitação, disponível antes e depois) na mesma
transação. A mesma chave com o mesmo conteúdo devolve a resposta original, revalidando tenant e
centro; conteúdo diferente recebe `409 IDEMPOTENCY_CONFLICT`.

**Testes.** `api/tests/test_stock_deliveries.py`, no PostgreSQL, cobre entrega parcial e total,
cancelamento após entrega parcial, reversões parciais e esgotadas, dataset anterior, papéis e
centros, idempotência e CSRF, uma sequência aleatória de operações com encaminhamentos, aceites e devoluções de Compras
(três sementes) que confere `r + e + c + p = Q`, `p ≥ 0`, `D ≥ 0`, `S = D + R + E` e a variação de `D` a cada passo, e duas
entregas concorrentes contra a mesma reserva, o encerramento combinado com Compras nas duas
ordens e o cancelamento da solicitação após entrega parcial.

## 19. Atendimento parcial entre estoque e compras (#242)

Implementa o caminho 3 e a decisão D1. Nenhuma tabela nova nem migração: as parcelas são uma
reserva (`stock_reservations`, seção 14) e um encaminhamento (`purchase_forwards`, seção 16),
ambos ligados à mesma solicitação.

**Quem confirma.** A D1 dá a escolha ao solicitante, e a seção 9 reserva `stock:reserve` ao
Almoxarifado. A decisão adotada: o próprio solicitante confirma a opção (`requests:create`, dono
da solicitação, centro autorizado), e o servidor executa as duas parcelas na mesma transação. A
quantidade reservada não vem do cliente: é sempre `min(D, p)`, calculada dentro do bloqueio.
Isso não concede `stock:reserve`: o solicitante continua recebendo `403` ao reservar uma
quantidade livre e não entrega, não cancela reservas nem reverte entregas. A parcela de estoque
fica na fila normal do Almoxarifado, que entrega ou cancela a reserva como em qualquer outra
(D2, D3). Almoxarifado, Compras e Cadastro recebem `404` ao confirmar a divisão de uma
solicitação alheia.

**Consulta.** `GET /api/v1/material-requests/{id}/fulfillment-options`, só para o dono, devolve as
parcelas atuais (`requested`, `reserved`, `delivered`, `forwarded`, `pending`), o disponível do
centro e as opções com `reserve_quantity` e `forward_quantity`. Com `0 < D < p` as opções são
`PARTIAL` (padrão) e `PURCHASING_ONLY`; com `D = 0`, só `PURCHASING_ONLY`. Quando a divisão não
se aplica, `blocked_reason` traz o mesmo código que a confirmação recusaria (`STOCK_AVAILABLE`,
`NOTHING_PENDING`, `NO_INVENTORY_DATASET`, `RECONCILIATION_REQUIRED`, `STOCK_UNIT_UNRESOLVED`,
`REQUEST_NOT_IN_SERVICE`, `INACTIVE_MATERIAL`, `UNIT_MISMATCH`) e não há opções. A consulta não
bloqueia nem grava nada; selecionar o padrão também não.

**Confirmação.** `POST /api/v1/material-requests/{id}/fulfillment` com `expected_version` e
`option` (`PARTIAL` ou `PURCHASING_ONLY`, obrigatório: a confirmação é sempre explícita) exige
`Idempotency-Key` e Origin/CSRF nas sessões de navegador. A transação usa as mesmas verificações
e a mesma ordem do encaminhamento integral (`purchase_forward_service.locked_shortage`):

1. bloqueia a linha da solicitação e confere dono, versão, estado `EM_ATENDIMENTO`, material
   ativo e unidade;
2. obtém o bloqueio consultivo por tenant, material principal e centro e só então lê `p` e `D`;
3. recusa como a seção 16 quando não há falta confirmada (`D ≥ p` dá `409 STOCK_AVAILABLE`: o
   atendimento integral pelo estoque é a reserva do Almoxarifado, caminho 1);
4. calcula a divisão: em `PARTIAL`, reserva `min(D, p)` e encaminha `p − min(D, p)`; em
   `PURCHASING_ONLY`, encaminha `p` sem reserva;
5. grava a reserva (se houver), o encaminhamento, a auditoria das duas parcelas e um único
   evento da solicitação, e incrementa a versão da solicitação uma vez.

**Recalcular sem duplicar.** Se `D` mudar entre a consulta e a confirmação, vale o `D` lido dentro
do bloqueio: com 6 disponíveis na consulta e outra reserva de 2 confirmada antes, a divisão vira
4 reservados e 6 encaminhados. Se nada restar, `PARTIAL` encaminha tudo sem reserva e o histórico
diz que nada foi reservado; se `D` passar a cobrir `p`, a confirmação é recusada com
`STOCK_AVAILABLE` e nada é gravado. Reserva e encaminhamento somam exatamente `p`, então
`r + e + c ≤ Q` continua valendo, e a reserva concorrente de outra solicitação esbarra no mesmo
bloqueio (`409 INSUFFICIENT_STOCK` quando a divisão chegou antes). O encaminhamento leva a versão
da solicitação anterior à confirmação e continua único por (`material_request_id`,
`request_version`): repetir com a mesma chave devolve a resposta salva; outra chave na mesma
versão recebe `409 VERSION_CONFLICT`; outra opção com a mesma chave, `409 IDEMPOTENCY_CONFLICT`.

**Auditoria.** `STOCK_RESERVED` (entidade `stock_reservation`) registra o papel efetivo do
solicitante, o disponível antes e depois e `origin: REQUESTER_PARTIAL_CONFIRMATION`;
`PURCHASE_FORWARD_CREATED` registra o encaminhamento; a solicitação recebe
`MATERIAL_REQUEST_PARTIAL_FULFILLMENT` (ou `MATERIAL_REQUEST_FORWARDED_TO_PURCHASING` quando nada
foi reservado), com `fulfillment_split` no `after_json`: opção, pendente antes, disponível na
confirmação, quantidades e identificadores das duas parcelas.

**Visível ao solicitante.** O detalhe da solicitação passa a trazer `reserved_quantity`,
`delivered_quantity`, `reservations` (com `quantity`, `delivered_quantity`, `open_quantity` e
estado) ao lado de `forwarded_quantity` e `purchase_forwards`. A resposta da confirmação traz
`reserved_quantity`, `forwarded_quantity`, `available_at_confirmation`, os identificadores das
parcelas e o detalhe atualizado. O encerramento continua único (`close_if_fulfilled`, seção 17):
entregar os 6 e Compras aceitar os 4 encerra com `ATENDIDA_PARCIAL_COMPRAS`, o que vier por último.

**Testes.** `api/tests/test_partial_fulfillment.py`, no PostgreSQL, cobre 10 solicitadas com 6
disponíveis (reserva de 6 e encaminhamento de 4, até o encerramento), consulta sem gravação,
replay e conflitos de idempotência e versão, recálculo quando outra reserva chega antes da
confirmação, `PARTIAL` sem saldo restante, `PURCHASING_ONLY`, recusa com saldo suficiente ou
material não identificado, papéis e CSRF, e uma divisão concorrente com uma reserva avulsa,
aceitando qualquer ordem e conferindo `r + e + c + p = Q` e `S = D + R + E`.

## 19. Confirmação da necessidade no chat (#238)

O chat pede quantidade e unidade em campos explícitos da ficha e mostra o centro autorizado
selecionado para a conversa. Não interpreta medidas, pressão ou referências como quantidade.
O botão “Confirmar solicitação de material” chama
`POST /api/v1/chat/{session_id}/request-material`, com versão da conversa, quantidade decimal,
unidade, CSRF e chave de idempotência. Material, centro, identidade e estado não vêm do navegador.

A API lê a ficha salva e a prova do catálogo, com o mesmo controle de dono, tenant, centros e
versão do chat. Mudanças no catálogo exigem atualizar a conversa antes de confirmar. Os caminhos:

- **Identificado:** identidade verificada ou código ERP explicitamente informado leva a
  `EM_ATENDIMENTO`, com o código ativo. Não cria pedido de cadastro.
- **Inexistente:** PDM completo, busca válida e similares descartados explicitamente levam a
  `AGUARDANDO_CADASTRO`; solicitação, pedido, vínculos, auditoria e idempotência são gravados
  na mesma transação. Qualquer falha desfaz tudo.
- **Inconclusivo:** cria `EM_IDENTIFICACAO`, sem material presumido nem cadastro automático.
  Escolher um produto apenas semelhante não elimina dúvidas técnicas de identidade.

A consulta por código usa a ferramenta MCP de busca, com tenant, estoque autorizado e índice
atual. “Código 16031971” é uma escolha explícita de registro; um número ERP isolado é aceito
somente no início da conversa. A seleção mantém `identity_verified=false` e usa
`EXACT_MATERIAL_CODE`: não é evidência para unificar materiais ou liberar substituições.
A API confirma essa intenção contra a mensagem real do solicitante antes de usá-la.

Uma conversa gera no máximo uma solicitação, também protegida por unicidade no banco. Repetir
com a mesma chave ou com outra chave e os mesmos dados recupera a solicitação; alterar os dados
após confirmar recebe conflito. Depois de confirmar, inicie outra conversa para outro item.
O histórico restaura protocolo e estado; resposta perdida é reconciliada pela leitura da sessão.
Reservas, compras, entregas e publicação permanecem fora desta ação.

A migração de unicidade recusa uma base que já tenha várias solicitações vinculadas à mesma
conversa. Essas duplicações precisam de revisão operacional antes do upgrade; a migração não
apaga nem escolhe solicitações automaticamente.

O aviso de outra necessidade aberta no mesmo material e centro (#248) também se aplica ao chat.
A confirmação inicial responde `409 OPEN_REQUESTS_EXIST` sem gravar. O formulário pede ciência
explícita antes de reenviar com `acknowledge_open_requests: true`; a criação registra essa ciência
na auditoria, sem revelar solicitações fora do escopo.

Após confirmar a necessidade, o chat oferece “Nova solicitação” e “Encerrar”. A primeira
abre uma conversa vazia no mesmo centro, sem reenviar a anterior; a segunda mantém as
mensagens e a ficha em consulta. O histórico restaura o protocolo e oferece as mesmas
escolhas, preservando a solicitação já registrada.

## 20. Acompanhamento pelo solicitante (#245)

O menu **Minhas solicitações** abre `/solicitacoes/`, com lista paginada por protocolo e filtro
pelas quatro etapas. O protocolo abre `/solicitacoes/detalhe/?id=...`, compatível com o export
estático. Ambas as consultas usam `mine=true`: mesmo revisores consultam apenas suas próprias
solicitações nessa jornada. A API continua verificando tenant, centros e permissões em cada leitura.
Trocar a sessão descarta os dados anteriores e cancela consultas pendentes.

O detalhe mostra texto original, centro, etapa, equipe correspondente à etapa, pendência geral,
quantidades solicitada, reservada, entregue, encaminhada e pendente, unidade e histórico real de transições com data e motivo. A equipe é a
referência do fluxo operacional, não uma atribuição individual. Decimais são formatados como
strings para preservar a precisão integral da quantidade persistida.

As parcelas reais vêm do detalhe da solicitação; reserva e encaminhamento aparecem com seus estados.
Encaminhar para Compras não indica compra realizada, recebimento nem entrega. Na ausência de
uma parcela na resposta, ela aparece como **Não informada**, sem presumir zero. Não há registros
nem totais simulados. O modo mock orienta entrar em uma sessão conectada, sem lista fictícia.

## 21. Resolução do cadastro vinculado (#243)

A decisão do cadastro e a continuidade da solicitação compartilham a mesma transação,
com auditoria, controle de versão e a idempotência da decisão existente:

- `REGISTERED`: vincula o código recém-publicado, muda para `EM_ATENDIMENTO` e cria um
  encaminhamento `ENCAMINHADO` para Compras com a quantidade e a unidade confirmadas
  pelo solicitante. Não cria compra, recebimento, reserva nem movimento de estoque.
- `EXISTING`: um único material ativo e com unidade compatível passa a ser o material da
  solicitação. Ela segue em `EM_ATENDIMENTO`, sem encaminhamento automático, pelo fluxo
  normal de consulta de saldo e confirmação do atendimento.
- `REJECTED`: encerra com `CADASTRO_REJEITADO`. O histórico mostra o motivo da decisão
  e orienta criar uma nova solicitação com as correções; a solicitação encerrada não reabre.

Mais de um código possível ou unidade incompatível retorna a necessidade a
`EM_IDENTIFICACAO`, com motivo para revisão de Cadastro, sem escolher um substituto
incerto nem converter a quantidade. Solicitações já encerradas, inclusive canceladas,
são preservadas. O protocolo, o dono, o centro e o texto original não mudam.

O encaminhamento automático registra o revisor que publicou o cadastro como ator,
com o papel efetivo daquela decisão; não se faz passar pelo solicitante. Ele dá
continuidade à necessidade já confirmada, não exige uma nova sessão do dono. Uma falha
na gravação ou na auditoria desfaz material, cadastro, solicitação e encaminhamento juntos.
O histórico existente da solicitação expõe essas transições, sem mudar o contrato da API.
A resolução para material existente também vale quando detectada no envio ou na complementação
do cadastro, além da decisão de Governança ou Fiscal.
