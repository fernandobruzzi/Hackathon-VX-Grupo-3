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

## Tratamento de NCM

O objeto `ncm` e a seção “Tratamento de NCM” apresentam a ausência no original e
no snapshot posterior. Sem snapshot, `missing_after=null`; corrigir a master não
inventa o depois.

O funil conta uma vez cada proposta `NCM_CORRECTION`, nas mesmas restrições de
tenant, dataset e centros do funil geral. Uma proposta com qualquer membro fora do
escopo fica inteiramente de fora. `content` reúne mudanças de código e
`format_only` reúne grafias diferentes de um mesmo NCM válido de oito dígitos no
`ncm_before_assessment.input_ncm` fixado na proposta (no legado sem avaliação,
usa-se o original importado; por exemplo, `73181500` → `7318.15.00`). Estoque em vários centros não
multiplica propostas.

- `created`: propostas registradas no dataset.
- `fiscal_approved`: propostas com decisão fiscal humana auditada.
- `rejected`: propostas cujo estado final é rejeitado, inclusive rejeição técnica.
- `pending`: propostas ainda pendentes e sem decisão fiscal auditada.
- `stale`: propostas desatualizadas.

Os desfechos são exclusivos: rejeição ou desatualização prevalece sobre uma
aprovação fiscal anterior. Aprovação fiscal pendente da técnica fica na coluna
aprovada fiscal. A **precisão operacional** é a proporção de aprovações nas decisões fiscais
registradas, incluindo as duas categorias e contando cada proposta uma vez. `fiscal_approved_decisions` conserva o numerador histórico, mesmo se a proposta
foi depois rejeitada na revisão técnica. A aprovação técnica ou apenas preencher a coluna `fiscal_review_status` não entra
nesse denominador. Sem decisões, `operational_precision=null` e
`fiscal_decided=0`. Essa aceitação operacional não prova acurácia independente.

### Benchmark de desenvolvimento

A tabela expansível exibe o resultado **por família** do benchmark NCM v2:
incorretos/ausentes resolvidos e seu denominador elegível, alterações indevidas e
abstenções. Ela é uma medição global de desenvolvimento congelada, separada das
contagens operacionais do tenant. Não publica os indicadores de avaliação
independente da #113. Os rótulos são documentais, sem revisão fiscal independente.

O artefato `back/pipelines/evaluation_data/ncm_benchmark_v2.json` conserva data,
versões de regras/algoritmos e hashes da entrada e do PDM. Ele é incluído no pacote
Python; o endpoint lê o resultado congelado, sem reexecutar regras ou usar rede.
A medição de 08/11/2026 às 11h18 BRT usou `pdm-ncm-v2`, `aliases_v2@1`,
`rule_based_v1@11-quantity-reference-199` e `head_noun_v2`: **1.228/1.842**
problemas elegíveis resolvidos, **1 alteração indevida** e **605 abstenções**,
preservadas na tela por família. Não remover erros nem reclassificar pendentes
como acertos. Famílias sem problema elegível mostram denominador zero.

Para reproduzir o relatório bruto, a partir de `back/`:

```bash
CLASSIFICATION_REPOSITORY=aliases_v2 EXTRACTION_REPOSITORY=rule_based_v1 CORRECTION_REPOSITORY=head_noun_v2 uv run python -m pipelines.measure_ncm_benchmark ../data/benchmark_ncm/v2 --pdm-workbook ../data/desafio01/03_padrao_cadastro_PDM.xlsx
```

A captura usa a configuração padrão **sem snapshot NCM oficial** e sem auditor
LLM. Uma nova medição deve registrar sua própria data, versões e hashes. Por
família, `resolved` e `eligible_problems` são o numerador/denominador de
`errors_and_missing_resolved`; `improper_changes` e `abstentions` conservam seus
nomes no relatório bruto. Nenhum desses resultados autoriza aplicação fiscal.

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
realizada permanece indisponível: unificar códigos conserva o valor contábil e
não comprova economia. Estimativas ficam indisponíveis sem premissas quantitativas
registradas. A API inclui a interpretação no campo `assumptions` e detalha os
componentes e hipóteses conforme a seção abaixo.

## Validação local

Com Docker Compose ativo, execute na raiz:

```bash
scripts/smoke_test.sh http://localhost:8000 --mode local
```

O smoke confere dados importados, bloqueio da visão financeira para Governança,
acesso do Fiscal e ausência de comparação inventada. Os testes da API verificam
sessões reais, isolamento por tenant/dataset/centro, transições do funil,
preservação do antes, decimais exatos, valores ausentes e o contrato público.
O front usa a API por padrão e trata carregamento, base ausente, erro e repetição.
Somente `NEXT_PUBLIC_DATA_SOURCE=mock` habilita os exemplos, rotulados como simulados.

## Economia com premissas explícitas (#316)

A visão executiva mostra quatro componentes, sempre rotulados como dados
sintéticos do desafio. A visão de qualidade não carrega nem devolve esses valores.

| Componente | Contagem e origem | Valor |
| --- | --- | --- |
| Reutilizações confirmadas | Uma conversa por confirmação explícita de um código existente, pelo botão do chat; evento `CHAT_EXISTING_CONFIRMED` com dataset, centro e código | Contagem × hipótese `registration_cost`, em R$/cadastro |
| Códigos desativados | Membros além do principal que passaram de ATIVO a BLOQUEADO em aplicação auditada de unificação e continuam bloqueados | Contagem × hipótese `code_annual_cost`, em R$/código/ano |
| Revisões em lote | Propostas aplicadas com aprovação técnica auditada em lote, uma vez por proposta | Contagem × (`review_minutes_before` − `review_minutes_after`) / 60 × `hourly_cost` |
| Valor atendido com estoque | Quantidade efetivamente entregue, líquida de reversões, por material, centro e unidade | Quantidade × preço original ajustado pelo fator de consolidação aprovado |

Exibir um semelhante, encontrar saldo ou reservar não comprova atendimento.
Escolher explicitamente um semelhante também registra a confirmação se a API
validar o resultado como existente. Repetir a confirmação do mesmo código,
centro e dataset não insere outro evento. A métrica conta uma conversa uma vez.
O evento fica no log transacional; a listagem de auditoria atual continua limitada
a propostas e pedidos. Não há criação de material, pedido ou reserva por essa ação.

O valor atendido não comprova compra evitada nem economia realizada. Fica
separado da soma de estimativas. Sem preço conhecido e único para o material,
centro e unidade (incluindo fontes consolidadas), o valor fica indisponível;
não se escolhe um preço entre vários nem se trata ausência como zero.
O contador desse componente agrupa atendimentos por material, centro e unidade,
pois somar quantidades de unidades diferentes não é uma contagem válida.

`estimated_savings` soma apenas os componentes estimados disponíveis: operações
observadas no dataset mais um ano hipotético de manutenção dos códigos.
É um cenário parcial com horizontes explícitos, sem extrapolar o volume de
operações para um ano. Capacidade de trabalho não é caixa. `realized_savings`
permanece indisponível. Sem premissa, a contagem continua visível e seu resultado
financeiro permanece indisponível. Valores são calculados com Decimal e
arredondados a centavos por componente antes da soma.

### Registrar e selecionar premissas

O arquivo `api/contracts/fixtures/savings-assumptions.example.json` contém
hipóteses iniciais explícitas. Não define custo anual por código, pois esse valor
não foi validado. Não é ativado automaticamente. Cada hipótese tem valor decimal,
origem e data; unidades são definidas pelas chaves da tabela acima.

Registro local, com o mesmo ObjectStore usado pela API:

```bash
uv run python -m vx_materials_api.savings_assumptions api/contracts/fixtures/savings-assumptions.example.json
```

Com a imagem atualizada e o volume compartilhado do Compose:

```bash
docker compose run --rm --no-deps -T --entrypoint python api -m vx_materials_api.savings_assumptions /dev/stdin < api/contracts/fixtures/savings-assumptions.example.json
```

O comando grava imutavelmente `references/savings/<version>.json`, valida chaves,
decimais não negativos, origem, datas e ausência de duplicação. Repetir os mesmos
bytes é idempotente; outro conteúdo exige versão nova. Depois, configure
`SAVINGS_ASSUMPTIONS_VERSION=pitch-hypotheses-v1` na API e reinicie-a.
A resposta informa versão e SHA-256 dos bytes usados. As hipóteses aparecem ao
lado do componente no painel; os números do pitch devem usar essa mesma versão.

Configuração vazia mantém valores estimados indisponíveis. Referência configurada
ausente, inválida ou inacessível retorna `SAVINGS_ASSUMPTIONS_UNAVAILABLE` na visão
executiva, sem substituir por valores de exemplo. A visão de qualidade continua
independente dessa referência. Tenant, dataset e centros restringem as contagens;
propostas que alcançam um centro não autorizado, inclusive por consolidação,
não contribuem para os componentes baseados em propostas.
