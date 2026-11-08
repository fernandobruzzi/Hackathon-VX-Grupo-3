# Dashboard com métricas reais

`GET /api/v1/dashboard/metrics` exige sessão autenticada. `view=quality` (padrão)
exige `metrics:quality`; `view=executive` exige `metrics:financial` e retorna 403
para Governança. O backend confere a matriz de papéis e as permissões da sessão.
Cabeçalhos de papel enviados pelo navegador não concedem acesso.

O dataset padrão é o importado mais recentemente que tenha estoque visível nos
centros autorizados. O parâmetro opcional `dataset_id` permite consultar outro
snapshot importado do mesmo tenant e escopo. Sem dataset visível, a API responde
404 e a tela orienta a importar uma base. Respostas têm `Cache-Control: no-store`.

## Origem das contagens

- **Antes:** registro bruto imutável do estoque original. Cada material conta uma
  vez, mesmo com estoque em vários centros; em registros repetidos, usa-se a
  primeira linha visível. Status, NCM ausente e unidade fora do padrão são lidos
  desses registros, nunca da master corrigida. A checagem de unidade reutiliza o
  normalizador compartilhado selecionado por `NORMALIZATION_REPOSITORY`.
- **Funil:** estados atuais das propostas persistidas `proposal-v1` daquele
  dataset, independentemente do job que as gerou. Propostas com qualquer membro
  sem estoque no dataset ou fora dos centros autorizados ficam de fora. Cada
  proposta conta uma vez; duas aprovações de uma proposta composta não contam
  duas aplicações. Rascunhos antigos incompatíveis não contam como propostas
  revisáveis.
- **Avaliação:** zero pares e precisão/recall indisponíveis até existir uma
  avaliação independente publicada. Aprovação humana de propostas operacionais
  não é uma amostra rotulada de precisão. O [relatório da #85](avaliacao-saneamento.md) é de desenvolvimento e não alimenta
  esses indicadores; sua publicação futura exige a revisão independente da #113.
- **Depois:** vem do snapshot posterior mais recente do dataset. Sem snapshot,
  `after=null` e `AFTER_SNAPSHOT_NOT_AVAILABLE`; aplicações atualizam o funil, mas
  não o depois. Com snapshot, `comparison_status=AVAILABLE`, `after` traz as mesmas
  contagens do antes e `after_snapshot` identifica o snapshot. Mudanças na master
  feitas depois do snapshot só aparecem no próximo.
- **Duplicados:** `duplicate_codes` conta os ativos que unificações pendentes ou
  aplicadas apontam como duplicados, ou seja, os membros além do principal. No
  depois, só os que continuam ativos no snapshot. Unificações rejeitadas ou
  desatualizadas não contam.

## Jornada do solicitante (#250)

O campo `journey` resume as solicitações de material persistidas (seções 13 a 17 de
[solicitacao-material.md](solicitacao-material.md)). Vale para as duas visões, com o mesmo
conteúdo: são contagens e tempos, sem quantidades, preços nem valores. Não depende do dataset:
conta as solicitações do tenant cujo centro de destino está entre os centros autorizados da
sessão, de qualquer solicitante. Solicitações de outros centros não entram em nenhum indicador.

| Campo | Origem |
|---|---|
| `requests_total` | Solicitações no escopo, em qualquer estado |
| `open` | Não encerradas por estado: `EM_IDENTIFICACAO`, `AGUARDANDO_CADASTRO`, `EM_ATENDIMENTO` |
| `closed` | Encerradas por motivo, separando estoque (`ATENDIDA_ESTOQUE`), parcial (`ATENDIDA_PARCIAL_COMPRAS`) e compras (`ENCAMINHADA_COMPRAS`), além de `CANCELADA` e `CADASTRO_REJEITADO` |
| `resolution_time` | Horas entre a criação e o primeiro `MATERIAL_REQUEST_CLOSED` da auditoria, só das solicitações atendidas (os três primeiros motivos). Mediana e percentil 90 pelo posto mais próximo (sempre um tempo observado), com o tamanho da amostra |
| `registration_avoided` | Cadastro evitado: solicitações com encaminhamento para Compras `ENCAMINHADO` ou `ACEITO`, feito com o código existente e sem pedido de cadastro vinculado. Devolvidos e cancelados não contam |
| `identified_under_other_code` | Duplicidade evitada: solicitações vinculadas a uma conversa cuja busca salvou uma correspondência de identidade (`duplicate_check.existing`) que resolve para o material da solicitação, pelo mesmo código ativo ou pelo `active_code_target` de um código bloqueado. Semelhança sem identidade comprovada não conta |

Sem dados, o indicador volta `null` e aparece em `unavailable` com o motivo, nunca como zero
estimado:

- `NO_REQUESTS`: nenhuma solicitação no escopo; vale para todos os indicadores.
- `NO_RESOLVED_REQUESTS`: nenhuma solicitação atendida, então não há tempo até o atendimento.
- `NO_CHAT_LINKED_REQUESTS`: nenhuma solicitação vinculada a conversa, então não há base para
  saber se o item foi identificado sob outro código.

Limites conhecidos: a duplicidade evitada lê a correspondência salva na conversa no momento da
consulta; enquanto a criação de solicitações pelo chat (#238) não registrar a correspondência
na própria solicitação, uma conversa que continuar depois pode mudar esse valor. Pedidos de
cadastro que terminam em `EXISTING` ainda não resolvem a solicitação vinculada (#243) e não
entram no indicador. O encaminhamento para Compras não comprova compra nem recebimento.

Na tela, a seção "Jornada do solicitante" mostra cada indicador; os indisponíveis aparecem
como "Indisponível" com o motivo.

## Snapshot posterior

`POST /api/v1/dashboard/snapshots` exige `batch:run` (Governança), CSRF e
`Idempotency-Key`. Repetir a mesma chave devolve o mesmo snapshot.

1. Lê o estado atual de cada material do dataset (status, NCM e unidade) e o
   compara com o registro importado.
2. Cada campo e valor final diferente precisa corresponder a uma aplicação
   auditada de proposta `APPLIED` do mesmo dataset e material. A autorização é
   específica: revisão fiscal de NCM não autoriza unidade nem estado; bloqueio
   exige a aplicação de uma unificação. Aplicações sucessivas são ordenadas pela
   versão do material: o primeiro valor anterior precisa coincidir com o original
   importado, e os seguintes precisam continuar a cadeia. Uma aprovação sem
   mudança do campo não explica uma diferença anterior sem aprovação.
   Cada proposta aplicada que toca o material precisa ter seu evento de aplicação
   e a transição de revisão correspondente; um evento posterior não encobre o
   início ausente.
   Campo adicional, valor final divergente ou histórico incompleto resulta em
   409 `UNTRACEABLE_CHANGES` com os códigos, antes de gravar snapshot ou exportação.
3. Recalcula o valor do estoque pelas consolidações (quantidade × fator, preço ÷
   fator) e confere que é igual ao original. Saldo sem valor impede a conferência.
4. Grava `exports/{snapshot_id}/quality_snapshot.json` com as propostas aplicadas e,
   para cada material alterado, campos antes e depois e as propostas que explicam
   a mudança. `field_proposal_ids` conserva a cadeia de propostas por campo,
   além da união em `proposal_ids`. As tabelas `quality_snapshots` e `quality_snapshot_items` guardam o
   mesmo estado, sem permissão de UPDATE ou DELETE para a API.
5. Registra `QUALITY_SNAPSHOT_CREATED` na auditoria.

Na tela, a Governança gera o snapshot pelo botão "Gerar snapshot posterior".

## Valores financeiros

A visão executiva soma com precisão decimal os valores contábeis dos snapshots
originais dos centros autorizados. O valor é uma string decimal; se qualquer
saldo não tiver valor, o total fica indisponível, sem tratar ausência como zero.
A visão de qualidade não consulta preços ou valores nem devolve o objeto
`financial`.

Os valores do kit são identificados como **dados sintéticos do desafio**. Economia
realizada e estimada ficam nulas: unificar códigos conserva o valor contábil,
sem comprovar economia, e não há premissas quantitativas registradas para uma
estimativa. A API inclui essas premissas no campo `assumptions`.

## Validação local

Com Docker Compose ativo, execute na raiz:

```bash
scripts/smoke_test.sh http://localhost:8000 --mode local
```

O smoke confere dados importados, bloqueio da visão financeira para Governança,
acesso do Fiscal e ausência de comparação inventada. Os testes da API verificam
sessões reais, isolamento por tenant/dataset/centro, transições do funil, jornada do
solicitante por centro autorizado e indicadores indisponíveis sem dados,
preservação do antes, decimais exatos, valores ausentes e o contrato público.
O front usa a API por padrão e trata carregamento, base ausente, erro e repetição.
Somente `NEXT_PUBLIC_DATA_SOURCE=mock` habilita os exemplos, rotulados como simulados.
