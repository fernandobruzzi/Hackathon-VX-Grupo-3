# Valores técnicos explícitos na extração

A #133 corrige o material real **22825019**: `MATERIAL CORPO: FERRO FUNDIDO`
deixa de preencher `FERRO FUNDIDO NODULAR`. O campo fica ausente e o PDM pede
confirmação. A regra anterior escolhia a única opção do PDM que contivesse todas
as palavras informadas, mesmo que acrescentasse especificações.

A comparação flexível agora exige as mesmas palavras. A ordem pode mudar e as
conversões explícitas já existentes continuam válidas: `CF8M`, `A403 WP316`,
`A105`, grafias compactas e `FEM` por `FEMEA`, por exemplo. Nenhum alias técnico
novo foi acrescentado. Batch, pedidos importados, busca e cartão do chat usam o
mesmo extrator pelo registro `get_extraction_repository`.

## Integração com identidade-v3 e pontuação

A revalidação sobre `5c1211a0b929870f20dbc84f87d2bf7c6399a71e` conserva a decisão
compartilhada `identity-v3` e as regras de pontuação/linhas da #121, usando a revisão de extração
**5**. O mesmo classificador, PDM, regras de
identidade e construtores de propostas são usados nos dois lados; varia somente
o extrator. O [registro da integração](measurements/explicit-values-133-integration-5c.json)
identifica os hashes, os códigos afetados e os resultados das coortes preservadas.

| Medida na base de 23.554 materiais | Antes | Depois |
| ---------------------------------- | ----: | -----: |
| Atributos preenchidos | 73.570 | 73.153 |
| Materiais completos pelo PDM | 10.719 | 10.618 |
| Materiais incompletos pelo PDM | 6.979 | 7.080 |
| Materiais fora do PDM | 5.856 | 5.856 |
| Chaves de identidade disponíveis | 11.655 | 11.554 |
| Propostas MERGE | 978 | 968 |
| Propostas PDM_CORRECTION | 7.243 | 7.167 |
| Propostas UNIT_CORRECTION | 887 | 887 |
| Propostas NCM_CORRECTION | 4.000 | 3.969 |

Continuam sendo **339 materiais com 417 abstenções**, sem atributos adicionados
nem valores trocados. Dez grupos de MERGE e 31 propostas fiscais deixam de ser
gerados; nenhum grupo ou proposta fiscal nova surge. Nos 520 pedidos, atributos
e estados ficam iguais: **256 prontos, 178 incompletos e 86 fora do escopo**.
Esses são estados da análise antes da consulta de duplicidade ao cadastro.
O tratamento de pontuação e linhas já está nos dois lados dessa comparação;
seus ganhos de preenchimento não são atribuídos à exigência de qualificações.

Na coorte fixa da #73, 32 grupos positivos remanescentes passam a 31, mantendo
zero junções erradas conhecidas. O grupo `16490712` / `25536305` fica retido porque
o primeiro informa `ACO ZINCADO`, sem confirmar `CARBONO`. Na amostra adicional de
desenvolvimento da #73, os testes continuam conferindo os grupos retidos por sufixo
de referência não confirmado pela `identity-v3`. Além dessas retiradas, o grupo
`13563770` / `29792424` deixa de ser proposto sem a qualificação `BW` explícita. Os rótulos dessas amostras
permanecem intactos, com a perda de cobertura registrada separadamente.

A coorte histórica original passa de 30/30 para 29/29 entre os grupos decididos;
a coorte histórica após aliases permanece em 30/30. São resultados condicionados
de desenvolvimento, sem precisão populacional ou revisão técnica independente.
Nenhuma coorte, rótulo ou medição anterior é substituído por esta rodada.

O caso de perda de texto `28611241` também permanece registrado: seu terminal
`FEMEA 90 JIC` não confirma `CURVA/GRAUS`. Agora ele fica incompleto antes de gerar
uma correção PDM; os testes distinguem essa abstenção da classificação em nível 3
das propostas completas que ainda perdem informação.

Para reproduzir o comparativo sem escrever no cadastro, na raiz:

```bash
uv run python docs/measurements/explicit-values-133-integration.py --root . --baseline 5c1211a0b929870f20dbc84f87d2bf7c6399a71e --output docs/measurements/explicit-values-133-integration-5c.json
```

## Medição histórica anterior à integração da #73

Comparação preservada contra `b162946086621ef6ec8f65818b68a7c3a3010439`, após a
integração fiscal da #22, com o mesmo PDM, classificador, normalizador e
construtores de propostas. Apenas o extrator varia. A rodada anterior contra
`8f3e40301a06aa905c42a6eb9eeaa832a5d04493` tinha os mesmos resultados de materiais,
pedidos, MERGE, PDM e unidade; a rodada atual acrescenta a medição fiscal.
Os hashes dos arquivos e das duas implementações, os 339 materiais alterados,
os campos retirados e os grupos de MERGE estão no
[registro completo](measurements/explicit-values-133.json).

| Medida na base de 23.554 materiais |  Antes | Depois |
| ---------------------------------- | -----: | -----: |
| Atributos preenchidos              | 73.520 | 73.103 |
| Materiais completos pelo PDM       | 10.688 | 10.587 |
| Materiais incompletos pelo PDM     |  7.010 |  7.111 |
| Materiais fora do PDM              |  5.856 |  5.856 |
| Chaves de identidade disponíveis   | 12.139 | 12.038 |
| Propostas MERGE                    |  1.165 |  1.154 |
| MERGE sem conflito                 |    784 |    779 |
| Propostas PDM_CORRECTION           |  7.202 |  7.126 |
| Propostas de correção de descrição |  6.923 |  6.844 |
| Propostas UNIT_CORRECTION          |    887 |    887 |
| Propostas NCM_CORRECTION           |  3.991 |  3.960 |

**339 materiais mudam; 417 preenchimentos tornam-se abstenções**, sem atributos
novos nem valores trocados. São 101 conexões, 92 materiais de terminais, 73
terminais A, 62 terminais B, 56 materiais de corpo, 28 materiais e cinco materiais
de disco. Onze grupos de MERGE deixam de ser propostos; nenhum grupo novo surge.
O ganho demonstrado é evitar a qualificação sem suporte de 22825019 e dos casos
de regressão. As 417 retiradas **não são 417 erros técnicos confirmados**.

Nos **520 pedidos**, todos os atributos e estados ficam idênticos: 229 prontos
para revisão, 205 incompletos e 86 fora do escopo. Não houve ganhos nem perdas
de preenchimento nesses pedidos. As variações de pontuação da #121 pertencem
ao PR #123 e não foram incorporadas nesta comparação.

Há cobertura retida para revisão: `ENCAIXE SOLDA` sem `SW`, `FERRO NODULAR`
sem `FUNDIDO` e terminais sem direção explícita podem ter equivalências que um
especialista confirme. A unicidade entre opções do PDM não é essa confirmação.
Esses casos ficam pendentes; esta entrega não decide equivalências nem amplia
a tabela de aliases para recuperar contagens.

## Coortes e limites

Nenhuma coorte, rótulo histórico ou relatório anterior da #85 foi alterado.
Na coorte histórica de 40 grupos, um positivo passa a abstenção: a precisão
condicionada dos grupos decididos fica em **34/36**, antes **35/37**. Os dois
erros conhecidos anteriores à #73 e os três grupos inconclusivos continuam
registrados. Essa taxa não é precisão de produção nem revisão independente.

O teste de extração antigo que completava `FEMEA BSP` como `FEMEA RETA BSP`
passou a exigir abstenção: o texto não informa `RETA`. Isso corrige a expectativa
desse teste, sem reescrever rótulos de avaliação técnica ou a história dos grupos.

## Integração fiscal após a #22

Com os mesmos construtores fiscais nos dois lados da comparação, 31 materiais
deixam de gerar `NCM_CORRECTION`, sem propostas fiscais novas. O motivo é a
completude exigida pelo produtor: a extração agora deixa qualificações pendentes
em vez de fornecê-las implicitamente. Os códigos retirados constam no registro
completo, separados dos onze grupos de MERGE retirados.

A regressão usa o material real **11264434**: o original informa `MACHO NPT`
e `FEMEA 45 JIC`. Sem completar `RETO` e `CURVA/GRAUS`, o material não gera
correção fiscal. Quando esses valores são escritos completos, a correção de
grafia do NCM original `4009.2210` para `4009.22.10` continua sendo proposta
com revisão fiscal obrigatória. Nenhuma regra de NCM foi alterada nesta issue.

A decisão para as propostas antigas é **manter para revisão manual explícita**,
sem retirada ou marcação `STALE` automática. A mudança limita novas extrações;
não apaga propostas já persistidas. O mecanismo existente de substituição invalida
uma proposta pendente quando há uma nova do mesmo tipo e membros. Uma proposta
fiscal que deixou de ser gerada não recebe essa substituta automaticamente.

### Localizar e conferir os 31 casos

Na raiz, listar os códigos do relatório, sem alterar o arquivo:

```bash
python - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("docs/measurements/explicit-values-133.json").read_text())
codes = [members[0] for members in report["ncm_correction_materials_removed"]]
print(json.dumps(codes))
PY
```

Em um cliente SQL com parâmetros vinculados, fornecer `:material_codes` como
essa lista de textos e `:tenant_id` / `:dataset_id` como o escopo autorizado.
A consulta somente leitura mostra as propostas **ainda pendentes**, junto ao
texto original e à interpretação persistida. Pode retornar menos de 31 códigos
se propostas não tiverem sido gravadas ou já tiverem uma decisão.

```sql
SELECT p.id AS proposal_id, p.version, m.material_code,
       m.original_description_long AS original_description,
       member->'attributes' AS interpreted_attributes,
       p.changeset->'after'->'attributes' AS proposed_attributes,
       p.changeset->'ncm_assessment' AS fiscal_assessment
FROM sanitization_proposals AS p
CROSS JOIN LATERAL jsonb_array_elements(p.members) AS interpreted(member)
JOIN materials_master AS m ON m.id = (member->>'material_id')::uuid
WHERE p.tenant_id = :tenant_id
  AND m.tenant_id = p.tenant_id
  AND p.changeset->>'dataset_id' = :dataset_id
  AND p.status = 'PENDING'
  AND p.proposal_type = 'NCM_CORRECTION'
  AND m.material_code = ANY(:material_codes)
ORDER BY m.material_code, p.id;
```

A Governança deve conferir o texto e a evidência dos atributos antes de decidir,
sem tomar a interpretação antiga como confirmação. Se faltarem qualificações ou
evidência suficiente, **manter a proposta pendente**; não completar um atributo
para liberar a aprovação. Esta conferência não altera propostas aplicadas,
rejeitadas ou o cadastro e não cria outra tela ou fila.

A atualização obrigatória do **assessment fiscal v2**, na integração da #30,
continua sujeita às verificações de referência e de integridade daquele fluxo.
Quando exigir regeneração do assessment, ela deve ocorrer antes de decidir a
revisão fiscal. Isso é distinto de marcar automaticamente como `STALE` toda
proposta sem substituta, comportamento que esta issue não implementa.

## Índice e verificação

O PR original usou a revisão **`4`**, diferente da revisão `3` proposta no PR #123
de pontuação. A integração sobre `5c1211a0b929870f20dbc84f87d2bf7c6399a71e`,
com a decisão compartilhada `identity-v3` e a pontuação da #121 já na `main`,
usa a revisão **`5`**.
Ela conserva os marcadores de revisão de peça e a extração de modelo de equipamento
da #73, os guardas de sufixo, substantivo, fabricante e atributos da `identity-v3`
e as regras de pontuação/linhas da #121, junto à exigência de qualificações
explícitas da #133. Os resultados
históricos acima permanecem preservados; a medição dessa combinação é separada.

O índice antigo é recusado porque sua assinatura inclui a revisão da extração.
Reconstruir com `docker compose up --build` (serviço `index`) ou:

```bash
docker compose run --rm --build batch
```

As regressões usam a linha original 22825019, valores técnicos incompletos,
valores completos, aliases explícitos, análise de pedidos e o cartão do chat
com MCP real. Para executá-las, de `back/` e depois `mcp/`:

```bash
uv run pytest tests/test_explicit_values.py
```

Para conferir as contagens correntes sem escrever no cadastro, de `back/`:

```bash
uv run vx-back sanitize-report ../data/desafio01/01_base_materiais.csv --pdm-workbook ../data/desafio01/03_padrao_cadastro_PDM.xlsx
```

## Aliases explícitos que dependem de evidência (#158)

A #158 revisou a tabela de aliases explícitos atrás de valores que o texto não
sustenta. A maioria é equivalência direta (`CF8M`, `WCB`, `F316`, `A105` nomeiam
o próprio grau; `VITON` é FKM). Três completariam o valor:

| Alias | Valor do PDM | Por que depende de evidência | Evidência exigida |
| ----- | ------------ | ---------------------------- | ----------------- |
| `ROSCA GROSSA`, `ROSCA FINA` | `METRICA GROSSA`, `METRICA FINA` | O PDM001 também aceita `UNC` e `UNF` | `BITOLA` métrica validada (`M14`, `M6X25`) ou `MA`/`MF` no próprio campo `ROSCA`; bitola em polegada veta o alias |
| `BLINDADO` | `METALICA AMBOS LADOS` | Blindagem pode ser de um lado só | `ZZ` ou `2Z` no texto ou na referência; sufixo `ZZ` também na referência canônica validada (`6004ZZ` → `6004-ZZ`) |
| `EPI BOTINA` | `BOTINA CADARCO` | O PDM071 também tem `BOTINA ELASTICO` | Alias removido |

Sem evidência, o campo fica vazio e a inferência da referência do rolamento não o
substitui por `ABERTO`. Mantidos por equivalência de uso: `OXIDADO` (o único
oxidado do PDM é `OXIDADO PRETO`), `MANOPLA` (`ALAVANCA`), `MINI DISJUNTOR`
(`MINIDISJUNTOR DIN`) e `CARBONO` (`ACO CARBONO`).

Na medição histórica original da #158 (classificador revisão `1`), comparando
material a material com a revisão anterior, só cinco
parafusos mudam: escrevem `ROSCA GROSSA` ou `ROSCA FINA` sem bitola
(29878298, 26323422, 22872566, 14943072 e 19083115) e perdem a rosca. Os cinco
já estavam incompletos por falta de bitola, então nenhuma proposta, unificação
ou correção muda. Os quatro rolamentos `BLINDADO` da base têm `ZZ` e continuam
iguais; `EPI BOTINA` não aparece na base. Nos 520 pedidos nada muda. A medição de
extração continua com 10.883 materiais válidos (46,2%), e a avaliação de
classificação, com 36/36 decisões corretas.

Regressões em `back/tests/test_alias_evidence.py`, com as linhas reais acima e os
casos que precisam continuar reconhecidos.

### Revalidação corrente da integração (#205)

A comparação de desenvolvimento em 2026-11-07 mantém o classificador
`aliases_v1` revisão **2** nos dois processos e compara o extrator revisão **8**
com **9**. O [registro corrente](measurements/alias-evidence-158-current.json)
identifica os hashes dos três arquivos de entrada, das implementações e cada
alteração semântica. Os relatórios e gabaritos históricos permanecem preservados.

| Medida | Antes (8) | Depois (9) |
| ------ | --------: | ---------: |
| Materiais analisados | 23.554 | 23.554 |
| Atributos preenchidos | 74.306 | 74.301 |
| Materiais válidos pelo PDM | 10.927 | 10.927 |
| Materiais incompletos | 7.002 | 7.002 |
| Materiais fora do PDM | 5.625 | 5.625 |
| Chaves de identidade disponíveis | 11.813 | 11.813 |
| Pedidos prontos para revisão | 256 | 256 |
| Pedidos incompletos | 183 | 183 |
| Pedidos fora do escopo | 81 | 81 |

Só os cinco parafusos históricos acima perdem `ROSCA`; continuam incompletos,
sem chave. Nos 520 pedidos não muda atributo, estado nem chave. Os 1.922
atributos e as 256 chaves dos pedidos permanecem iguais. A contagem histórica de
10.883 materiais válidos não representa esta integração. Esta rodada mede
cobertura e diferenças de extração; não mede propostas nem precisão populacional
e não constitui revisão técnica independente.

O guarda usa a bitola já interpretada e validada, com evidência fora de campos
de referência: `PN:M12`, `REF:M12`, `MODELO:M12`, `REF:M1234`, `REF:MA`,
`MODELO:MF` e a referência estruturada não confirmam rosca métrica.
A primeira correção limitava apenas o alias de `ROSCA`; a integração também
filtra cada ocorrência no leitor métrico, antes de preencher `BITOLA` ou
comprimento. Assim, `PN:M12`, `REF:M12` e `MODELO:M12` não fornecem uma bitola
física, mesmo com `ROSCA:METRICA GROSSA` explícita. O código e seu rótulo ficam
no texto não resolvido. `M12` físico sem rótulo e `BITOLA:M12` continuam válidos,
inclusive em `REF:M12 BITOLA M12`, sem consumir o código da referência. Esse filtro
físico adicional não acrescenta diferenças nos 23.554 materiais nem nos 520
pedidos em relação à primeira correção do guarda. `MA` e `MF`
continuam válidos em `ROSCA:ROSCA GROSSA MA` e `ROSCA:ROSCA FINA MF`, sem
emprestar evidência de outro rótulo. Uma bitola explícita em polegadas veta o
alias mesmo com esses marcadores. O rolamento `BLINDADO` com `MODELO:6004ZZ`
ou `6004ZZ/C3` mantém a vedação, enquanto `6004` continua sem vedação e não
recebe `ABERTO` por inferência.

Reproduzir sem alterar os dados, usando dois worktrees com as revisões indicadas:

```bash
.venv/bin/python docs/measurements/alias-evidence-158-current.py --root . --baseline-root /caminho/para/worktree-base --output /tmp/alias-evidence-158-current.json
```
