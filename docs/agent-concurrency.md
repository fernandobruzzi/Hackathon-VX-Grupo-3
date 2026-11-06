# Concorrência e processos do Agent

O Agent admite no máximo `AGENT_MAX_CONCURRENT_TURNS` turnos simultâneos por
worker. O padrão é **2**, com um worker no comando `vx-agent`. O Compose limita esse
container a 1 CPU, 512 MiB e 64 PIDs, configuráveis por `AGENT_CPUS`,
`AGENT_MEMORY_LIMIT` e `AGENT_PIDS_LIMIT`. A configuração
precisa ser um inteiro positivo; valores inválidos impedem a inicialização.
Não existe fila de espera dentro do Agent. Excesso recebe HTTP 503, código
`AGENT_BUSY` e `Retry-After: 1`, antes de classificar ou abrir um servidor MCP.
A API mantém o erro controlado do Agent e libera a reserva daquele turno.
Não há repetição automática de uma mensagem.

Cada turno tem uma sessão stdio exclusiva e uma cópia da identidade verificada
no token interno. A identidade e os centros seguem no ambiente daquele processo,
sem alterar o ambiente global ou os parâmetros das tools. As permissões fiscais
continuam sendo aplicadas pelo servidor MCP.

## Prazo e encerramento

O prazo de execução continua em 20 segundos. Ao expirar, o Agent cancela o turno
cooperativamente e responde `AGENT_TIMEOUT`. O fechamento pode acrescentar o
intervalo de limpeza do SDK ao tempo de resposta: fechar pipes, aguardar saída e,
se necessário, encerrar o grupo de processos. A vaga fica ocupada durante essa
limpeza, impedindo que cancelamentos em rajada abram mais processos do que o limite.

Desconectar o HTTP interno API → Agent cancela o turno (`AGENT_CANCELLED`, 499).
Cancelar a tarefa HTTP ou encerrar o lifespan também cancela os turnos ativos.
A implementação usa cancel scopes do AnyIO para preservar o shield de limpeza
do SDK MCP, em vez de cancelar repetidamente a tarefa dona da sessão stdio.
A API pode continuar um turno caso o navegador feche sem encerrar a conexão
interna; nesse caso, o prazo do Agent continua valendo.

No SIGTERM, o Uvicorn dá até cinco segundos para os pedidos terminarem; depois
cancela os handlers e o lifespan aguarda o recolhimento dos servidores MCP.
Docker Compose usa `init: true` e `stop_grace_period: 15s`, deixando tempo para
essa limpeza. Na AWS, mantenha init habilitado e uma janela de parada de pelo
menos 15 segundos. SIGKILL/OOM não oferecem execução do cleanup Python.

## Medição local

Resultados brutos: [agent-concurrency-local.json](measurements/agent-concurrency-local.json).
Foram usadas duas rodadas independentes com oito chamadas HTTP paralelas cada,
seguidas de oito chamadas canceladas durante a inicialização do MCP. O container
tinha **1 CPU, 512 MiB, limite de 64 PIDs e init**, com um worker e limite de dois
turnos. A busca usou o banco local com o kit de 23.554 materiais e seu índice real.
O planejador foi `rule_based_v1`; não houve chamadas a Bedrock nem respostas
simuladas de ferramentas.

| Observação                                           |   Rodada 1 |   Rodada 2 |
| ---------------------------------------------------- | ---------: | ---------: |
| Atendidas / ocupadas                                 |      2 / 6 |      2 / 6 |
| Latência p50 dos atendidos                           |   15,728 s |    6,447 s |
| Latência p95 dos atendidos                           |   15,782 s |    6,451 s |
| Servidores MCP antes / pico / depois                 |  0 / 2 / 0 |  0 / 2 / 0 |
| Processos Agent + descendentes antes / pico / depois |  1 / 3 / 1 |  1 / 3 / 1 |
| Soma RSS no pico                                     | 355,17 MiB | 355,70 MiB |
| Memória do cgroup no pico                            | 308,40 MiB | 308,52 MiB |

O p95 usa o posto mais próximo; cada rodada tem só dois turnos atendidos.
Estes números são observações locais, não um SLA ou limite universal. Outros
testes disputavam recursos da máquina. Somar RSS pode contar páginas compartilhadas
mais de uma vez; memória do cgroup inclui o próprio medidor e caches. Não se exige
que o RSS volte ao mesmo byte, mas os processos precisam voltar à contagem inicial.

O limite dois manteve o pico medido abaixo de 512 MiB e os turnos atendidos abaixo
do prazo. Aumentá-lo exige repetir a medição. A homologação na task AWS, incluindo
o modelo e as quotas reais, está na #107.

## Reproduzir

Depois de subir a aplicação e construir o índice:

```bash
docker compose up --build -d --wait
docker compose exec -T agent python - --requests 8 < scripts/measure_agent.py
```

O Compose já usa os recursos limitados da medição. Para uma execução isolada,
construa a imagem `agent` e use `--init --cpus=1 --memory=512m --pids-limit=64`,
`AGENT_MAX_CONCURRENT_TURNS=2` e a conexão de leitura `mcp_reader`, na mesma rede
do Postgres local. O medidor não imprime tokens, variáveis de ambiente ou DSNs.
O CI executa a mesma carga no stack isolado e falha se ultrapassar o limite,
não houver resposta de sucesso ou restarem processos depois dos cancelamentos.

## Interpretar a memória coletada

O medidor resolve `/proc/self/cgroup` e `/proc/self/mountinfo` para ler o cgroup
em que ele executa. Rode-o dentro do container Agent, como no comando acima:
executá-lo no host não mede o mesmo escopo. São aceitos cgroup v2
(`memory.current`) e v1 (`memory.usage_in_bytes`), inclusive montagens de subárvore
e namespaces de cgroup. O medidor não usa o total da raiz do host quando o Agent
pertence a um cgroup filho.

Em `before` e `after`, `container_memory_kib` é o contador convertido para KiB
(bytes divididos por 1024, truncados). `container_memory_source` informa o caminho
do contador utilizado ou tentado. `container_memory_unavailable_reason` é `null`
quando a leitura funciona; caso contrário, o valor da memória é `null`, nunca zero:

| Motivo                      | Interpretação                                                                   |
| --------------------------- | ------------------------------------------------------------------------------- |
| `metadata_unreadable`       | Não foi possível ler os metadados de cgroup/montagem no `/proc`.                |
| `no_matching_memory_cgroup` | Não foi possível associar a participação do processo a uma montagem de memória. |
| `counter_unreadable`        | O contador está ausente ou não pode ser lido, por exemplo por permissão.        |
| `counter_invalid`           | O contador não contém um inteiro não negativo.                                  |

`peak.container_memory_kib` é o maior valor **observado nas amostras disponíveis**,
não o pico histórico do kernel. `peak.container_memory_sources` lista as fontes
das leituras válidas; `peak.container_memory_unavailable_samples` conta as amostras
sem leitura. Se esse contador for maior que zero, a observação de memória tem
lacunas, mesmo que `before` e `after` sejam válidos. Se nenhuma amostra tiver leitura,
o pico fica `null` e a lista de fontes fica vazia. Zero KiB continua sendo uma
leitura válida. Os picos de processos, RSS e memória podem ocorrer em instantes
diferentes.

Memória de cgroup inclui o medidor e caches; RSS soma Agent e descendentes e pode
contar páginas compartilhadas mais de uma vez. Uma medida não substitui a outra.
Um relatório com memória indisponível ainda verifica processos e respostas, mas
não comprova margem de memória nem ausência de OOM. Os resultados locais já
registrados acima permanecem observações locais; este diagnóstico não substitui
a homologação da task AWS da #107 nem altera recursos ou limites do deploy.

A suíte MCP cobre rajada, timeout, cancelamento da tarefa HTTP, desconexão ASGI,
shutdown do lifespan e SIGTERM de um servidor Uvicorn real, conferindo a saída
dos subprocessos. Duas buscas reais simultâneas também conferem isolamento de
centros e de permissões financeiras.
