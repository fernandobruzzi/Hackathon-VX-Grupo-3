# Dados

`desafio01/` traz o kit do Desafio 01, sintético e de uso livre (ver `desafio01/LEIA-ME.md`).

| Arquivo | Conteúdo |
|---|---|
| `01_base_materiais.csv` | Base de materiais, 23.554 registros |
| `02_pedidos_cadastro.csv` | Pedidos de cadastro, 520 registros |
| `03_padrao_cadastro_PDM.xlsx` | Padrão descritivo de materiais, também usado nos testes do back |

Os dados ficam no repositório para que qualquer pessoa, inclusive a banca, consiga rodar o projeto só com um clone. Rever essa decisão quando o banco existir ([arquitetura](../docs/arquitetura.md)): a carga passa a ser feita pelo bootstrap.

Os `.xlsx` de 01 e 02 ficaram de fora porque têm o mesmo conteúdo dos `.csv`. Não edite estes arquivos: eles são a entrada original do pipeline. O comando `vx-bootstrap` os carrega no banco, e o `docker compose up` já faz isso.

## Benchmark de NCM

[`benchmark_ncm/v1/`](benchmark_ncm/v1/README.md) contém as bases com e sem gabarito documental de parafusos, válvulas e anéis: 6.271 cadastros pareados, 5.908 pontuáveis e 363 pendentes de revisão técnica. O manifesto registra versão, fontes, limites e hashes. Esses derivados não alteram o kit original do desafio.

[`benchmark_ncm/v2/`](benchmark_ncm/v2/README.md) amplia a referência documental para todos os 23.554 cadastros dos 15 grupos e 80 famílias, com bases pareadas, gabaritos por grupo, resumos e pendências técnicas explícitas. São 13.932 NCMs pontuáveis e 9.622 casos para revisão. A v1 permanece congelada.
