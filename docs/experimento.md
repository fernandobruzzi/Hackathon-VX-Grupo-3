# Experimento manual × solução

Responde com números a três perguntas: o que faz dois registros serem o mesmo item, o que faz
parecerem iguais sem ser, e se a base fica melhor. Duas pessoas revisam às cegas uma amostra do kit,
e o resultado é comparado com o que o sistema decidiu. Complementa a revisão independente das
unificações da #113 e segue as regras da [avaliação de desenvolvimento](avaliacao-saneamento.md).
Nada aqui altera dados, propostas ou decisões.

## O que o revisor recebe

Uma planilha com quatro abas, gerada a partir de um commit, dos dados e de uma semente fixos:

| Aba | Conteúdo | Pergunta |
|---|---|---|
| Como revisar | Instruções, identificador do pacote e o nome do revisor | — |
| Mesmo item | 80 casos misturados: **A**, 40 unificações propostas pelo sistema; **B**, 40 grupos de controle contendo um par vizinho não proposto | SIM, NAO ou NAO SEI, com a evidência |
| Descrição | 40 correções de descrição de nível 2, as que vão para aprovação em lote | Está correta? Perdeu informação? |
| Manual | 120 parafusos sextavados (PDM001), com grupos de duplicidade escondidos | Agrupar à mão os que são o mesmo item, com cronômetro |

A planilha não diz a que parte cada caso pertence nem o que o sistema decidiu. Os pares iniciais de **B**
vêm das sugestões do `tokens_v1`, desligado porque uniria itens diferentes; o sorteio sai dos 200
pares mais parecidos que o sistema não une. Cada controle B conserva esse par e recebe materiais
ativos da mesma classe prevista do primeiro membro, sorteados sem reposição dentro do grupo, até
igualar a cardinalidade de um grupo A. A distribuição de tamanhos A/B é idêntica; nenhum MERGE
é reduzido a um par. Se faltarem controles ou membros, a geração falha explicitamente.
A unidade é o **grupo inteiro**: SIM exige que todos sejam intercambiáveis. Os controles aumentados
não estimam precisão de pares vizinhos individuais. As sobreposições entre casos são permitidas;
a ausência de pistas estatísticas de conteúdo não está demonstrada por essa construção. A **chave** fica em outro
arquivo, `chave-<pacote>-NAO-ENVIAR.json`, e nunca vai aos revisores.

## Como rodar

Da pasta `back/`, gere o pacote:

```bash
uv run vx-back experiment-packets ../data/desafio01/01_base_materiais.csv --pdm-workbook ../data/desafio01/03_padrao_cadastro_PDM.xlsx --out-dir ../experimento
```

O resumo traz o identificador do pacote, a assinatura da análise e o tamanho de cada quadro de
sorteio. A semente padrão é 207; `--seed`, `--pairs`, `--corrections` e `--slice` mudam a amostra.
O mesmo commit, os mesmos dados e a mesma semente geram os mesmos casos, na mesma ordem, e o mesmo
identificador. Um commit com outras regras gera outro pacote: revise o pacote que foi gerado, sem
regerar no meio da sessão.

Com uma ou duas planilhas preenchidas, calcule o resultado:

```bash
uv run vx-back experiment-result ../experimento/chave-<pacote>-NAO-ENVIAR.json revisor1.xlsx revisor2.xlsx
```

O comando recusa uma planilha de outro pacote, uma chave cujo digest não confere, uma planilha sem o nome do
revisor e o mesmo nome normalizado duas vezes. Recusa também abas/colunas/linhas extras ou ausentes,
IDs duplicados, alterações de códigos ou textos protegidos e células de fórmula. Linhas completas
podem ser reordenadas preservando o ID e seu conteúdo. Textos originais iniciados por `=` são
exportados como texto literal.

O SHA-256 canônico vincula dados capturados uma vez, PDM, assinatura, código dos algoritmos,
exportação e pontuação, quadros de sorteio, seleção, tamanhos, semente e versão do layout. O hash
é uma verificação de consistência chave/planilha, sem autenticação criptográfica da autoria:
quem pode reescrever ambos pode recalcular o digest. Nomes diferentes não provam independência.

## Como conduzir a sessão

- **Quem pode revisar:** pessoas que não escreveram nem ajustaram as regras de classificação,
  extração, identidade ou correção. O ideal é alguém com experiência em manutenção, suprimentos ou
  almoxarifado. Duas pessoas de fora valem mais que cinco do time.
- **Às cegas:** cada revisor recebe sua cópia da planilha, sem a chave, e trabalha sem consultar o
  sistema, o código ou o outro revisor. Combinem o critério antes de começar, só a partir das
  instruções da planilha, e não discutam casos durante a sessão.
- **Tempo:** de 1 h a 1 h 30 nas abas Mesmo item e Descrição, e 40 minutos cronometrados na aba
  Manual. Anote o início e o fim no formato hh:mm.
- **Material:** a planilha e, se quiser, o `03_padrao_cadastro_PDM.xlsx` para consultar as classes.

## Como ler o resultado

| Campo | O que mede |
|---|---|
| `merges_proposed.precision` | Das unificações propostas e decididas, quantas eram mesmo o mesmo item |
| `similar_pairs_not_merged.correctly_kept_apart` | Dos grupos de controle decididos, quantos não eram todos o mesmo item |
| `similar_pairs_not_merged.missed_duplicates` | Grupos de controle que os revisores dizem serem todos o mesmo item |
| `lot_descriptions.correct` e `lost_information` | Correções de descrição em lote certas, e as que perderam informação |
| `manual_task` | Materiais agrupados por minuto e pares de duplicidade achados pela pessoa e propostos pelo sistema |
| `reviewer_agreement_on_pairs` | Com dois revisores, em quantos casos decididos pelos dois eles concordaram |
| `system_errors` | Cada caso em que os revisores discordam do sistema, com a evidência |

Cada taxa traz numerador, denominador e o intervalo de Wilson a 95% dos casos decididos. Com dois
revisores, um caso só conta quando os dois concordam; divergência ou "NAO SEI" deixam o caso
inconclusivo, sem voto de maioria, como na avaliação da #85. SIM/NAO exigem evidência textual
não vazia (Evidência ou O que); sem ela o rótulo válido fica inconclusivo. Rótulos fora das
opções da coluna são recusados, inclusive quando não têm evidência. GRUPO manual permanece
texto livre. Uma única revisão é identificada como tal, sem prova de independência.

A comparação manual usa somente os pares de MERGE efetivamente **propostos** e congelados na
chave, restritos aos códigos agrupados pela pessoa. Igualdade de chave de recuperação não é
uma decisão de MERGE. Nenhuma unificação aplicada é medida; `system_decision_kind` explicita isso.

Todos os experimentos humanos permanecem **pendentes**. Testes usam rótulos sintéticos e não
constituem resultados de revisão nem evidência de qualidade. O pacote real é entregue vazio.

## O que pode e o que não pode ser afirmado

Pode: "Em uma amostra sorteada do kit do desafio, revisada às cegas por duas pessoas que não
escreveram as regras, X de Y unificações propostas eram o mesmo item (intervalo de Wilson a 95%)",
e o mesmo para os pares parecidos e as correções em lote. O tempo manual pode ser comparado com o
tempo do sistema na mesma fatia.

Não pode: chamar o resultado de precisão em produção, de recuperação de todas as duplicidades da
base, ou estendê-lo a outra base. O kit é sintético, a amostra **B** foi escolhida entre os pares
mais parecidos, e a fatia manual é de uma classe só. Mudanças de regra depois da revisão exigem um
pacote novo; o resultado vale para a assinatura da análise registrada na chave.
