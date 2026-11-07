# Consistência de NCM pelo PDM

A função `domain.ncm_rules.check_ncm_consistency` e a tool MCP de mesmo nome
avaliam o formato do NCM e a coerência com `NCM_REFERENCIA` do PDM. Não escrevem
no cadastro, não concedem aprovação e não substituem o Auditor fiscal.

Exemplo da tool:

```json
{
  "pdm_class_id": "PDM003",
  "attributes": {"TIPO": "SEXTAVADA", "BITOLA": "M16"},
  "ncm": "7318.15.00",
  "pdm_version": "pdm-kit-v1"
}
```

O resultado é `INCONSISTENT`, sugere `7318.16.00` e exige revisão fiscal.
NCM vazio ou malformado mantém o original e recebe `UNDETERMINED`. Uma mudança
de formatação também exige revisão se for persistida. `CONSISTENT` significa
somente concordância com o PDM, sem confirmar a tabela oficial.

As 11 classes com múltiplos códigos usam condições explícitas: material e reforço
de mangueiras; comprimento externo de correias; material de juntas; substantivo,
material e conexão de conexões; material, costura e diâmetro de tubos; material
de luvas; biqueira; tipo de disco; substantivo de filtros; aplicação e exceções
por substantivo em sobressalentes. Informe `item_name` quando houver vários nomes.
Falta de informação, valores não previstos e regras alteradas deixam a decisão
pendente. Não se deduz circunferência de uma referência comercial de correia.

O resultado registra versão e hash do PDM, aba de origem, versão do avaliador e
`evaluation_hash`, calculado sobre classe, atributos, substantivo, NCM original
e versões. Mudar esses dados exige nova avaliação. As regras condicionais são
vinculadas ao hash de seu texto de referência; uma atualização exige revisão.

## Referência adotada e limites

Sem o snapshot oficial da #30, `exists_in_snapshot` e `valid_in_snapshot` são
`null`, com `OFFICIAL_SNAPSHOT_UNAVAILABLE`. Informar `ncm_version` é recusado,
pois essa versão não foi carregada. O PDM não é apresentado como tabela oficial.

## Do batch às revisões

`sanitize-report` inclui `NCM_CORRECTION` nas contagens de correções. `sanitize`
persiste essas propostas pelo mesmo contrato `proposal-v1`, inclusive nos jobs
retomáveis. Recebem proposta materiais em qualquer status cuja classe vem do nome
que abre a descrição, por extenso ou abreviado sem ambiguidade (`aliases_v2`). Só os
atributos que decidem o código são exigidos. Condição não resolvida ou vários códigos
possíveis não são escolhidos por suposição.

Propor é mais restrito que a coerência, que segue o PDM ao pé da letra e continua igual
no chat e na aprovação (`ncm_proposal_blockers`, política `ncm-proposal-v1`):

- A posição do NCM depende da matéria (cap. 73 é ferro/aço; 4016, borracha vulcanizada).
  O código único da classe só é proposto com `MATERIAL` ou `CLASSE RESISTENCIA` admitidos
  pelo PDM. Classe de resistência de fixador (8.8, SAE GRAU 5, A2-70) só existe para aço.
  Parafuso sem material nem classe e O-ring sem elastômero ficam sem proposta.
- Anel ou vedação de sobressalente (`PDM110`) pode ser junta, artefato de borracha ou parte
  de máquina: o equipamento de aplicação não decide sem material e desenho, e o item vai
  para revisão manual.

A aprovação de uma `NCM_CORRECTION` grava só o NCM, inclusive em material bloqueado ou
obsoleto. Classe, atributos, descrição, identidade e canonicidade não mudam por ela.

O original permanece no membro e em `changes.before`; `changes.after` traz o
código proposto. `ncm_before_assessment` e `ncm_assessment` registram as avaliações,
origem, versão, hash e atributos, vinculados ao hash da proposta. A proposta exige
revisão fiscal e técnica: a interpretação PDM que sustenta o NCM também deve ser
conferida. O batch não aprova, altera cadastros nem muda os snapshots originais.

Na interface, entre como Governança e abra Saneamento para a revisão técnica.
Depois entre como Fiscal: a fila abre na área fiscal. O detalhe diferencia formato,
coerência e existência/vigência desconhecidas, e mostra a origem e versão do PDM.
As decisões continuam no endpoint da #20, com sessão, RBAC, escopo, justificativa,
versão observada e idempotência. O estado só passa a `APPLIED` com todas as
revisões exigidas aprovadas, em qualquer ordem.

A API reavalia classe, nome, atributos e NCM antes de cada aprovação. Um código
da união de referências da classe não basta se sua condição é incompatível.
Alterar uma base fiscal sem renovar a avaliação retorna `NCM_ASSESSMENT_CHANGED`.
Mudanças de conteúdo após uma primeira decisão também invalidam o vínculo da
aprovação anterior; é necessário gerar outra proposta e revisar novamente.
Propostas legadas sem avaliação armazenada são conferidas pelo mesmo motor,
preservando o vínculo existente do hash aos atributos e à referência PDM.
Cada evento de aprovação registra a avaliação efetivamente conferida na auditoria.

## Benchmark documental

`data/benchmark_ncm/v1` traz 6.271 parafusos, válvulas e anéis com gabarito documental.
O avaliador lê só a base sem gabarito para gerar as propostas e une o gabarito depois,
por `ID_BENCHMARK`. Do diretório `back/`:

```bash
uv run python -m pipelines.measure_ncm_benchmark ../data/benchmark_ncm/v1 --pdm-workbook ../data/desafio01/03_padrao_cadastro_PDM.xlsx
```

O relatório separa, por família, preservação dos corretos, correção dos incorretos,
preenchimento dos ausentes, acurácia balanceada, precisão das propostas, alterações
indevidas, propostas só de formato, abstenções e encaminhamento dos pendentes. Outra
família ou versão com as mesmas colunas usa o mesmo avaliador. Os rótulos são documentais,
sem revisão humana independente: a medição é de desenvolvimento e não autoriza aplicar
nada.

Medição em 7/11/2026 (`aliases_v2@1`, `head_noun_v2`, política `ncm-proposal-v1`):

| Família   | Erros e ausências resolvidos | Acurácia balanceada | Precisão das propostas | Alterações indevidas | Pendentes encaminhados |
| --------- | ---------------------------- | ------------------- | ---------------------- | -------------------- | ---------------------- |
| Anéis     | 98/111                       | 91,8%               | 343/343                | 0                    | 346/346                |
| Parafusos | 416/421                      | 99,3%               | 1628/1628              | 0                    | 17/17                  |
| Válvulas  | 163/163                      | 100%                | 583/583                | 0                    | —                      |
| Total     | 677/695 (97,4%)              | 98,2%               | 2554/2554              | 0                    | 363/363                |

Antes destas regras, o mesmo avaliador resolvia 158/695 (22,7%), com acurácia balanceada
de 59,3%. Manter o cadastro já acerta 88,24% dos pontuáveis, por isso a acurácia simples
não é a métrica de referência. Das 2.554 propostas, 1.877 só mudam a grafia do código
(`73181500` para `7318.15.00`) e também passam pela revisão fiscal. Os 18 restantes são
anéis retentores escritos como `ANEL RETENTOR`, materiais por extenso fora do PDM
(`ETILENO PROPILENO`) e um erro de digitação no nome (`PAARAFUSO`).

## Reprodução local

Do diretório `back/`, sem banco, AWS ou credenciais:

```bash
uv run vx-back sanitize-report ../data/desafio01/01_base_materiais.csv --pdm-workbook ../data/desafio01/03_padrao_cadastro_PDM.xlsx
```

Com o Compose e as três contas locais configurados conforme
[`aprovacoes.md`](aprovacoes.md), execute `docker compose run --rm --build batch`
para popular a fila. Os números são propostas, não mudanças aplicadas nem ganhos.

Verificação: `uv run pytest` em `back/`, `mcp/` e `api/`; configure o PostgreSQL
de teste para verificar o ciclo completo. Os testes da API exercitam a proposta
da porca produzida pelo batch, ambas as ordens de revisão, ausência de autorização
fiscal, atributo alterado e avaliação na auditoria. A ferramenta MCP é chamada
pelo protocolo stdio real, sem AWS e sem credencial de escrita no cadastro.
