# Ensaio e congelamento da demo

Estado em 5/11/2026: **plano preparado; ensaios integrados não realizados**.
A #27 está concluída; a preparação local da #34 já entrega reset protegido,
mas seu ensaio remoto, o aceite da #26 e o Plano B #29 permanecem pendentes. A parte documental pode
avançar, mas a #28 não deve ser encerrada por conter um roteiro escrito.

## Responsáveis e orçamento

Definir uma pessoa para apresentar, uma para operar e uma para o tempo. O
[roteiro](script.md) reserva 270 segundos de conteúdo e 30 de margem. Fazer
duas passagens completas por ambiente com cronômetro, incluindo cliques e rede.
Se passar de cinco minutos, cortar explicações e anexos, sem acelerar a revisão.

O pitch usa apenas a medição e a versão aprovadas no congelamento. Não anunciar
que um roteiro coube em cinco minutos com base apenas em contagem de palavras.

A checagem textual atual contou 371 palavras na fala principal (palavras
separadas por espaço nas linhas de citação). Com hipóteses de 120 palavras
por minuto e 45 segundos de interação, são 230.5 segundos estimados, abaixo dos
270 planejados. Essa conta verifica folga textual; não mede o ritmo de uma pessoa
nem a latência dos ambientes e não substitui as duas passagens cronometradas.

## Pré-condições do ensaio integrado

- [ ] #26 confirmou o fluxo e os critérios de pronto, com evidências verificáveis.
- [ ] #29 disponibilizou e testou o Plano B com HTTPS e login.
- [ ] Executar e conferir no ambiente remoto o seed/reset já entregue pela #34 (`DEMO_MODE=true`), registrando o resumo e os IDs.
- [ ] API, Agent e front estão no commit identificado; URLs de AWS e Plano B registradas.
- [ ] As três personas têm sessões reais válidas, quando a troca fizer parte da demo.
- [ ] O lote da #32 tem job, manifesto, hashes, contagens e amostra revisada identificados.
- [ ] IDs das propostas, materiais e evidências usados na demo foram registrados.
- [ ] A proposta escolhida exige as revisões que serão mostradas e está no estado inicial esperado.
- [ ] Há operador apto a restaurar o estado somente com o mecanismo entregue pela #34.
- [ ] Há captura de segurança do mesmo commit, sem credenciais, rotulada como gravação.

Usar o reset entregue em [demo.md](../../docs/demo.md), no ambiente de demonstração.
O smoke oferece `health`, `local`, `flow` e `authenticated`; `health` cobre apenas
saúde, `flow` altera o estado local e `authenticated` requer HTTPS e cookie jar.
Registrar o modo e o resultado reais; a existência do script não aprova o ensaio
remoto nem as etapas acima.

## Sequência cronometrada

1. Confirmar o ambiente de demonstração e a versão. Preparar/resetar usando a
   entrega da #34 e anotar os IDs. Não executar no ambiente de produção.
2. Entrar como Solicitante e enviar o pedido do [roteiro](script.md).
   Verificar o campo ausente, resposta e chamadas MCP executadas; conferir a
   descrição depois da resposta “classe 8.8, norma DIN 933”.
3. Se o bloco integrado estiver liberado, trocar para Governança com sessão
   real e abrir a proposta pré-selecionada, com antes/depois e evidência.
4. Trocar para Auditor fiscal quando exigido. Mostrar estados separados;
   uma aprovação isolada não deve produzir `APPLIED` se houver outra pendente.
5. Mostrar auditoria com ator e papel efetivos. Os controles visuais de uma
   persona não substituem a autorização do backend.
6. Mostrar somente as métricas confirmadas da execução final. Proposta,
   aplicação e estimativa devem estar identificadas separadamente.
7. Encerrar a fala, registrar duração total e restaurar o estado para outra passagem.

As etapas 3–5 substituem parte da demo, em vez de serem somadas ao bloco de
80 segundos. Se não couberem ou falharem, voltar ao roteiro reduzido e declarar
a limitação; não marcar o fluxo completo como ensaiado.

## Interrupção e alternativa

Decidir a alternativa antes do palco. Se uma ação não responder em até dez
segundos, interromper a tentativa e usar captura já validada, dizendo “esta é
a gravação do ensaio no commit X”. Preservar os limites do sistema; não afrouxar
autenticação ou trocar um dado real por mock para manter a aparência de sucesso.

Sem gravação e sem ambiente integrado, mostrar o relatório local e a validação
real do motor por MCP, com esse rótulo. Um teste local não conclui o Plano B
em EC2 nem o ensaio na AWS. Trocar para EC2 no palco somente se essa passagem
tiver sido ensaiada, com sessões e callback funcionando.

## Registro a preencher após executar

| Ambiente               | Commit/URL                | Seed e IDs                  | Passagem 1                              | Passagem 2          | Evidência             | Situação                                  |
| ---------------------- | ------------------------- | --------------------------- | --------------------------------------- | ------------------- | --------------------- | ----------------------------------------- |
| AWS                    | Pendente                  | Pendente                    | Não executada                           | Não executada       | Pendente              | Bloqueado pelas integrações               |
| Plano B EC2            | Pendente                  | Pendente                    | Não executada                           | Não executada       | Pendente              | Bloqueado pela #29 e integrações          |
| Recorte local do motor | Ver artefato de validação | Caso de parafuso do roteiro | Teste automatizado, sem duração de fala | Não é ensaio humano | Log dos testes locais | Evidência técnica, sem aprovação de palco |

No registro real, incluir data/hora BRT, operador, duração de cada passagem,
resultado por etapa, caminho de captura/log e incidentes. Remover cookies,
tokens, senhas e dados pessoais de logs e capturas compartilháveis.

## Congelamento antes da apresentação

- [ ] Substituir a prévia local pelas contagens verificadas da #32, ou manter a indicação de prévia na fala.
- [ ] Conferir os denominadores: registros, propostas, materiais distintos, campos e dinheiro.
- [ ] Revalidar funcionalidades e retirar do roteiro qualquer etapa não entregue ou não ensaiada.
- [ ] Validar os dois ensaios por ambiente e o tempo total de até cinco minutos.
- [ ] Conferir fontes, datas e rótulos de hipótese; não usar multas ou casos comerciais sem contexto.
- [ ] Registrar a revisão exata dos documentos e dos artefatos mostrados, com os responsáveis pelo aceite.

Até concluir esses itens, os critérios “demo ensaiada na AWS e no Plano B” e
“evidências confirmadas antes do congelamento” da #28 permanecem pendentes.
