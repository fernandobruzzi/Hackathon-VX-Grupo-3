# Snapshot de NCM: existência e vigência

O módulo `domain.ncm_snapshot` prepara a tabela de referência e confere existência e
vigência de códigos na **data registrada no snapshot**. Não usa a data da consulta,
não muda materiais, não sugere substituições e não concede aprovação fiscal.

Preparação local da #30: **manter o PR em rascunho** até obter e validar uma
captura oficial real. Os testes locais e os contratos integrados não encerram
esse critério; não há bytes oficiais nesta entrega.

## Fonte e limite da entrega

A [Receita Federal](https://www.gov.br/receitafederal/pt-br/assuntos/aduana-e-comercio-exterior/classificacao-fiscal-de-mercadorias/download-ncm-nomenclatura-comum-do-mercosul)
publica o endereço JSON sem captcha:

```text
https://portalunico.siscomex.gov.br/classif/api/publico/nomenclatura/download/json
```

A página esclarece que a exportação contém somente a tabela vigente: códigos
passados e futuros devem ser consultados pelo Histórico do Classif. A
[documentação de integração do Siscomex](https://www.gov.br/siscomex/pt-br/sistemas-de-comercio-exterior/integre-seu-sistema)
informa atualização diária à meia-noite. Portanto, importar a tabela de hoje com
uma data histórica arbitrária não recria a tabela daquela data.

Em 06/11/2026, a captura no ambiente de desenvolvimento foi bloqueada pela política
de saída: `curl --head --max-time 20 <URL acima>` recebeu
`HTTP/1.1 403 Forbidden` e `CONNECT tunnel failed, response 403`. O conector web
confirmou as páginas oficiais, mas não conseguiu abrir o arquivo JSON. Nenhuma
tabela oficial foi obtida ou incluída neste PR. O host necessário é
`portalunico.siscomex.gov.br`, por HTTPS; TLS permanece verificado e não há fallback.

O adaptador aceita o envelope `Data_Ultima_Atualizacao_NCM` / `Nomenclaturas` e os
campos `Codigo`, `Descricao`, `Data_Inicio`, `Data_Fim`. Datas usam `DD/MM/AAAA`,
inclusive `31/12/9999`. A compatibilidade precisa ser confirmada com uma captura
oficial antes de habilitar o fluxo. Os testes usam exclusivamente a fixture
**SIMULADA** `back/tests/fixtures/ncm_simulated.json`: códigos e intervalos são
exemplos de teste, não uma fonte fiscal. Os cenários expirado/futuro exercitam a
regra, sem afirmar que a exportação vigente os contém.

## Importar e conferir localmente

A partir de `back/`, com o workspace instalado:

```bash
STORAGE_LOCAL_DIR=/tmp/vx-ncm-demo uv run python -m clients.ncm_snapshot_cli import-file tests/fixtures/ncm_simulated.json --snapshot-date 2026-11-06 --version simulated-ncm-v1 --simulated
STORAGE_LOCAL_DIR=/tmp/vx-ncm-demo uv run python -m clients.ncm_snapshot_cli check simulated-ncm-v1 73181500
```

O resultado conserva o NCM original, normaliza o código com a regra já existente,
e inclui `exists_in_snapshot`, `valid_in_snapshot`, `requires_fiscal_review`, motivos,
`ncm_version`, `source_sha256`, `snapshot_date`, `source_kind` e `rule_id`.
Um código fora do intervalo, ausente ou inválido sempre exige revisão fiscal.
Os dois extremos do intervalo são inclusivos. Capítulos e posições não são códigos
NCM completos; apenas registros de oito dígitos entram no índice.

Arquivos importados sem `--simulated` recebem `IMPORTED_UNVERIFIED`; importações não
comprovam procedência. Tanto essa origem quanto `SIMULATED` sempre acrescentam
`NCM_SOURCE_UNVERIFIED` e mantêm revisão fiscal, mesmo quando existência e vigência
no conteúdo sejam verdadeiras. Nenhum comando permite marcar um arquivo local
como download oficial.

Quando a rede permitir a captura real:

```bash
uv run python -m clients.ncm_snapshot_cli download
```

O cliente usa apenas a URL fixa, timeout de 30 s por operação de I/O (não um
prazo total nem limite para DNS), limite de 20 MiB, proxies e verificação TLS
do sistema, sem redirecionamentos. Somente esse caminho registra
`OFFICIAL_DOWNLOAD` e a URL oficial. A data é capturada no fuso
`America/Sao_Paulo`; o cabeçalho `Vigente em DD/MM/AAAA`, quando presente, deve
coincidir com ela. Uma data simples de última atualização pode ser anterior à
captura, mas nunca posterior. Cabeçalhos desconhecidos, datas inválidas, períodos
invertidos, códigos duplicados e arquivos incompletos são recusados.

## Registro e integração pendente

`NcmSnapshotStore` recebe o `ObjectStore` existente: funciona localmente e com
`STORAGE_BACKEND=s3`. Grava os bytes originais em
`references/ncm/raw/<sha256>.json` e um manifesto imutável em
`references/ncm/versions/<version>.json`, com versão, SHA-256 completo, data,
origem, URL quando comprovada, atualização declarada e quantidade de códigos.
Repetir a mesma carga é idempotente. Outra carga ou data sob a mesma versão é
recusada. A leitura confere o hash e revalida o arquivo antes de disponibilizá-lo.
Não existe seleção implícita de versão “mais recente”.

A interface para consumidores é:

```python
from clients.ncm_snapshot_store import NcmSnapshotStore
from clients.storage import get_object_store
from domain.ncm_snapshot import check_snapshot_ncm

snapshot = NcmSnapshotStore(get_object_store()).load(version)
assessment = check_snapshot_ncm(snapshot, raw_ncm)
```

## Referência compartilhada e aprovação

Após registrar a tabela, configure `NCM_SNAPSHOT_VERSION=<versão registrada>` na
API, no Agent e no batch, com acesso ao mesmo ObjectStore. A variável fica vazia
por padrão: preserva o comportamento sem referência, com existência/vigência
indisponíveis e `OFFICIAL_SNAPSHOT_UNAVAILABLE`. Não há consulta de rede durante
uma avaliação nem seleção automática da tabela mais recente. Os rótulos legados
de contexto em sessões/jobs (por exemplo, `ncm-demo-v1`) permanecem nesta entrega;
a referência fiscal efetiva é a versão/hash/data/origem do assessment e do
checkpoint, não esse rótulo de contexto.

O helper `clients.ncm_snapshot_store.load_configured_ncm_snapshot(requested_version=None)`
resolve a versão do servidor e revalida o objeto sem cache. Uma versão solicitada
pelo cliente precisa coincidir com a configurada. Referência configurada ausente,
corrompida ou inacessível provoca erro explícito, sem fallback para ausência ou
simulação. MCP retorna erro de tool; API retorna `NCM_REFERENCE_UNAVAILABLE`.

`check_ncm_consistency` combina a coerência PDM com o snapshot opcional. Ausência,
intervalo não vigente e procedência não verificada mantêm revisão fiscal, mesmo
quando o código é tecnicamente consistente com o PDM. Divergências técnicas e
mudanças na grafia também conservam seus motivos de revisão. A avaliação agora
inclui `ncm_version`, `ncm_source_sha256`, `ncm_snapshot_date` (ISO) e
`ncm_source_kind`; todos entram no `evaluation_hash` determinístico.

O batch vincula a referência às propostas fiscais e, quando configurada, também
às propostas de merge/correção técnica. O checkpoint guarda versão, hash, data e
origem; retomar a análise com outra referência exige novo job. A retomada
exclusiva da finalização usa as métricas já congeladas, sem reavaliar propostas. A API recalcula a
avaliação usando a mesma configuração em cada aprovação e compara o assessment
inteiro já vinculado ao changeset. Mudanças de versão, hash, data ou origem recusam
a proposta com `NCM_ASSESSMENT_CHANGED`; propostas antigas sem assessment também
precisam ser regeneradas quando a referência passa a ser configurada. O guard de
aprovação exige revisão fiscal para os motivos do snapshot, inclusive quando o
NCM persistido não está sendo alterado. Uma diferença apenas de grafia, quando
a correção técnica conserva o NCM original, não é um motivo do snapshot; a
avaliação global continua sinalizando que normalizar esse NCM seria uma alteração
fiscal. Os guards existentes continuam exigindo revisão para mudanças reais de
NCM ou dos atributos que sustentam sua classificação. A autorização humana continua separada do
resultado do motor. O contrato de avaliação passa a `pdm-ncm-v2`: assessments v1
já persistidos precisam ser regenerados mesmo sem configurar um snapshot, porque
não contêm os novos campos vinculados ao hash. A compatibilidade sem configuração
preserva a checagem PDM, não autorizações ou assessments antigos.

A configuração atravessa as allowlists dos subprocessos de MCP/batch. No Compose,
Agent lê o volume de referências compartilhado sem escrita; API e batch mantêm
acesso ao armazenamento existente. Na AWS, configure a mesma versão e bucket nas
três tasks e permissão de leitura dos objetos para o Agent. Nenhum schema de banco
ou dependência foi adicionado. A captura real da fonte oficial e a confirmação do
formato permanecem pendentes; não habilite o fluxo oficial com a fixture simulada.

Validação local:

```bash
uv run pytest tests/test_ncm_snapshot.py
```

## Critério pendente para sair de rascunho

Registrar uma captura obtida pelo cliente HTTPS fixo, com TLS e política de rede
vigentes, conferir o envelope e os campos contra os bytes oficiais e preservar
SHA-256, data de cobertura, origem e manifesto no ObjectStore. Validar então a
leitura compartilhada e os assessments de batch, MCP e API com essa referência.
O registro histórico de bloqueio por CONNECT 403 acima não foi substituído por
uma captura nesta integração. Um arquivo de espelho ou uma fixture não recebe
origem oficial. A configuração permanece vazia até essa validação; sem referência
a existência e a vigência continuam desconhecidas.

A integração conserva a resolução manual de pendências e a finalização de métricas
congeladas do batch: a retomada da finalização não reexecuta a análise nem altera
o payload aprovado. A referência NCM é vinculada à análise e às propostas antes
desse congelamento. A aprovação continua reavaliando a referência configurada
e exigindo as autorizações técnica e fiscal aplicáveis.
