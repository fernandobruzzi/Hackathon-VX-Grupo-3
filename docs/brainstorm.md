# Brainstorm do produto: Desafio 01

Respostas iniciais do time às perguntas do briefing.

## Quem convive com esse problema no dia a dia, e do que essa pessoa precisa para confiar no resultado?

Estoque e fluxo de mercadoria, suprimentos, gestão de materiais, compras, almoxarifado. Todas as equipes de qualquer empresa realizam solicitações de bens para a própria empresa ou outras empresas.

## O que faz dois registros serem o mesmo item? E quando parecem iguais, mas não são?

- Mesmo item: têm as mesmas características, como tamanho, cor, marca e ano (metadados).
- Parecem iguais, mas não são: qualquer característica muda, mesmo que seja somente uma.

## O que custa mais caro: juntar dois itens diferentes ou deixar uma duplicidade passar?

Juntar dois itens diferentes é mais caro. Entregar um item de uma categoria diferente da solicitada é mais penoso do que entregar um item da mesma categoria com uma cor diferente, por exemplo.

## Quando falta uma informação, onde buscar, e como saber se a fonte é confiável?

Tabela NCM disponível em portalunico.siscomex.gov.br. Caso o sistema ainda tenha dúvidas, buscar confirmação com quem fez a solicitação do pedido. Informações adicionais sobre o produto podem ser achadas no PDM (Padrão Descritivo de Materiais).

## Quando a decisão pode ser automática, e quando precisa de alguém validando?

Automática a partir de um certo limiar de confiança; caso contrário, exigir validação manual.

> Em aberto: a arquitetura exige aprovação humana. Decisão acompanhada na [issue #36](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/issues/36).

## Vale mais corrigir o que já existe ou impedir que o erro entre?

Depende: qual o tamanho da base, qual o fluxo de entrada, em que momento vale mais corrigir ou impedir a entrada, e qual a capacidade de sanitizar o que já existe.

Temos 23.554 registros na base e 520 pedidos de cadastro, portanto é mais importante corrigir o que já está na base. Assim que conseguirmos corrigir, vale atacar as novas entradas.

## Como provar que a base ficou melhor?

Percentual de cache hit. Mostrar o que acontece em situações-problema:

- Registrar um item com pouca informação: notificação exigindo mais detalhes.
- Registrar um item parecido com algum do banco: evitar duplicata, adicionando só depois de um check com quem tenta cadastrar.
- Mostrar como conseguimos evitar que erros ocorram.

## Ideias

- Regex.
- Regex modificado de acordo com o que aprendemos, com verificação humana.
- Tokenizar dados, porque dados similares como PREGO e PRG vão cair no mesmo token.
- RAG.
- Genie Code → SQL.
- Embedding.
