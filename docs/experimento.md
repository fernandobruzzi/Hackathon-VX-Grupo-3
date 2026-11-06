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
| Mesmo item | 80 casos misturados: **A**, 40 unificações propostas pelo sistema; **B**, 40 pares muito parecidos no texto que o sistema não une | SIM, NAO ou NAO SEI, com a evidência |
| Descrição | 40 correções de descrição de nível 2, as que vão para aprovação em lote | Está correta? Perdeu informação? |
| Manual | 120 parafusos sextavados (PDM001), com grupos de duplicidade escondidos | Agrupar à mão os que são o mesmo item, com cronômetro |

A planilha não diz a que parte cada caso pertence nem o que o sistema decidiu. Os pares de **B**
vêm das sugestões do `tokens_v1`, desligado porque uniria itens diferentes; o sorteio sai dos 200
pares mais parecidos que o sistema não une, que são os que confundem. A **chave** fica em outro
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

O comando recusa uma planilha de outro pacote, uma chave alterada, uma planilha sem o nome do
revisor e o mesmo revisor duas vezes.

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
| `similar_pairs_not_merged.correctly_kept_apart` | Dos pares parecidos que o sistema não uniu, quantos eram itens diferentes |
| `similar_pairs_not_merged.missed_duplicates` | Pares que o sistema deixou passar e os revisores dizem ser o mesmo item |
| `lot_descriptions.correct` e `lost_information` | Correções de descrição em lote certas, e as que perderam informação |
| `manual_task` | Materiais agrupados por minuto e pares de duplicidade achados pela pessoa e pelo sistema |
| `reviewer_agreement_on_pairs` | Com dois revisores, em quantos casos decididos pelos dois eles concordaram |
| `system_errors` | Cada caso em que os revisores discordam do sistema, com a evidência |

Cada taxa traz numerador, denominador e o intervalo de Wilson a 95% dos casos decididos. Com dois
revisores, um caso só conta quando os dois concordam; divergência ou "NAO SEI" deixam o caso
inconclusivo, sem voto de maioria, como na avaliação da #85.

## O que pode e o que não pode ser afirmado

Pode: "Em uma amostra sorteada do kit do desafio, revisada às cegas por duas pessoas que não
escreveram as regras, X de Y unificações propostas eram o mesmo item (intervalo de Wilson a 95%)",
e o mesmo para os pares parecidos e as correções em lote. O tempo manual pode ser comparado com o
tempo do sistema na mesma fatia.

Não pode: chamar o resultado de precisão em produção, de recuperação de todas as duplicidades da
base, ou estendê-lo a outra base. O kit é sintético, a amostra **B** foi escolhida entre os pares
mais parecidos, e a fatia manual é de uma classe só. Mudanças de regra depois da revisão exigem um
pacote novo; o resultado vale para a assinatura da análise registrada na chave.
