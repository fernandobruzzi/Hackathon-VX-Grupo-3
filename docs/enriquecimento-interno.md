# Enriquecimento interno e completude da base

O saneamento `SANITIZE` inclui diagnóstico PDM e enriquecimento com evidência dos
arquivos originais do dataset. O fluxo é: analisar dados atuais → medir lacunas →
cruzar fontes com identidade confirmada → registrar evidências e propostas →
revisar em Enriquecimento → aplicar pela API com auditoria → executar novo batch.
Sugestões não são aplicações. Apenas a aprovação altera o cadastro.

## Fontes e critérios

- `03_padrao_cadastro_PDM.xlsx`: define atributos, condições, formatos e valores
  permitidos. Não comprova um valor de produto apenas porque ele consta da lista.
- `01_base_materiais.csv`: oferece atributos presentes em outros registros ativos
  do mesmo item. O próprio registro não é usado como sua fonte de enriquecimento.
- `02_pedidos_cadastro.csv`: texto do pedido e `CONTEUDO_ANEXO` fornecem evidência
  interna. Dos 520 pedidos, 136 têm anexos textuais: 107 fichas e 29 catálogos.
  Pedido é fonte documental, sem virar material nem pedido aprovado automaticamente.

As fontes são indexadas pela identidade e cada par é confirmado por
`decide_identity`, incluindo classe, nome do item, fabricante, referência/sufixo
ou atributos técnicos obrigatórios. Não se presume um obrigatório ausente em
classe técnica a partir de uma descrição parecida. Nas classes por referência,
um fabricante e part number genuínos podem comprovar identidade mesmo faltando
aplicação ou modelo do equipamento; isso permite recuperar esses campos.

Diferenças conhecidas, inclusive opcionais, impedem aproveitar os demais valores
daquela fonte. Valores divergentes entre fontes ficam retidos, sem escolher um
vencedor. Campos conhecidos não são substituídos. A sugestão é revalidada no PDM,
incluindo aplicabilidade condicional. Atributos com condição ainda desconhecida
são listados separadamente, sem contá-los como opcionais dispensáveis.

Observações independentes de cada fonte e do alvo são reextraídas pelos mesmos
rótulos e aliases do extrator. Dois part numbers, fabricantes ou valores
contraditórios impedem o preenchimento, inclusive dentro de um único anexo.
Descrição longa, curta e campos estruturados são lidos separadamente. A curta
com 40 ou mais caracteres perde a cauda possivelmente cortada e não comprova
referências livres. Valores discordantes ficam para revisão, sem precedência
silenciosa de um campo. As novas regras têm revisão própria nas assinaturas.

Cada evidência registra arquivo, identificador, trecho, SHA-256 do original, chave
no armazenamento, data da primeira observação dos mesmos arquivos e fundamento
da confiança. `MEDIUM` indica
evidência interna com identidade confirmada; não é uma probabilidade de acerto.
A referência `dataset://.../arquivo#registro` identifica o documento interno e não
faz uma consulta de internet. O trecho aparece na tela existente de evidências.

## Operação

Diagnóstico reproduzível, sem banco, rede ou alteração dos dados, a partir da raiz:

```bash
uv run --locked vx-back enrichment-report --data-dir data/desafio01 > /tmp/enriquecimento.json
```

O JSON inclui resultados por material, obrigatórios faltantes, inválidos,
condicionais pendentes, opcionais ausentes, sugestões, fontes rejeitadas e
comparação antes/depois das sugestões. `VALID` mede atributos PDM, sem certificar
vigência NCM, unidade de embalagem, estoque, precisão do classificador ou cadastro
pronto para produção.

O diagnóstico distingue `UNRESOLVED` de `OUT_OF_SCOPE`, candidatos de classe,
conflitos no próprio registro e entre fontes. Cada lacuna informa uma pergunta
PDM e sua causa: identidade não confirmada, rótulo não interpretado, evidência
insuficiente, condição desconhecida ou valor inválido. Evidência insuficiente
não afirma que o atributo inexiste no mundo real. Fontes sem identidade utilizável
continuam rastreáveis em `unusable_sources`. As pendências exibem essas questões.

### Acrescentar documentos internos

Use um bundle JSON, fornecido pela equipe responsável pelos dados. Exemplo:

```json
{
  "schema_version": "internal-documents-v1",
  "dataset_id": "UUID_DO_DATASET",
  "documents": [{
    "id": "ficha-001",
    "title": "Ficha técnica conferida",
    "kind": "INTERNAL_DOCUMENT",
    "text": "FILTRO OLEO LUBRIFICANTE; FABRICANTE: ...; REFERENCIA FABRICANTE: ...; ALTURA: 100MM"
  }]
}
```

Campos opcionais do documento: `short_description`, `manufacturer` e
`manufacturer_reference`. Não são aceitos campos desconhecidos, IDs duplicados,
outro dataset, fonte externa, proposta pendente ou autodeclaração de aprovação.
Limites: 2 MB, 500 documentos e 20 mil caracteres por texto. Não há busca de URLs.

```bash
uv run --locked vx-back register-internal-sources fichas.json --dataset-id UUID_DO_DATASET
```

Configure `ENRICHMENT_INTERNAL_SOURCES_KEY` com a chave retornada, no mesmo
armazenamento da API e batch. O conteúdo é arquivado em
`references/internal-sources/<dataset>/<sha256>.json`. O batch recusa troca das
fontes na retomada; abra um novo job. A API reabre o documento, confere bytes,
trecho, valor, identidade e dataset antes de aprovar. Propostas pendentes nunca
são lidas como fontes. Datas da primeira observação dos originais e dos bundles
são preservadas separadamente; documentos sem relação não duplicam propostas.

Para ensaio sem banco, use `dataset_id: "kit"` no bundle e acrescente
`--internal-documents fichas.json` ao comando `enrichment-report`.

### Leitura assistida opcional

O batch padrão continua com zero chamadas de modelo. O piloto Bedrock exige
`ENRICHMENT_LLM_MODEL_ID` e `ENRICHMENT_LLM_MAX_CALLS` positivo (máximo 100 por job).
O orçamento é reservado no checkpoint antes da chamada e preservado na retomada;
trocar modelo, prompt ou orçamento exige novo job. Há limites de texto, tokens,
tempo e nenhuma repetição automática de chamada.

O modelo só lê campos do registro para atributos ausentes da classe conhecida.
Cada candidato precisa de trecho literal, rótulo explícito e valor sustentado
pelo extrator e pelo PDM, sem contradições entre os campos. Resultado inválido,
erro ou orçamento esgotado permanece no relatório. Candidatos aparecem nas
pendências com confirmação manual obrigatória e não viram evidências publicáveis
nem propostas automáticas de enriquecimento. O uso registra modelo, prompt,
chamadas, falhas e tokens; custo permanece desconhecido se houver chamadas.
Os testes usam cliente injetado; esta entrega não homologa uma execução real AWS.

### Revisão por atributo

Congele o relatório e extraia uma amostra reproduzível:

```bash
uv run --locked vx-back enrichment-review-packet /tmp/enriquecimento.json --sample-size 100 --seed 263 > /tmp/pacote.json
```

O pacote contém originais do alvo, atributos conhecidos, valor candidato e
evidências. Preserve o checksum fora do arquivo. Registre revisões em outro JSON:

```json
{"packet_sha256":"HASH_DO_PACOTE","reviews":[{"case_id":"ID_DO_CASO","author":"Nome do técnico","label":"SUPPORTED","evidence":["Documento e identidade conferidos no trecho indicado."]}]}
```

Use `UNSUPPORTED` para erro e `INCONCLUSIVE` quando não puder concluir. Execute:

```bash
uv run --locked vx-back enrichment-evaluate /tmp/pacote.json revisoes.json
```

A avaliação confere hashes, seleção e autoria; desacordo permanece inconclusivo.
Mostra cobertura e precisão entre candidatos decididos, com intervalo Wilson e
recortes por classe/atributo. Não mede recall da população nem precisão
independente; aprovação operacional não fornece rótulo de verdade. Não autoriza
aplicar dados. Os rótulos históricos permanecem intactos.

No batch normal, use o mesmo armazenamento dos originais do bootstrap:

```bash
docker compose run --rm --build batch
```

O batch confere os hashes registrados no dataset, grava um relatório imutável em
`runs/internal-enrichment/<dataset_id>/<hash>.json` e publica propostas ENRICHMENT
ligadas ao job. `counts.internal_enrichment` guarda a chave do relatório e as
métricas; `counts.enrichment` conta propostas de enriquecimento. As pendências
recebem o diagnóstico em `observation.completeness` e continuam disponíveis para
complementação manual. Fontes ausentes são identificadas em `unavailable_sources`;
conteúdo com hash divergente interrompe o processamento. Um job retomado não
aceita troca dos arquivos de referência.

A revisão usa a fila e a tela Enriquecimento existentes. A API confere versão do
material, PDM, classe, origem interna do mesmo dataset e hash de cada evidência.
Uma proposta parcial preserva unidade e NCM e não torna um material canônico.
Não altera quantidades ou valores de estoque. A mudança de atributos já aprovados
pode exigir também revisão fiscal conforme a política existente.

Propostas internas e externas permanecem independentes; uma execução não descarta
a revisão da outra. A aplicação de uma delas exige revalidar a versão das demais.
Cada proposta usa um artefato por material: alterações em outros materiais não
invalidam revisões já realizadas. A primeira data de observação do documento é
preservada em reimportações e resets.

Repetir o mesmo conteúdo não duplica evidências nem propostas. Depois da aprovação,
os atributos persistidos entram na análise seguinte, evitando reapresentar o mesmo
preenchimento. Uma contradição com a descrição original permanece para revisão.

## Medição do kit em 7 de novembro de 2026

A medição de desenvolvimento, sem aplicações, está em
[`measurements/enriquecimento-interno-263.json`](measurements/enriquecimento-interno-263.json).
As 24.074 fontes correspondem a 23.554 registros originais e 520 pedidos.

| Indicador | Antes | Após sugestões, se aprovadas |
|---|---:|---:|
| Materiais com atributos PDM completos | 10.928 | 11.160 |
| Materiais com obrigatórios ausentes | 7.001 | 6.769 |
| Sem classe reconhecida pelo classificador atual | 5.625 | 5.625 |

Foram encontrados 402 preenchimentos em 337 materiais, dos quais 232 passam de
incompletos a completos em atributos. É cobertura das regras, não validação
independente de precisão. O relatório detalha cada fonte para revisão técnica.

## O que ainda é necessário para completar a base

As fontes atuais não comprovam todos os valores: 6.769 materiais ainda ficariam
incompletos e 5.625 exigem revisão de classificação/extração. Melhorar o extrator
nas famílias com mais lacunas pode recuperar valores já escritos; quando o valor
não está nos documentos, a complementação precisa do solicitante ou de nova fonte.

A pesquisa externa permanece restrita aos 15 produtos reais do manifesto, pelo
[fluxo de fontes confiáveis](enriquecimento.md). Ele continua sendo acionado pelos
comandos `enrich-real-products` e `publish-enrichment`; este incremento integra
fontes internas ao SANITIZE e não faz pesquisa externa durante o saneamento.
O restante do kit usa combinações fictícias de fabricante/referência.

O carregador versionado de NCM da #30 também foi integrado pela equipe. A
publicação do enriquecimento vincula a avaliação fiscal configurada e conserva a
exigência de revisão fiscal. A captura de um snapshot oficial continua necessária
para confirmar existência/vigência; as planilhas do Drive não são atributos
técnicos de produto. Ver [snapshot NCM](ncm-snapshot.md).
