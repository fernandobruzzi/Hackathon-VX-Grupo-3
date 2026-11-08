# Roteiro alternativo: jornada do solicitante

Versão da #247, em 8/11/2026. O solicitante é o usuário principal, e o cadastro é a capacidade de
apoio. Ela complementa o [roteiro principal](script.md) da #28, que segue sendo o padrão do
hackathon e mantém o recorte do enunciado: reserva e compras entram como ponto de saída. Use esta
versão só depois de ensaiar a jornada no ambiente da apresentação, com as mesmas regras de tempo
e honestidade do roteiro principal.

**Planejado para 4min30s, com 30s de margem dentro dos cinco minutos.** A duração é uma
estimativa textual; nenhuma etapa deste roteiro foi ensaiada por pessoas.

## Regra para cada etapa

Cada etapa demonstrada precisa ter implementação no `homologacao` e um teste que a cubra, listado
na tabela abaixo. O que ainda não foi entregue aparece como próximo passo, nunca como
funcionalidade. Se uma etapa falhar no ensaio, ela sai da fala e vira próximo passo.

| Etapa | Implementado | Teste que cobre | Demonstrar? |
| --- | --- | --- | --- |
| Necessidade no chat, com material, quantidade e centro | #238 | `api/tests/test_chat_material_requests.py`, `front/tests/chat-material-request.test.ts` | Sim |
| Material identificado com saldo visível no centro | #239 | `api/tests/test_stock_reservations.py` | Sim |
| Reserva e entrega pelo Almoxarifado | #239, #240 | `api/tests/test_stock_reservations.py`, `api/tests/test_stock_deliveries.py` | Sim, com a sessão do Almoxarifado |
| Sem saldo: equivalente autorizado, com confirmação | #246 | `api/tests/test_material_equivalences.py` | Sim, se houver equivalência aprovada no ensaio |
| Sem saldo: encaminhamento para compras (integral ou parcial) | #241, #242 | `api/tests/test_purchase_forwards.py`, `api/tests/test_partial_fulfillment.py` | Sim |
| Acompanhamento pelo protocolo e notificações | #245, #249 | `front/tests/request-tracking.test.ts`, `api/tests/test_notifications.py` | Sim |
| Pedido ao fornecedor, recebimento e entrega pela compra | Fora do MVP (D7) | — | Não: próximo passo |
| Transferência entre centros | Informativa no MVP (D6, #251) | — | Não: próximo passo |
| Cadastro novo publicado seguindo para compras | #243, pós-hackathon | — | Não: próximo passo |
| Indicadores da jornada no dashboard | #250, pós-hackathon | — | Não: próximo passo |

## Tempo e operação

| Janela | Duração | Assunto | Operação planejada |
| --- | --- | --- | --- |
| 00:00–00:25 | 25s | Problema | Pessoa da manutenção precisa de uma peça e não sabe se ela existe |
| 00:25–01:15 | 50s | Pedido no chat | Pedido em linguagem natural; o motor pede o campo faltante; a busca acha o item cadastrado |
| 01:15–02:05 | 50s | Com saldo | Solicitação criada com protocolo; Almoxarifado reserva e confirma a entrega |
| 02:05–02:50 | 45s | Sem saldo | Equivalente autorizado com confirmação, ou encaminhamento para compras com o mesmo protocolo |
| 02:50–03:15 | 25s | Acompanhamento | Notificação no menu e histórico da solicitação |
| 03:15–03:50 | 35s | Impacto hipotético | Três linhas de valor separadas, rotuladas como hipótese |
| 03:50–04:30 | 40s | Cadastro como apoio e fechamento | Saneamento da base sustenta a busca; próximos passos |
| 04:30–05:00 | 30s | Margem | Troca de tela ou latência; sem conteúdo novo |

## Fala principal

### 00:00 — O problema

> A pessoa da manutenção precisa de uma peça hoje. Ela não sabe se a peça já existe no
> almoxarifado, com que código, nem se há outra equivalente. Quando não acha, pede um cadastro
> novo ou uma compra, e o estoque parado continua invisível.

### 00:25 — Pedido no chat

> Ela descreve a necessidade com as próprias palavras. O motor usa o padrão de materiais para
> pedir o que falta e procura o item já cadastrado antes de qualquer cadastro novo.

### 01:15 — Com saldo

> O item existe e tem saldo neste centro. A solicitação ganha um protocolo. O Almoxarifado
> reserva e confirma a entrega, e o saldo importado nunca é alterado: cada movimento fica
> registrado e auditado.

### 02:05 — Sem saldo

> Quando falta saldo, só aparecem equivalentes que a Governança aprovou. Um produto parecido não
> basta, e a troca exige a confirmação do solicitante. Sem equivalente, a demanda segue para
> Compras com o mesmo protocolo. Isso registra a demanda; ainda não é compra nem recebimento.

### 02:50 — Acompanhamento

> O solicitante acompanha tudo pelo protocolo e recebe uma notificação a cada mudança de etapa
> feita pelas equipes.

### 03:15 — Impacto como hipótese

> Separamos três valores possíveis: estoque reaproveitado, cadastro duplicado evitado e compra
> evitada. Nenhum deles foi medido em um cliente. As fórmulas e premissas estão no material de
> apoio, e um piloto precisa comprovar cada um sem contar a mesma peça duas vezes.

### 03:50 — Cadastro como apoio e fechamento

> Por trás da busca está o saneamento da base: em 8 de novembro, o lote local analisou os 23.554
> registros do kit e gerou propostas revisadas por pessoas. Os próximos passos são o pedido ao
> fornecedor, a transferência entre centros e a medição num piloto.

## Perguntas prováveis da banca

- **A compra foi feita?** Não. O encaminhamento registra a demanda para Compras; pedido ao
  fornecedor e recebimento estão fora do MVP (D7).
- **O equivalente une os materiais?** Não. Os códigos e os saldos continuam separados; a troca
  só vale com equivalência aprovada e confirmação do solicitante.
- **Quanto se economiza?** Não foi medido. As três linhas de valor estão nas
  [premissas de ROI](roi-assumptions.md#6-jornada-do-solicitante-três-linhas-de-valor) como hipótese.
