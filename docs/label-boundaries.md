# Rótulos em frases sem separadores

Em `parafuso sextavado M12 x 50 classe 8.8 aco carbono zincado branco DIN 933`,
`CLASSE` consome somente `8.8`; material, acabamento e norma continuam disponíveis
para extração. Um valor contido em uma frase não prova que a frase inteira seja
seu valor. Prefixos também não podem ganhar palavras qualificadoras ausentes.
Valores inteiros de várias palavras, como `ACO CARBONO` e `GALVANIZADO A FOGO`,
continuam juntos. As regras anteriores de palavras equivalentes permanecem para
o valor inteiro de um rótulo, sem consumir uma cauda de outros atributos.

O usuário confirmou que `ZINCADO` genérico deve manter o acabamento pendente e
que o exemplo completo deve usar `ZINCADO BRANCO`. `ZINCADO A FOGO` também não é
valor do PDM fornecido; nenhuma dessas grafias vira um subtipo por suposição.
O valor permitido de banho a quente é `GALVANIZADO A FOGO`. O PDM original não foi
alterado. A frase genérica ainda recupera classe, material e norma, mas pede a
qualificação do acabamento.

A revisão de todos os deltas encontrou dois riscos ao liberar as caudas: uma
fração do comprimento misto virava bitola, e `PTFE REFORCADO` perdia o qualificador.
O enum agora não consome uma fração interna da medida mista. A expressão completa
`PTFE REFORCADO` preserva `RPTFE`, equivalente ao alias já existente de
`TEFLON REFORCADO`; o qualificador está escrito, sem inferência adicional.
Frases contraditórias ou incompletas de terminais continuam pendentes.

A revisão `6-label-boundaries-159` integra também a revisão `5` da identidade compartilhada e altera a assinatura do índice. Depois de integrar,
reconstrua somente o índice com `docker compose run --rm --build index`. Não rode
o saneamento como etapa dessa reconstrução: propostas antigas pendentes ficam
para revisão manual explícita e não devem ser invalidadas em massa.

## Medição e revisão de desenvolvimento

A base fixa foi `03ff9a6`, já com identidade da #73 e pontuação da #121. O relatório
[de valores e propostas](measurements/label-boundaries-159.json) conserva antes/depois,
evidência de cada um dos 310 valores alterados em 247 materiais e a revisão textual
dos 11 grupos MERGE novos, 12 com conteúdo atualizado e dois grupos anteriores
ampliados. Os registros antigos e as coortes congeladas não foram relabelados.
Nenhuma proposta persistida foi alterada: esta análise foi somente em memória.

- Base de 23.554 materiais: VALID 10.877 → 10.989; INCOMPLETE 7.080 → 6.968;
  SEM_CLASSE permanece 5.597. Há 111 identidades diferentes entre antes/depois.
- Pedidos: todos os 520 mantêm os mesmos atributos, identidades e resultados:
  256 prontos, 178 incompletos e 86 fora de escopo.
- Conferência interna por colunas: fabricante 5.259/5.259 → 5.291/5.291 corretos;
  referência permanece 4.406/4.512. Isso não é avaliação independente de precisão.
- Pares conhecidos: 53 → 54 com identidade igual, um diferente e 148 → 147
  indecididos, entre 202 pares.
- MERGEs em memória: 1.049 → 1.058. Os dois grupos de óleo sem fabricante foram
  registrados como inconclusivos para identidade física, mantendo revisão manual;
  os demais grupos têm suporte textual e os conflitos de unidade/NCM/PDM continuam.
- Dez valores foram deixados pendentes, em vez de completar terminais, material
  ou bitola a partir de partes de uma expressão. Os códigos e motivos estão no relatório.

A revisão foi feita durante o desenvolvimento pelo próprio autor, lendo todos os
textos/valores alterados e os grupos afetados. Não é validação de especialista ou
medida independente. Ganho de cobertura não é prova de acerto.
