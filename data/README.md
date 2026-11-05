# Dados

`desafio01/` traz o kit do Desafio 01, sintético e de uso livre (ver `desafio01/LEIA-ME.md`).

| Arquivo | Conteúdo |
|---|---|
| `01_base_materiais.csv` | Base de materiais, 23.554 registros |
| `02_pedidos_cadastro.csv` | Pedidos de cadastro, 520 registros |
| `03_padrao_cadastro_PDM.xlsx` | Padrão descritivo de materiais, também usado nos testes do back |

Os dados ficam no repositório para que qualquer pessoa, inclusive a banca, consiga rodar o projeto só com um clone. Rever essa decisão quando o banco existir ([arquitetura](../docs/arquitetura.md)): a carga passa a ser feita pelo bootstrap.

Os `.xlsx` de 01 e 02 ficaram de fora porque têm o mesmo conteúdo dos `.csv`. Não edite estes arquivos: eles são a entrada original do pipeline.
