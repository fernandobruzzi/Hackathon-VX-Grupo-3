# Hackathon VX · Desafio 01 · Cadastro e saneamento de materiais

Pacote de dados para os times. Todos os dados são sintéticos e foram construídos para reproduzir os problemas de uma base real de materiais industriais. Nenhum dado é de cliente.

## A empresa

**Serra Azul Mineração e Energia S.A.** é uma empresa fictícia com operação de mineração, beneficiamento, terminal portuário e geração de energia. Os materiais estão cadastrados em um ERP e são usados por seis centros:

- 1100 - MINA SERRA AZUL
- 1200 - USINA DE BENEFICIAMENTO
- 1300 - TERMINAL PORTUARIO
- 2100 - UTE SERRA AZUL
- 2200 - PCH RIO CLARO
- 9000 - CD CENTRAL

## Arquivos

| Arquivo | O que é |
|---|---|
| `01_base_materiais.xlsx` e `.csv` | Base de materiais exportada do ERP, com 23.554 registros. A aba DICIONARIO_CAMPOS descreve cada coluna. |
| `02_pedidos_cadastro.xlsx` e `.csv` | 520 solicitações de cadastro, do jeito que chegaram ao time de cadastro. |
| `03_padrao_cadastro_PDM.xlsx` | O padrão descritivo de materiais (PDM) da empresa: regras, classes, atributos, unidades e NCM de referência. |

Os arquivos `.csv` têm o mesmo conteúdo das planilhas, em UTF-8, com vírgula como separador e ponto como separador decimal. Para abrir no Excel em português, use os arquivos `.xlsx`.

## Números

- 23.554 registros na base de materiais, em 44 classes do padrão.
- 520 pedidos de cadastro.

## Uso dos dados

Os dados são sintéticos e podem ser usados livremente, inclusive em ferramentas e modelos de IA externos.

## Observações

- A base é uma foto do ERP: tem o que foi cadastrado ao longo de mais de vinte anos, por pessoas e áreas diferentes.
- O padrão descritivo de materiais (PDM) descreve como um cadastro deveria ser, não como ele é hoje.
- Os últimos 15 registros da base (linhas 23.541 a 23.555 da planilha) são produtos reais de fabricantes conhecidos. Para eles, a informação que falta no cadastro pode ser encontrada em fontes públicas, como catálogos de fabricantes e de distribuidores. Quando usar uma fonte externa, registre de onde veio cada dado.
- Nos demais registros, as combinações de fabricante e código de peça são fictícias. Os formatos imitam os reais, então um código pode coincidir por acaso com um produto existente; nesse caso, a informação encontrada não vale para o item da base. O mesmo vale para os números de CA dos EPIs.
- Os NCMs do padrão seguem a tabela oficial da NCM. A tabela completa e vigente é pública e pode ser baixada no Portal Único Siscomex (portalunico.siscomex.gov.br, módulo Classif), e pode ser usada à vontade.
