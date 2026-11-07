# Quantidade solicitada e referência de fabricante

O extrator não usa expressões de quantidade para preencher `REFERENCIA FABRICANTE`.
`preciso de 20 unidades`, com ou sem fabricante, mantém a referência ausente.
O mesmo vale para quantidades com `QTD`, `QTDE`, `QUANTIDADE`, unidades de peça e
pedidos diretos como `solicito 2000`. O número continua no texto não resolvido;
nenhuma quantidade de estoque é criada ou alterada.

A recusa considera o texto normalizado anterior à separação dos rótulos. Assim,
`QUANTIDADE: 2000` não perde o cabeçalho para depois virar o código `2000`.
Ela se aplica à inferência sem rótulo. Campos estruturados e referências explícitas,
como `REF 123-4567`, `REF: 000020` e `PN 2000`, conservam valor e evidência.
Um código numérico sem contexto de quantidade também continua reconhecido.

A regra continua exigindo um único candidato antes dessa recusa. Descartar uma
quantidade não autoriza escolher outro código entre candidatos ambíguos. Modelos
de equipamento continuam distintos de referências de peça. O chat conserva uma
referência válida já confirmada quando o próximo turno só informa a quantidade;
sem referência, a identidade permanece incompleta e não libera o envio.

## Medição e verificação

O [relatório](measurements/quantity-reference-199.json) registra os hashes das
entradas, fontes do extrator e coortes, as assinaturas compartilhadas e todos os
deltas. A comparação usa `analyze_material` nos 23.554 materiais originais e
`analyze_order` nos 520 pedidos, incluindo anexos, mantendo PDM, classificador,
identidade, candidatos e normalização iguais nos dois lados.

Nenhum valor, identidade ou resultado do kit mudou. As 998 propostas MERGE em
memória mantiveram os mesmos membros e conteúdo: nenhuma adicionada, retirada ou
alterada. As coortes e os rótulos históricos foram preservados. Os novos cenários
são regressões de conversa; não estimam a frequência desse erro no cadastro.
Não houve escrita no banco nem alteração de propostas persistidas.

Testes específicos, de cada diretório:

```bash
cd back
uv run --locked pytest tests/test_quantity_reference.py tests/test_extraction.py
cd ../mcp
uv run --locked pytest tests/test_quantity_reference_flow.py
```

Os testes incluem referências numéricas legítimas, zeros à esquerda, referência
estruturada, ambiguidade, modelo de equipamento, identidade incompleta e dois
turnos usando o servidor MCP real. Executar também as três suítes completas de
`AGENTS.md`, com PostgreSQL nas integrações, antes do PR.

## Reconstrução do índice

A revisão `11-quantity-reference-199` altera a assinatura das regras. Reconstrua
**somente o índice**, sem iniciar um novo saneamento:

```bash
docker compose run --rm --build index
```

Propostas antigas pendentes continuam para revisão manual explícita; essa
reconstrução não as invalida em massa nem as aplica.
