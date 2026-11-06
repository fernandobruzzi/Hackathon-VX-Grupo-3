# Evidências dos produtos reais

`vx-back enrich-real-products` consulta fontes revisadas e produz evidências e
propostas de enriquecimento em armazenamento imutável. Não modifica o cadastro,
o estoque ou o NCM e não aprova valores. `publish-enrichment` adapta os artefatos
à fila persistida, cuja revisão usa a API e a tela de evidências.

## Seleção e execução

Use o manifesto original registrado pelo `vx-bootstrap`, no mesmo armazenamento
local ou S3. O manifesto contém `dataset_id`, `tenant_id`, `pdm_version`, arquivos
com hash e `real_material_codes`. O comando confere os hashes da base e do PDM e
exige exatamente os 15 códigos reais conhecidos do kit. Não seleciona novamente
as últimas linhas após ordenar ou filtrar a base.

Na raiz do repositório, com as dependências instaladas e `STORAGE_LOCAL_DIR`
apontando para a pasta usada no bootstrap, ou com o mesmo armazenamento S3:

```bash
uv run vx-back enrich-real-products --manifest-key raw/<dataset_id>/manifest.json --pdm-workbook data/desafio01/03_padrao_cadastro_PDM.xlsx
```

`--material-code` pode ser repetido para consultar somente parte desses 15 códigos.
Um código fora do manifesto é recusado antes de qualquer consulta externa.
O comando retorna `report_key`, resultados e os caminhos das propostas. Os
arquivos ficam sob `evidence/` e `runs/enrichment/`, com identificadores derivados
do conteúdo. Os originais sob `raw/` permanecem intactos.

Para repetir com os mesmos documentos, sem rede:

```bash
uv run vx-back enrich-real-products --manifest-key raw/<dataset_id>/manifest.json --pdm-workbook data/desafio01/03_padrao_cadastro_PDM.xlsx --evidence-manifest-key <report_key>
```

O relatório anterior precisa pertencer ao mesmo manifesto. A repetição verifica
o hash de cada documento, não acessa a rede e não duplica os artefatos. Consultar
novamente o mesmo conteúdo preserva a primeira data de coleta e a proposta.
Um documento diferente cria outra evidência, preservando a anterior.

## Fontes e limites

As URLs são escolhidas em um catálogo revisado do servidor, nunca pelo solicitante.
O catálogo registra referências exatas de SKF, FAG, NSK, Fleetguard, Caterpillar,
Donaldson e Baldwin. As páginas dos fabricantes são priorizadas; as duas páginas
FAG da ABF são identificadas como distribuidor. O NTN `6310ZZC3` fica pendente
enquanto não houver uma fonte revisada para essa referência exata: as variantes
`/EM`, `/5K` e `EC-` não comprovam o item da entrada.

Cada consulta admite somente HTTPS na porta 443 e os hosts exatos da fonte.
Usuário/senha, fragmentos e caracteres de controle na URL são recusados. Todos
os endereços DNS precisam ser públicos e não multicast; a conexão fixa um desses
IPs e mantém a validação TLS para o host original, impedindo nova resolução na
conexão. Redirecionamentos passam pela mesma política.

Limites padrão: dois redirecionamentos, 2 MB por documento, quatro segundos por
operação de rede e doze segundos para a consulta. O DNS também tem prazo.
Conteúdo comprimido e tipos diferentes de HTML, texto e PDF são recusados. PDFs
precisam ter texto, até dez páginas e conteúdo de página limitado. Erros HTTP,
timeout, bloqueios e páginas sem conteúdo utilizável produzem pendências, sem
fabricar valores nem contornar restrições do site.

## Extração e revisão

`ENRICHMENT_REPOSITORY` ou `--repository` seleciona o extrator registrado. O padrão
`catalog_labels_v1` reconhece apenas referência exata e rótulos explícitos de
dimensões em milímetros, fabricante e folga. Não usa equivalência comercial,
cross-reference, instruções do documento ou um score informado por modelo.
Scripts e recomendações de outros produtos não fornecem atributos.

Cada valor mantém URL, título, trecho literal, página, data de coleta, hash e chave
do documento, regra de extração e confiança baseada na evidência. Fonte do
fabricante recebe `HIGH`; distribuidor revisado recebe `MEDIUM`; documentos
simulados dos testes recebem `LOW` e a marca `SIMULATED`. Confiança nunca aprova.
Todos os valores começam `PENDING`.

Valores divergentes entre fontes ou diferentes de um atributo já extraído da
entrada ficam em `conflicts`, com os valores e as evidências envolvidos. Nenhum
deles é escolhido automaticamente. A proposta inclui somente atributos ausentes
e registra o antes original. Não se copia NCM de um catálogo externo.

## Publicação na fila e aprovação

Os artefatos usam `enrichment-artifacts-v2`. A versão nova registra a grafia decimal
do PDM (`118,87MM`) e separa a coleta da publicação. Relatórios anteriores podem
ser reprocessados offline, sem substituir seus documentos ou artefatos.

Com o banco local iniciado, configure `DATABASE_URL` com a conexão de `batch_user`
e use o mesmo armazenamento do bootstrap e da coleta:

```bash
uv run vx-back publish-enrichment --report-key <report_key> --pdm-workbook data/desafio01/03_padrao_cadastro_PDM.xlsx
```

O adaptador confere o hash do relatório, manifesto e documentos, reextrai os fatos
sem rede e vincula dataset, tenant, material e versão atual. Persiste as fontes e
propostas `ENRICHMENT` em uma transação. Repetir a publicação reutiliza os mesmos
identificadores, inclusive após aplicar a proposta. O cadastro mestre permanece
intacto até a aprovação.

Abra **Enriquecimento** como Governança. A lista e a rota estática
`/enriquecimento/revisao/?id=<UUID>` leem fontes persistidas. Cada atributo exibe
URL, trecho, página, confiança, hash do documento e divergência. Valores
divergentes ou inválidos no PDM ficam visíveis e fora desta aprovação. Valores já
conhecidos não são substituídos; não há equivalência de referências por suposição.

A decisão envia apenas versão, área, decisão e justificativa ao endpoint de
aprovação. A API revalida o PDM, original, versão das regras e hashes das fontes,
exige evidência para cada atributo novo e aplica os valores persistidos com
auditoria e idempotência. Mudança de versão ou fonte exige nova proposta.
Tenant e centros restringem leitura e decisão.

Uma proposta pode conter somente parte dos atributos obrigatórios, deixando os
restantes pendentes. A aprovação desse enriquecimento não torna o material
canônico e não altera descrição original, estoque, unidade ou NCM. A revisão
fiscal continua exigida quando há mudança na base fiscal já conhecida.
Aprovar os atributos não certifica o NCM original nem muda seu status fiscal;
uma correção de NCM continua exigindo proposta e avaliação fiscal próprias.
Evidências simuladas ficam marcadas `LOW`/`SIMULATED` e sua publicação ou aprovação
é recusada fora do ambiente local ou em runtime AWS.

## Verificação

Execute `uv run pytest` em `back/`. Os testes usam documentos explicitamente
simulados, cobrem todos os extratores registrados, códigos fora do manifesto,
integridade, divergências, repetição offline e limites do cliente HTTPS. No
Windows, use `PYTHONUTF8=1` para ler as fixtures como no CI Linux. Em `api/`, execute
`uv run pytest` com `TEST_DATABASE_URL` para verificar publicação → leitura →
aprovação parcial, adulteração, escopo, idempotência e preservação de originais e
estoque em PostgreSQL. Esses testes usam documentos simulados, sem rede externa.
Em `front/`, execute `npm run api:check`, `npm run typecheck`, `npm test` e
`npm run build`.

Na verificação externa de 5/11/2026, a página oficial
[NSK 6205DDUC3](https://www.nsk.com/engineering/products/bearings/ball-bearings/deep-groove-ball-bearings/single-row-deep-groove-ball-bearings/6205dduc3-apn.html)
forneceu cinco evidências; a página oficial SKF `6310-2Z/C3` forneceu quatro e
expôs uma divergência com a referência parcial extraída da entrada. No lote
completo, dois dos 15 materiais tiveram evidências e 13 permaneceram pendentes.
Donaldson DBL7300 respondeu 403, a página Fleetguard
LF9009 não forneceu conteúdo textual utilizável e sua URL alternativa de ficha
retornou 404. Esses resultados permaneceram pendentes. Disponibilidade de fonte
externa não é garantida; nenhuma dessas falhas é tratada como dado confirmado.
