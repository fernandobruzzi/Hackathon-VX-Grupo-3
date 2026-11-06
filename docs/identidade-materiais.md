# Identidade de materiais

## Regra de negócio

Só confirmar duplicidade quando as evidências indicam a mesma peça, sem contradição técnica. Perder uma duplicidade é preferível a unificar peças diferentes. Uma nota alta de similaridade ou uma chave coincidente encontra candidatos; não vence evidência contraditória.

| Decisão              | Evidência                                                                                         | Consequência                                                            |
| -------------------- | ------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| Mesmo material       | Identidade confirmada pelo PDM e evidências coerentes                                             | Pode gerar proposta de unificação, sujeita à aprovação                  |
| Materiais diferentes | Diferença confirmada nos atributos de identidade ou fabricantes distintos                         | Manter os cadastros separados; eventual equivalência é avaliada à parte |
| Revisão necessária   | Informação ausente ou contraditória, PN ambíguo, modelo de equipamento ou revisão sem confirmação | Não confirmar identidade; registrar o que precisa ser esclarecido       |

### Evidência mínima

- **Classes por especificação:** classe, substantivo/qualificador e atributos obrigatórios aplicáveis confirmados pelo PDM. Um valor ausente não comprova igualdade.
- **Classes por referência:** mesmo fabricante e PN genuíno, sem conflito conhecido de peça, atributos ou revisão. Se os dois lados só identificam a peça pelo PN, a regra do PDM continua aplicável. Se um lado traz um tipo específico e o outro não, a identidade fica em revisão; isso evita usar o registro genérico como ponte entre peças distintas.
- Fabricantes distintos permanecem separados mesmo quando os atributos técnicos coincidem. Fabricante desconhecido não conecta fabricantes conhecidos.
- Tipo, modelo de equipamento e código da peça são informações distintas. `6030` não prova que uma BUCHA e uma RODA GUIA sejam a mesma peça da escavadeira.
- Preservar o valor original e a interpretação. Referência estruturada e referência extraída contraditórias impedem confirmar identidade.
- `REV A` e outras revisões exigem confirmação técnica. Essa homologação permanece pendente, conforme decisão registrada para a #113.
- Normalização de grafia não comprova a neutralidade de sufixos. A chave legada pode aproximar `PN-00` e `PN`, mas a decisão compartilhada agora os retém para revisão quando diferem dessa forma. Duas ocorrências do mesmo PN completo continuam comparáveis. Catálogo, desenho ou declaração técnica identificável precisa respaldar uma futura regra de equivalência de sufixos.
- Nomes hierárquicos como TAMPA/TAMPA PRESSAO usam o tipo específico. Nomes disjuntos como NIPLE/COTOVELO não ganham um tipo escolhido arbitrariamente.

### Exemplos verificáveis

| Caso                                                                                           | Resultado                                                 |
| ---------------------------------------------------------------------------------------------- | --------------------------------------------------------- |
| FILTRO OLEO LUBRIFICANTE FLEETGUARD LF9009 / LF 9009, com evidência coerente                   | Mesmo material                                            |
| Consulta genérica FILTRO LF9009 diante de candidato classificado como FILTRO OLEO LUBRIFICANTE | Revisão necessária para confirmar o tipo                  |
| NIPLE e NIPLE com a mesma ficha PDM completa                                                   | Mesmo material                                            |
| NIPLE e COTOVELO com medidas iguais                                                            | Não são a mesma identidade; mudar o tipo exige nova busca |
| PETRONAS / MOBIL com a mesma especificação de óleo                                             | Cadastros separados; somente candidatos a equivalência    |
| TAMPA PRESSAO 25187467 / TAMPA MOLA 21290535, SULZER/916678-994                                | Revisão necessária: o nome contradiz o PN coincidente     |
| Modelo 6030 sem referência genuína, REV A não confirmada ou PN-00 versus PN                    | Revisão necessária                                        |

Preço, saldo e NCM não comprovam identidade. Identidade confirmada também não resolve sozinha a consolidação: embalagens exigem fator e fonte, NCM segue as aprovações fiscais e o cadastro principal exige Governança. Os saldos originais permanecem imutáveis.

## Aplicação no pipeline

`back/domain/identity_decision.py` contém a decisão de par consumida por candidatos exatos, propostas batch, busca MCP e aprovação transacional. A decisão revalida os atributos com o PDM; uma chave antiga ou fornecida por outro produtor não confirma identidade por si.

A busca identifica o substantivo tanto do pedido quanto do candidato, considerando a descrição original. O Agent transporta o tipo resolvido para a tool. Agent e API vinculam o resultado da busca à mesma assinatura de classe, tipo e atributos preenchidos. Mudar NIPLE para COTOVELO, mesmo mantendo as medidas, invalida a busca anterior; verificações legadas exigem nova consulta.

Na aprovação de unificação, a API confere a interpretação e a evidência original de cada membro antes de gravar. Conflito gera recusa explícita; a proposta continua pendente e não há alteração de material ou consolidação. A versão `identity-v3` entra na assinatura do índice e dos jobs: reconstruir o índice pelo fluxo de indexação existente antes de usar as novas regras. Um job iniciado com outra assinatura precisa de nova execução.

As pendências do relatório de identidade preservam códigos, versões, originais e motivos. A mudança não aprova, cancela ou elimina propostas antigas nem altera propostas já aplicadas. Pendências anteriores continuam sujeitas à revisão explícita; interpretações antigas não dispensam a revalidação atual.

## Papel da IA hoje

No fluxo atual, uma dúvida não dispara consulta a LLM. Classificação, extração, planejamento do chat e verificação de identidade usam regras. Os embeddings opcionais ajudam a recuperar candidatos na indexação/busca; não classificam o par como idêntico e não autorizam unificação. `ranking_score` ordena resultados e não é uma probabilidade calibrada.

## Evidência e homologação

Para resolver uma dúvida, registrar responsável técnico, data, fonte identificável, aplicação e justificativa: catálogo do fabricante, desenho, lista de peças ou declaração de Engenharia/Manutenção. Informação contraditória ou não comprovada continua inconclusiva. Uma confirmação de substituição deve identificar origem, destino, aplicação e restrições; não vira automaticamente duplicidade.

A comparação reproduzível desta entrega está em [shared-material-identity-144.json](measurements/shared-material-identity-144.json). Usa a mesma base e as mesmas coortes congeladas do PR #74, sem alterar rótulos históricos. Grupos retidos para revisão podem incluir duplicidades verdadeiras; redução do número de propostas não equivale a erros corrigidos. São evidências de desenvolvimento, não homologação independente nem estimativa de precisão do produto.

Na base de 23.554 materiais, comparada ao commit `dadd4bec`:

| Medida                                          | Antes | Depois |
| ----------------------------------------------- | ----: | -----: |
| Propostas MERGE                                 | 1.049 |    978 |
| Materiais envolvidos nas propostas              | 2.390 |  2.215 |
| Materiais com pendência explícita de identidade |   549 |    821 |
| Positivos recuperados na coorte histórica v1    | 32/35 |  30/35 |
| Positivos recuperados na coorte de aliases      | 31/37 |  30/37 |
| Pares positivos recuperados                     | 49/61 |  46/61 |

Os 71 grupos retirados exigem confirmação do sufixo da referência; nenhum grupo novo foi proposto. As 272 novas pendências tornam explícitos sufixos (175 materiais), substantivos contraditórios (11) e fabricante não confirmado (86). Nenhuma pendência anterior foi removida. Os falsos conhecidos continuam sem proposta nos dois estados; os 520 pedidos mantêm exatamente os mesmos resultados. As perdas de recuperação acima são mantidas como abstenções, sem mudar os rótulos positivos históricos.

Na revalidação anterior ao merge, sobre a `main` em `03ff9a61`, os grupos, motivos e recuperações acima permaneceram iguais. A extração atualizada da `main` alterou 37 análises de pedidos, incluindo 25 que passaram de incompletos a prontos: são agora 256 prontos, 178 incompletos e 86 fora de escopo. Esses resultados são idênticos na `main` e na candidata da #144; a melhoria dos pedidos pertence às mudanças anteriores da `main`, e o efeito desta entrega sobre os pedidos continua sendo zero. O relatório preserva a comparação histórica e acrescenta os hashes e resultados dessa revalidação.

Os testes cobrem as linhas reais das tampas, marcas distintas, modelo/revisão, PN contraditório, sufixos, medidas diferentes, consulta de NIPLE idêntico e invalidação da busca entre turnos. Rodar `uv run pytest` em `back/`, `api/` e `mcp/`; API e MCP usam `TEST_DATABASE_URL` de um banco descartável terminado em `_test`, conforme o AGENTS.md.

Este complemento é entregue pela #144 sobre a correção da #73, já integrada à `main` pelo PR #74. A homologação humana dos casos inconclusivos continua pendente na #113.
