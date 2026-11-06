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
  não é uma amostra rotulada de precisão. A avaliação independente segue na #85.
- **Depois:** `after=null` e `AFTER_SNAPSHOT_NOT_AVAILABLE`. Aplicações registradas
  atualizam o funil, mas não criam um snapshot aprovado. A comparação posterior
  segue na #33.

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
sessões reais, isolamento por tenant/dataset/centro, transições do funil,
preservação do antes, decimais exatos, valores ausentes e o contrato público.
O front usa a API por padrão e trata carregamento, base ausente, erro e repetição.
Somente `NEXT_PUBLIC_DATA_SOURCE=mock` habilita os exemplos, rotulados como simulados.
