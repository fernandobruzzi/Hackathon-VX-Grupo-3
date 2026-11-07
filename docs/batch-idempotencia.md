# Idempotência dos comandos batch

Iniciar (`POST /api/v1/batch/jobs`) e retomar
(`POST /api/v1/batch/jobs/{id}/resume`) exigem `Idempotency-Key` com UUID.
Ausência ou formato inválido recebe 422, antes de criar manifesto ou disparar task.

A chave identifica um comando do usuário autenticado. O registro em
`operation_requests` vincula tenant, ação, recurso e corpo completo. Locks
transacionais serializam comandos concorrentes; o job e a operação são confirmados
na mesma transação, antes do disparo. Só a primeira requisição grava o manifesto
e chama o runner. Uma nova chave continua sujeita à trava de job ativo por tenant.

Repetir a mesma operação devolve 202 com o mesmo id e o **estado atual** do job,
mesmo depois da conclusão. Não inicia outro processamento nem retoma um job que
falhou. Usar a chave em outro corpo, ação ou recurso recebe
`409 IDEMPOTENCY_CONFLICT`. Sessão, permissão `batch:run` e acesso ao dataset/job
são conferidos novamente antes de recuperar qualquer dado.

Uma falha de comunicação com o runner pode deixar o resultado do lançamento
incerto. O comando permanece registrado: o job recebe `FAILED/LAUNCH_FAILED`,
e repetir a chave recupera esse job sem outro lançamento. Se o processo parar
depois do commit e antes do disparo, o job fica `QUEUED` e a ausência de heartbeat
o torna `FAILED/WORKER_NOT_STARTED`. A recuperação nesses casos é uma **retomada
explícita com nova chave**, usando o checkpoint e a proteção de lease existentes.
Não há retry automático do lançamento externo.

A tela conserva chave, corpo e id do job enquanto não recebe uma resposta
confirmada. “Tentar novamente” repete esse comando, mesmo que o polling já mostre
um job ativo ou outro dataset tenha sido carregado. Uma nova operação recebe outra
chave. Trocar a sessão descarta a tentativa e impede respostas da sessão anterior
de alterar o estado da tela. O feedback de erro de ação permanece separado do
erro de atualização da listagem.

## Verificar localmente

Com PostgreSQL descartável e `TEST_DATABASE_URL` terminado em `_test`, de `api/`:

```bash
uv run --locked pytest tests/test_batch_idempotency.py tests/test_batch_api.py
```

Os testes HTTP cobrem chave ausente/inválida, repetição durante e depois da
execução, concorrência no início e na retomada, conflito de corpo/recurso,
revogação de permissão, outro tenant e resposta perdida do runner. De `front/`,
`npm test` exercita os botões reais, falha de rede, polling e repetição com a mesma
chave e corpo. O contrato inclui um replay de job concluído; `npm run api:check`
verifica os tipos gerados.
