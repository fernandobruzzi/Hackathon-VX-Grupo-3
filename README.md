# VX · Cadastro e saneamento de materiais

Solução do Grupo 3 para o Desafio 01 do Hackathon VX: sanear a base de materiais, padronizar novos cadastros e completar informações com fonte registrada.

O MVP está em construção. Veja o andamento nas [issues](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/issues) e nos [milestones](https://github.com/fernandobruzzi/Hackathon-VX-Grupo-3/milestones).

## Rodar

Requer [uv](https://docs.astral.sh/uv/) e Node 20.9 ou mais novo. Os dados já estão em `data/`. A API, o Agent e o MCP ainda estão em construção.

Back (testes e relatório de normalização da base):

```bash
cd back
uv run --locked pytest
uv run python cli.py normalization-report ../data/desafio01/01_base_materiais.csv
```

Front (protótipo navegável com dados mock, em http://localhost:3000):

```bash
cd front
npm ci
npm run dev
```

Tudo em containers, com Docker, em http://localhost:8000:

```bash
docker compose up --build
```

## Contribuir e validar

O fluxo é `branch de trabalho → homologacao → main` (produção). Antes de abrir
ou integrar um PR em `homologacao`, rode os testes localmente e registre no PR
os comandos, resultados e testes pulados. Não há CI remoto nessa etapa; a
validação completa roda apenas no PR de promoção de `homologacao` para `main`.
A branch de homologação é de integração; sua criação não implanta um ambiente AWS.

Da raiz, prepare o workspace e execute cada suíte Python separadamente:

```bash
uv sync --all-packages --locked
(cd back && uv run --locked pytest)
(cd mcp && uv run --locked pytest)
(cd api && uv run --locked pytest)
```

O `pytest` na raiz mistura arquivos de teste com o mesmo nome. Alterações em banco
ou busca também precisam dos testes com PostgreSQL; alterações de front precisam
dos checks npm. Veja os [comandos e regras](AGENTS.md#commands) e o
[runbook de integração e promoção](docs/devops.md).

## Documentação

- [Guia do time e dos agentes](AGENTS.md)
- [Arquitetura](docs/arquitetura.md)
- [Classificação PDM e avaliação](docs/classificacao.md)
- [Brainstorm](docs/brainstorm.md)
- [Front](front/README.md)
- [Dados](data/README.md)
