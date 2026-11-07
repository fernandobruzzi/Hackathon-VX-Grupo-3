# Atributos anteriores a rótulos inline

Em `parafuso sextavado M12 x 50 classe: 8.8 aco carbono zincado branco DIN 933`,
o trecho anterior a `CLASSE:` contém medidas do item. Ele não é o nome inteiro de
um campo e precisa continuar disponível ao extrator. O parser reconhece o rótulo
no fim desse trecho e usa a leitura por spans existente, preservando o prefixo,
a cauda e as evidências dos sete atributos. A mesma frase sem dois pontos produz
os mesmos valores.

Cabeçalhos compostos como `Código do fabricante:` conservam o tratamento anterior:
`DO` não se torna referência e o fabricante não é confundido com o código.
Rótulos no início, listas multilinha e valores de várias palavras continuam
funcionando. `8.8` permanece inteiro; `DIN 931.1` não vira `DIN 931`, e `ZINCADO`
genérico continua sem acabamento definido. Nenhuma tabela de aliases foi ampliada.

## Medição e limites

O [relatório completo](measurements/inline-label-prefix-198.json) compara o extrator
da base `746cbe5` (revisão `8`) com `9-inline-label-prefix-198`. PDM, classificador
`aliases_v1@2` e regras de identidade foram mantidos iguais nos dois lados.
O relatório registra hashes das entradas e dos dois fontes do extrator,
assinaturas das regras, antes/depois, evidência por valor e revisão textual.

A comparação foi feita em memória com `analyze_material` nos 23.554 materiais e
`analyze_order` nos 520 pedidos, incluindo anexos. As propostas foram reconstruídas
com `merge_proposals`, usando os mesmos candidatos e normalizador nos dois lados.
Não houve escrita em banco, alteração de estoque ou substituição de propostas.
Os arquivos das coortes históricas e seus rótulos foram preservados.

| Medida de desenvolvimento | Antes | Depois |
|---|---:|---:|
| Materiais completos segundo o PDM | 10.927 | 10.928 |
| Materiais incompletos | 7.002 | 7.001 |
| Materiais sem classe | 5.625 | 5.625 |
| Materiais com identidade calculada | 11.813 | 11.814 |
| Propostas MERGE em memória | 998 | 998 |
| Pedidos prontos para revisão | 256 | 256 |
| Pedidos incompletos | 183 | 183 |
| Pedidos fora do escopo | 81 | 81 |

Os quatro deltas foram revistos no texto original e recuperam somente quantidades
explícitas de condutores em cabos: `27406104 → 1`, `29181674 → 3`, `19387950 → 2`
e `18347105 → 1`. Cabeçalhos `NR CONDUTORES:` e `NUMEOR CONDUTORES:` contêm o
rótulo reconhecível e o número escrito. Não se completam cor, tensão ou isolamento
ausentes. Somente o primeiro material se torna completo; os demais continuam
pendentes. Testes usam essas linhas reais do kit.

Todos os 520 pedidos mantêm atributos, identidades e resultados anteriores.
Nenhuma das 998 propostas de MERGE foi adicionada, retirada ou alterada. A coorte
fixa da identidade conserva os mesmos resultados; seu hash e o da coorte de pares
estão no relatório. Os testes de regressão incluem pedidos reais com cabeçalho de
fabricante, inclusive um caso que continua sem referência inequívoca.

Esta é uma revisão textual de desenvolvimento, sem especialista independente.
Completude no PDM e uma identidade calculada não comprovam que dois produtos sejam
fisicamente iguais nem estimam a precisão das propostas.

## Integrar e verificar

A revisão altera a assinatura do índice. Reconstrua **somente o índice**:

```bash
docker compose run --rm --build index
```

Não execute o saneamento como parte dessa reconstrução. Propostas antigas
pendentes permanecem para revisão manual explícita; não são invalidadas em massa.

Testes específicos, de cada diretório:

```bash
cd back
uv run --locked pytest tests/test_inline_labels.py tests/test_extraction.py
cd ../mcp
uv run --locked pytest tests/test_label_boundaries_flow.py
```

O segundo comando usa o servidor MCP real em subprocesso. Antes do PR, executar
também as três suítes completas conforme `AGENTS.md`, com PostgreSQL nas integrações.
