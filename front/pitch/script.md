# Roteiro do pitch

Desafio 01 — Do Fundo do Poço. Evidência do saneamento atualizada em 8/11/2026, na #317.
**Planejado para 4min30s, com 30s de margem dentro dos cinco minutos.** A duração
é uma estimativa textual; o ensaio humano na AWS e no Plano B continua pendente.

O saneamento integral, as decisões da amostra e o snapshot posterior estão na
[evidência da rodada local](evidence/batch-final.json). O ensaio humano integrado
na AWS e no Plano B segue pendente nas #26, #29 e #34. Usar somente o ambiente
e os casos previamente ensaiados.
Ao citar qualidade, seguir [as evidências e limites da avaliação](evaluation.md)
e a homologação humana independente da #113.

## Tempo e operação

| Janela      | Duração | Assunto            | Operação planejada                                                                                                          |
| ----------- | ------- | ------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| 00:00–00:25 | 25s     | Problema           | Exibir descrição incompleta do parafuso                                                                                     |
| 00:25–00:55 | 30s     | Solução            | Mostrar regra PDM compartilhada e resultado como proposta                                                                   |
| 00:55–02:15 | 80s     | Saneamento da base | Exibir o resultado do batch, o caso de NCM da amostra, a auditoria e o snapshot posterior                                  |
| 02:15–03:00 | 45s     | Cadastro no chat   | Mostrar o campo faltante, a validação PDM e NCM e o resultado da busca de semelhantes                                      |
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
> aplicação das propostas passa pelo fluxo de revisão. A amostra da demonstração
> foi aplicada em um banco de ensaio.

### 00:55 — Saneamento integral e amostra aplicada

> Em 8 de novembro, o lote local analisou os 23.554 registros do kit. Foram
> registradas 16.721 propostas. Em NCM, foram 680 preenchimentos, 884 trocas de
> código e 4.519 ajustes de formato propostos. Um material pode aparecer em
> várias propostas. Aplicamos uma amostra pela fila normal,
> com decisões registradas na auditoria e um snapshot posterior da base.
> No snapshot, o preenchimento aprovado reduziu os registros sem NCM de
> 1.173 para 1.172. A rodada mede o tratamento do kit; a economia precisa
> ser comprovada num piloto.

### 02:15 — Validação no cadastro

> Vou enviar um pedido de parafuso sem a classe de resistência. O motor deve
> identificar o campo ausente e pedir essa informação. No painel, as chamadas
> ao MCP precisam corresponder às executadas. Agora informo a classe 8.8.
> A descrição fica no padrão. A busca deve mostrar se há candidatos e se falta
> alguma decisão. Validar a ficha não publica o material; o envio depende do
> resultado e das decisões exigidas.

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

> Hoje temos regras, propostas e um fluxo local de aprovação e auditoria.
> O próximo marco é ensaiar a versão implantada e medir resultado em um cliente. Nossa entrega parte de uma decisão simples: encontrar e conferir
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

Esperado: ficha validada pelo PDM. No Agent conectado atual, além de
`get_pdm_template` e `validate_and_format_pdm`, `search_similar_materials` consulta
o índice quando configurado e aplicável ao caso. O estado depende do índice,
da identidade e das decisões: pode permanecer `PENDING`, apresentar `MATCH_FOUND`
ou chegar a `NO_MATCH`; não fixar um resultado sem registrar a execução escolhida.
Sem índice, a verificação fica pendente e o envio bloqueado. Uma ficha `VALID`
não comprova publicação. Mostrar as chamadas realmente executadas e o estado
retornado. O planejador usa regras; esse fluxo não comprova inferência Bedrock/LLM.

Se o solicitante escolher um item já cadastrado ou aceitar um semelhante,
mostrar quantidade em estoque, detalhes do item e valor unitário para o papel
autorizado. O roteiro encerra a demonstração desse caminho nesse retorno.
Reservas, compras e acompanhamento detalhado ficam na evolução pós-hackathon.

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

Depois do aceite da #26 e do reset/ensaio remoto da #34, o bloco da demo
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

- **Quanto a empresa economizou?** A rodada mediu propostas e aplicações no kit
  sintético. Economia realizada precisa de evidência financeira num piloto.
- **O retorno de 9,5% foi medido?** Não. É um cenário econômico que inclui capacidade.
  Só um piloto com Controladoria pode comprovar benefício e caixa.
- **Qual é a precisão?** A identidade segue as regras do PDM. A medição independente
  por especialistas está na #113.
- **Onde está o modelo de IA?** O planejador demonstrado é determinístico e usa MCP
  real. Não apresentamos inferência Bedrock como algo executado nesta versão.
- **Há proteção fiscal completa?** A revisão fiscal e a consistência NCM local estão integradas;
  a atualização oficial da fonte NCM (#131) e a homologação humana permanecem pendentes. Não prometemos enquadramento legal nem multas evitadas.
- **E se a internet cair?** Mostrar evidência gravada do mesmo commit, com rótulo
  “gravada”; se não houver, apresentar o recorte local ou o registro do teste,
  explicando a limitação. Não chamar isso de ensaio concluído do Plano B.

Fontes e denominadores: [premissas](roi-assumptions.md),
[checagem de fontes](source-checks.md) e [evidência local](evidence/batch-final.json).
