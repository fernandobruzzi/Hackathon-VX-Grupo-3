# Roteiro do pitch

Desafio 01 — Do Fundo do Poço. Versão de trabalho de 5/11/2026, na #28.
**Planejado para 4min30s, com 30s de margem dentro dos cinco minutos.** A duração
é uma estimativa textual; o ensaio humano na AWS e no Plano B continua pendente.

Este roteiro usa o que é demonstrável na `main` de referência
`d11f13529f3436672a2145922e8d8509dede160d`: relatório batch e validação por MCP.
A demo integrada com troca real de persona ainda depende das #26, #29 e #34
e de seus pré-requisitos. Não apresentar seletor local simulado, dashboard com
mocks ou código de PR em rascunho como integração entregue.

## Tempo e operação

| Janela      | Duração | Assunto            | Operação planejada                                                                                                          |
| ----------- | ------- | ------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| 00:00–00:25 | 25s     | Problema           | Exibir descrição incompleta do parafuso                                                                                     |
| 00:25–00:55 | 30s     | Solução            | Mostrar regra PDM compartilhada e resultado como proposta                                                                   |
| 00:55–02:15 | 80s     | Demo real do motor | Dois turnos no chat conectado à API/MCP; se essa interface não estiver validada, usar a evidência local reproduzível abaixo |
| 02:15–03:00 | 45s     | Resultado medido   | Exibir o JSON do batch identificado por versão e hashes                                                                     |
| 03:00–03:40 | 40s     | Impacto hipotético | Exibir cenário central e rótulo “HIPÓTESE — inclui capacidade, não só caixa”                                                |
| 03:40–04:10 | 30s     | Mercado e piloto   | Recorte IBGE e proposta de validar disposição a pagar                                                                       |
| 04:10–04:30 | 20s     | Fechamento         | Próximo passo e limite atual                                                                                                |
| 04:30–05:00 | 30s     | Margem             | Troca de tela, latência ou conclusão; sem conteúdo novo                                                                     |

Uma pessoa apresenta; outra opera e avisa o tempo. Se a fala terminar antes,
encerrar e abrir para perguntas. Não preencher a margem com novas promessas.

## Fala principal

### 00:00 — O problema

> Uma peça pode estar no almoxarifado e continuar invisível para quem precisa
> dela. Descrições diferentes criam códigos diferentes. E um pedido incompleto,
> como um parafuso sem classe de resistência, não permite saber se o material
> atende à manutenção. Nosso desafio é tornar esse cadastro confiável.

### 00:25 — A solução

> Nossa solução usa o mesmo padrão de materiais para analisar a base existente
> e conferir novos pedidos. O resultado do saneamento é uma proposta com antes,
> depois e regra aplicada. A prioridade é evitar uma unificação errada. A
> publicação depende de revisão; esta demonstração não altera o cadastro.

### 00:55 — Antes de clicar, diga o que vai acontecer

> Vou enviar um pedido de parafuso sem a classe de resistência. O motor deve
> identificar o campo ausente e pedir essa informação. No painel, as chamadas
> ao MCP precisam corresponder às executadas. Agora informo a classe 8.8.
> A descrição fica no padrão. Isso valida a ficha; a verificação de duplicidade
> ainda está pendente neste fluxo, portanto ele não libera o cadastro.

### 02:15 — Resultado local, sem transformar proposta em economia

> Na rodada local preliminar, analisamos os 23.554 registros do kit. O algoritmo
> gerou 1.147 propostas de unificação, envolvendo 2.629 materiais: 11,2% da entrada.
> Também propôs 7.202 correções de descrição ou grupo e 887 de unidade.
> São propostas, com possíveis sobreposições de materiais. Não são registros
> já eliminados nem dinheiro economizado. A rodada final atualizará esses números.

### 03:00 — Impacto como hipótese

> Para discutir valor, separamos capacidade, despesas e liberação de capital.
> Em um cenário inteiramente hipotético, o modelo estima 300 mil reais de benefício
> econômico no primeiro ano para 274 mil de custo: retorno de 9,5%.
> Esse benefício inclui horas aproveitáveis; não é todo caixa. O estoque de
> 100 milhões é premissa. Nenhum desses valores foi realizado pelo MVP.

### 03:40 — Mercado e validação comercial

> O IBGE registra 2.036 empresas industriais brasileiras com pelo menos 500
> pessoas ocupadas em 2024. É um recorte para investigar, não uma lista de clientes.
> Queremos começar com um piloto em uma grande operação: medir a precisão,
> o trabalho de revisão, o custo e a disposição a pagar antes de escalar.

### 04:10 — Fechamento

> Hoje conseguimos demonstrar as regras e as propostas no kit. O próximo marco
> é validar o fluxo integrado de aprovação e auditoria e medir resultado em
> um cliente. Nossa entrega parte de uma decisão simples: encontrar e conferir
> a peça antes de comprar de novo.

## Ações exatas e resultado esperado

Pedido, conforme caso existente de integração do agente:

```text
Preciso de parafuso sextavado M12x50, aço carbono, zincado branco, DIN 933.
```

Esperado: `PDM001`, `INCOMPLETE`, `CLASSE RESISTENCIA` ausente e `can_submit=false`.
Responder:

```text
classe 8.8, norma DIN 933
```

Esperado: descrição PDM, `VALID`, duplicidade `PENDING` e envio ainda bloqueado.
Não afirmar que a busca ou a publicação ocorreu: o agente dessa versão chama
`get_pdm_template` e `validate_and_format_pdm`. O planejador atual usa regras;
uma chamada a Bedrock/LLM não foi demonstrada por esse fluxo.

Verificação local pelo endpoint do agente e subprocesso MCP reais, a partir de `mcp/`:

```bash
uv run pytest tests/test_conversation_flow.py -k "incomplete_request or panel_calls or follow_up_answer" -v
```

Isso comprova o motor local em teste de integração; **não equivale a uma demo
de navegador, SSO, AWS, Plano B ou três sessões reais**. Se o ambiente integrado
ainda não estiver pronto, apresentar esse recorte com esse nome e manter a
aceitação completa da #28 pendente. O relatório batch é reproduzido pelos
comandos em [roi-assumptions.md](roi-assumptions.md).

## Troca real de persona: substituição condicionada do bloco de 80 segundos

Depois de a #26 confirmar o fluxo e a #34 preparar o estado, o bloco da demo
pode ser substituído por: Solicitante envia o pedido; Governança abre uma
proposta pré-selecionada; Auditor fiscal assume sua sessão autenticada para
uma proposta que exige revisão fiscal; mostrar o estado e o evento de auditoria.
Usar IDs previamente ensaiados e os mesmos valores persistidos, sem improvisar
um novo valor no botão de aprovação. Se faltar uma das revisões, mostrar o
estado pendente; `APPLIED` somente após todas as exigidas.

Esse bloco é **planejado e não ensaiado**. Não somá-lo aos 80 segundos originais.
Não usar a troca de permissões simulada no navegador como prova de autenticação.
As condições, evidências e fallback estão em [rehearsal.md](rehearsal.md).

## Perguntas prováveis da banca

- **Vocês economizaram 11,2% do estoque?** Não. Esse percentual conta registros
  envolvidos em propostas no kit; não mede valor excedente nem caixa.
- **O retorno de 9,5% foi medido?** Não. É um cenário econômico que inclui capacidade.
  Só um piloto com Controladoria pode comprovar benefício e caixa.
- **Qual é a precisão?** A identidade segue regras do PDM, mas a medição em amostra
  revisada por especialistas é uma entrega da #32. Não anunciar “100%”.
- **Onde está o modelo de IA?** O planejador demonstrado é determinístico e usa MCP
  real. Não apresentamos inferência Bedrock como algo executado nesta versão.
- **Há proteção fiscal completa?** A publicação fiscal integrada ainda precisa
  ser validada. Não prometemos enquadramento legal nem multas evitadas.
- **E se a internet cair?** Mostrar evidência gravada do mesmo commit, com rótulo
  “gravada”; se não houver, apresentar o recorte local ou o registro do teste,
  explicando a limitação. Não chamar isso de ensaio concluído do Plano B.

Fontes e denominadores: [premissas](roi-assumptions.md),
[checagem de fontes](source-checks.md) e [evidência local](evidence/batch-preview.json).
