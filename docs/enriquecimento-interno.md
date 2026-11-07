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
