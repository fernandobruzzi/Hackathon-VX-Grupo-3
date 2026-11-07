# Classificação de materiais e pedidos

A classificação sugere uma das 44 classes do PDM sem alterar o mestre. Batch e
chat podem usar `ClassificationInput` e `ClassificationRepository` do domínio.
O repositório recebe o catálogo compilado pelo loader existente.

```python
from domain.contracts import ClassificationInput
from domain.pdm_loader import load_pdm
from repositories.classification import get_classification_repository

catalog = load_pdm("data/desafio01/03_padrao_cadastro_PDM.xlsx")
repository = get_classification_repository(catalog)
result = repository.classify(
    ClassificationInput(
        description="Preciso de válvula de esfera 2POL",
        merchandise_group="VAL01",
    )
)
# result.pdm_class_id == "PDM040"
```

## Regras da primeira implementação

`rule_based_v1` usa os nomes completos de `item_names` do PDM e limites de palavras.
Ignora caixa, acentos, separadores e as preposições DA/DAS/DE/DO/DOS. Não expande
abreviações técnicas nem interpreta inglês.

`aliases_v1`, o padrão, aplica as mesmas regras depois de trocar aliases técnicos
inequívocos pela forma do PDM (seção [Aliases técnicos](#aliases-técnicos)).

Os três textos — descrição longa, curta e anexo — são considerados. O nome mais
específico prevalece quando os trechos se sobrepõem: PARAFUSO SEXTAVADO INTERNO
não vira PARAFUSO SEXTAVADO. Classes diferentes em trechos distintos ou em fontes
contraditórias ficam sem decisão. Rótulos de atributos como `DIAMETRO EIXO:` e
`REVESTIMENTO:` não são confundidos com produtos; o texto original é preservado.

Nomes genéricos compartilhados (`LUVA`, `BUCHA`) e palavras muito curtas (`TE`,
`CAP`) exigem apoio do grupo da classe. O grupo nunca basta sozinho. Um nome
completo inequívoco pode contrariar o grupo legado, registrando `group.mismatch`:
isso permite identificar correções futuras do grupo, sem aplicá-las agora.

| Estado         | Significado                                                            |
| -------------- | ---------------------------------------------------------------------- |
| `CLASSIFIED`   | Uma classe com evidência suficiente; `pdm_class_id` preenchido         |
| `UNRESOLVED`   | Texto ausente, nome incompleto, ambiguidade ou conflito; classe nula   |
| `OUT_OF_SCOPE` | Nenhum nome ou família reconhecido por esta implementação; classe nula |

`OUT_OF_SCOPE` é o resultado do classificador, não uma comprovação de que o produto
está fora do negócio. Abreviações e traduções também podem cair nesse estado.
Consumidores devem manter esses itens para revisão ou outra implementação, sem
rejeitar um pedido automaticamente. `candidate_class_ids` ajuda a revisão de
casos incompletos, mas não autoriza cadastro ou unificação.

Cada resultado carrega a entrada original, regra versionada, candidatos,
evidências por campo, versão e SHA-256 do PDM. O relatório acrescenta identificador
e posição lógica do registro de origem e hash do CSV. Códigos repetidos não são
descartados. Não há score de confiança nem chamada externa.

## Aliases técnicos

`aliases_v1` troca sequências exatas de palavras antes da busca dos nomes. O contexto faz
parte do padrão, e a tabela fica em `repositories/classification/aliases_v1_tables.py`:

| Alias                     | Vira             | Por quê                                                                        |
| ------------------------- | ---------------- | ------------------------------------------------------------------------------ |
| `VALV ESF`, `VALVULA ESF` | `VALVULA ESFERA` | ESF só é esfera logo depois de válvula                                         |
| `VALV`                    | `VALVULA`        | O tipo (GLOBO, GAVETA...) continua decidindo a classe                          |
| `ELEMENTO FILTRANTE`      | `FILTRO`         | Com o tipo (AR, OLEO...) vira o filtro; sem ele, fica em dúvida                |
| `FILT`                    | `FILTRO`         | As 95 ocorrências da base são filtros; sem o tipo completo, fica em dúvida     |
| `RET` no começo do campo  | `RETENTOR`       | As 57 descrições que começam com RET são retentores; depois de VALV é retenção |
| `CONT` no começo do campo | `CONTATOR`       | Abre as 28 descrições de contatores; no meio do texto é corte de outra palavra |
| `LAMP LED`                | `LAMPADA LED`    | Todas as 28 ocorrências são lâmpadas LED                                       |
| `O RING` sem `ANEL` antes | `ANEL O RING`    | O nome do PDM é ANEL O-RING; 89 descrições escrevem só O-RING                  |
| `BALL VALVE`              | `VALVULA ESFERA` | Linhas de catálogo em inglês nos anexos dos pedidos                            |

Cada alias usado vira uma evidência com o trecho como foi escrito e a regra
`aliases_v1/alias.<id>`; o texto original continua em `original`. Os aliases não
preenchem atributos: a extração lê o texto original, então `VALV ESF 2" AISI 316 NPT`
vira válvula esfera de 2POL com rosca NPT, e o material do corpo fica vazio, porque
AISI 316 não diz se é forjado ou fundido.

Não entram na tabela: ESF fora de válvula (`ROL RIG ESF`), `ELEMENTO` sozinho,
abreviações que dependem do item, como `PARAF CAB SEXTAVADA ALLEN` ou `VALV RET`, e
sinônimos, como `VERGALHAO TENSORA` (`VERGALHAO ROSCADO` é outra peça). Esses
textos continuam sem classe ou em dúvida. No chat, uma classificação em dúvida não é
rejeição: o pedido fica aguardando resposta e, com até oito nomes possíveis, o agente
pergunta qual deles é o item (`ELEMENTO FILTRANTE FLEETGUARD LF9009` lista os cinco filtros).

Efeito na base de materiais, comparado ao `rule_based_v1`:

- 579 materiais passam a ter classe, todos válvulas e filtros do tipo descrito.
- 24 elementos filtrantes de óleo deixam de ser classificados como `OLEO LUBRIFICANTE`.
- 44 válvulas que viravam `FLANGE` ou peça de reposição (`PISTAO`) ficam em dúvida.
- Unificações: de 1.147 para 1.165 grupos. A amostra de precisão foi sorteada e revisada
  de novo: 39 de 40, e o erro é o caso PETRONAS/MOBIL da #73.
- Na medição inicial da revisão 1, a amostra ficou em 36/36: nenhuma linha dela usava esses aliases, e as
  linhas reais dos aliases estão em `tests/test_classification_aliases.py`.

Abreviações da #204 (revisão 2 do `aliases_v1`), comparadas com a revisão 1:

- Gabarito de classificação: de 36 para 43 classificados, todos corretos; falsos "fora do
  escopo" de 8 para 1 (`VERGALHAO TENSORA`, que fica para revisão humana).
- Base: 290 materiais mudam de status ou classe; outros 11 mudam apenas as classes candidatas. 235 deixam de ser "fora do escopo" (anel O-ring, filtro,
  retentor, contator e lâmpada LED), 23 filtros de óleo deixam de ser `OLEO LUBRIFICANTE`, e
  18 retentores com `EIXO:` deixam de ser a peça `EIXO` e ficam em dúvida.
- Pedidos: 5 dos 520 deixam de ser "fora do escopo" (3 anéis O-ring e 2 válvulas esfera).
- Unificações: de 976 para 998 grupos. São 28 composições novas: 22 grupos novos e
  6 ampliações que substituem 6 grupos anteriores. Os membros acrescentados são de
  itens agora classificados, com mesmo fabricante e referência ou mesmos atributos.

Mudar a tabela ou a revisão do repositório muda a versão do índice de busca. Reconstrua o
índice antes de usar o chat: `docker compose up --build` faz isso pelo serviço `index`.

## Executar localmente

De `back/`, os comandos abaixo escrevem JSON no stdout. O relatório contém uma
entrada por registro, além das contagens; redirecione para um arquivo se necessário.

```bash
uv run vx-back classification-report ../data/desafio01/01_base_materiais.csv \
  --input-kind materials \
  --pdm-workbook ../data/desafio01/03_padrao_cadastro_PDM.xlsx

uv run vx-back classification-report ../data/desafio01/02_pedidos_cadastro.csv \
  --input-kind orders \
  --pdm-workbook ../data/desafio01/03_padrao_cadastro_PDM.xlsx

uv run vx-back classification-evaluate tests/fixtures/classification_review.json \
  --pdm-workbook ../data/desafio01/03_padrao_cadastro_PDM.xlsx

uv run pytest
```

Sem uv instalado na máquina, a avaliação também roda no container batch, da raiz,
sem iniciar banco, API ou AWS:

```bash
docker compose --profile batch run --build --rm --no-deps \
  -v ./data:/data:ro batch \
  vx-back classification-evaluate /app/back/tests/fixtures/classification_review.json \
  --pdm-workbook /data/desafio01/03_padrao_cadastro_PDM.xlsx
```

## Avaliação reproduzível e limites

A amostra versionada tem 55 registros reais do kit, com rótulos atribuídos por
inspeção das descrições e confronto com o PDM, sem derivá-los do grupo ou das
previsões. A seleção contém os dois primeiros materiais de cada grupo ERP,
os primeiros 20 pedidos e cinco pedidos negativos (cadeira, toner, notebook,
café e água). Os testes conferem os textos contra os arquivos originais.

É uma amostra de desenvolvimento: a inspeção também identificou regressões
cobertas pelos testes. Não é um conjunto de teste independente, revisão de
especialista ou estimativa de acurácia de toda a base.

Resultado com `pdm-kit-v1`, SHA-256
`33820f96f0e2a6742bcbf2f9552bd18666f6898ff027d36a4ddc68ee313d6a5b`:

- Precisão das classes atribuídas na amostra: **36/36 (100%)**.
- Cobertura da amostra: **36/55 (65,45%)**; recuperação dos 50 itens em escopo: **72%**.
- Dos cinco negativos, quatro saem como `OUT_OF_SCOPE` e um como `UNRESOLVED`.
- Oito itens realmente em escopo ficam como `OUT_OF_SCOPE`, principalmente por
  abreviações/tradução. Esses falsos negativos aparecem em `false_out_of_scope`.

Execução integral com `aliases_v1`, sem usar rótulos inferidos como verdade. Entre
parênteses, o `rule_based_v1` quando difere:

| Entrada   | Registros |      Com classe | Ambíguos/incompletos | Sem correspondência |
| --------- | --------: | --------------: | -------------------: | ------------------: |
| Materiais |    23.554 | 17.698 (17.347) |        3.480 (3.485) |       2.376 (2.722) |
| Pedidos   |       520 |             434 |                   24 |                  62 |

As contagens integrais medem cobertura, não precisão. O avaliador retorna precisão
nula quando não há previsões, em vez de inventar 100%. Nenhuma dessas métricas
autoriza unificação, publicação ou mudança fiscal.

## Trocar o algoritmo

Implemente o protocolo em um novo módulo de `repositories/classification`, registre
uma fábrica em `REPOSITORIES` e selecione com `CLASSIFICATION_REPOSITORY`. O nome
explícito (`--repository` no CLI) tem precedência sobre a variável de ambiente.
Não remova a implementação anterior. Os testes de contrato usam todas as fábricas
registradas e conferem as 44 classes, rastreabilidade, abstenção e casos ambíguos.

A comparação foi repetida na integração com o extrator na revisão 8, preservando
os hashes da base, pedidos, PDM e gabarito. O gabarito de desenvolvimento ficou
em 36/36 e 43/43 decisões classificadas, respectivamente; isso não é homologação
independente nem precisão da base inteira. As 301 mudanças de materiais, cinco
de pedidos e 28 composições de grupos estão identificadas na
[medição da integração](measurements/classifier-abbreviations-rebase-204.json),
com decisões anteriores/posteriores, versões e hashes. Rótulos históricos foram
preservados; a medição não autoriza unificação de materiais.
