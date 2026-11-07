# Histórico e acompanhamento de batch

A Governança consulta `GET /api/v1/batch/jobs` com `limit` entre 1 e 100
(padrão 20), `cursor` opcional e `status` opcional (`QUEUED`, `RUNNING`,
`SUCCEEDED` ou `FAILED`). A ordenação usa a data original de criação decrescente
com o UUID crescente como desempate. Retomar um job não muda sua posição no histórico.

`next_cursor` é opaco: envie o valor recebido na próxima consulta, conservando o
status. `null` indica o fim. O cursor registra a posição, empresa e filtro; formato
inválido, posição inválida ou troca de empresa/filtro recebe `422 INVALID_CURSOR`.
A posição não depende de o registro de referência continuar existindo. O cursor
não concede acesso: todas as consultas conferem a sessão, `batch:run` e o tenant.
Numa coleção estável, cada job aparece uma única vez ao percorrer as páginas.

A resposta inclui `active_job`, com o job `QUEUED` ou `RUNNING` do tenant, ou
`null`. Essa leitura independe da página e do status selecionado. Assim, uma
execução antiga retomada aparece no acompanhamento mesmo fora dos últimos 20
registros ou enquanto o histórico mostra somente falhas. Jobs sem heartbeat
continuam sujeitos ao prazo de expiração já usado pela API.

A tela permite carregar mais páginas, filtrar por status e atualizar o histórico.
Enquanto há um job ativo, ela atualiza seu acompanhamento e as páginas carregadas.
Cada atualização percorre novamente a sequência de cursores a partir da primeira
página para incorporar novas execuções sem conservar limites antigos. A interface
remove IDs repetidos se houver mudanças durante a consulta. Trocar sessão ou filtro
reinicia o histórico; respostas anteriores não repovoam a tela. Falhas de leitura
preservam as páginas já exibidas e permitem tentar novamente. A resposta da primeira
página atualiza o acompanhamento mesmo quando uma página seguinte falha. Erros de iniciar ou
reprocessar continuam separados dos erros de consulta, e respostas perdidas mantêm
a chave do comando conforme [batch-idempotencia.md](batch-idempotencia.md).

## Verificação local

Os testes de API em `tests/test_batch_history.py` usam PostgreSQL descartável:
125 jobs, datas empatadas, outro tenant, cursores inválidos, mudança de filtro,
fim da coleção e retomada fora da primeira página. Os testes da tela exercitam
125 registros, falha de página e repetição, filtro, acompanhamento e troca de
sessão com resposta antiga pendente. Execute as suítes e os comandos do front
conforme o `AGENTS.md` antes de integrar.
