# Evidências de qualidade para o pitch

O saneamento foi avaliado em **coortes de desenvolvimento**, não por revisão
independente de especialista. O método, os hashes, os denominadores e os erros
estão no [relatório de avaliação](../../docs/avaliacao-saneamento.md).

Frase para o roteiro: “A mesma regra é usada no lote e no chat; casos incertos
seguem para revisão humana, e nossas medições atuais são de desenvolvimento.”

- A coorte histórica de 40 grupos tem três casos de revisão de peça inconclusivos.
  Os dois erros conhecidos ficam registrados até serem corrigidos na #73.
- A coorte nova após aliases é publicada separadamente: não soma seus casos aos
  históricos nem apaga o histórico de erros.
- O acerto em pares escolhidos para regressão não é precisão de produção. Ao
  mencionar uma taxa, citar a coorte, a unidade e seu numerador/denominador.
- A aceitação de atributos pelo PDM não é validação física do produto. A avaliação
  técnica dirigida registra também ausências e preenchimentos sem suporte no texto.
- Recuperar redirecionamentos conhecidos não mede recall de todas as duplicidades.
- O dashboard deixa precisão e recall indisponíveis enquanto não houver evidência
  independente homologada. Nenhum desses números autoriza unificação automática.

A homologação independente está registrada na #113, após a correção de identidade.
