# Snapshot de NCM: existência e vigência

O módulo `domain.ncm_snapshot` prepara a tabela de referência e confere existência e
vigência de códigos na **data registrada no snapshot**. Não usa a data da consulta,
não muda materiais, não sugere substituições e não concede aprovação fiscal.

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

A integração com `check_ncm_consistency`, batch, chatbot, recursos MCP e aprovação
continua dependente da entrega de #22 (PR #67). Seus arquivos não foram alterados.
O consumidor deve combinar os motivos de ambas as avaliações, conservar pendências
técnicas/fiscais já existentes e incluir **versão + hash + data** no assessment e
no hash do conjunto de alterações aprovado. Uma troca de referência precisa
invalidar/regenerar a proposta, sem reaproveitar uma aprovação anterior. Snapshot
ausente ou com falha de integridade não autoriza o cadastro: o erro deve aparecer
como referência indisponível, sem substituir a referência por dados simulados.

Validação local:

```bash
uv run pytest tests/test_ncm_snapshot.py
```
