# Enriquecimento: piloto por família e evidência — plano de implementação

> **For agentic workers:** implementação em frentes independentes com TDD; revisão integrada ao final. Não fazer merge.

**Goal:** Ampliar o PR #272 com recuperação de informação existente, fontes complementares, diagnóstico acionável e avaliação por atributo.

**Architecture:** Reutilizar classificador, extrator, PDM, identidade e aprovação atuais. Documentos adicionais são arquivados com hash e vinculados ao dataset; IA opcional propõe leituras citadas para revisão, sem criar identidade ou fatos por inferência. Valores aprovados e originais permanecem rastreáveis.

**Tech Stack:** Python 3.12, boto3/Bedrock opcional, PostgreSQL/SQLAlchemy, Next.js/TypeScript. Sem novas dependências.

**Spec:** solicitação do usuário para implementar as seis melhorias discutidas, localmente e no PR #272, sem merge; docs/enriquecimento-interno.md.

## Restrições

- Nenhum merge em homologacao ou main. Atualizar apenas o PR existente.
- PDM valida estrutura; valores precisam de documento ou confirmação humana.
- Não relaxar identidade, combinar produtos conflitantes ou propagar propostas pendentes como fonte.
- Pesquisa externa de produto continua restrita aos 15 códigos reais; documentos adicionais são fontes internas fornecidas.
- IA desativada por padrão; chamadas exigem modelo e orçamento configurados. Medição padrão não chama modelo nem inventa custo/precisão.
- Preservar medições históricas e rotulagem congelada. Publicar novo artefato comparativo.

## Frentes e interfaces

### 1. Recuperação determinística

- [ ] Testes RED/GREEN para aliases inequívocos e leitura independente de descrição longa/curta/estruturados.
- [ ] Compartilhar `extract_material_fields` entre saneamento e validação da origem; conflitos não confirmam identidade.
- [ ] Regressões nas classes PDM110, PDM050 e PDM001 e famílias reconhecíveis sem inventar liga/acabamento/conexão.

### 2. Fontes documentais internas

- [ ] Loader versionado de bundle `internal-documents-v1`, dataset_id e documentos com id/título/texto.
- [ ] Rejeitar identificadores duplicados, escopos inválidos, tipos externos e campos desconhecidos; não buscar URLs.
- [ ] CLI arquiva bytes em `references/internal-sources/<dataset>/<sha256>.json`; relatório e aprovação vinculam chave/hash.
- [ ] Fontes novas não alteram os originais, não atestam aprovação por autodeclaração e não usam propostas como evidência.

### 3. Leitura assistida opcional

- [ ] Cliente Bedrock Converse com injeção do cliente para testes, limites de entrada/saída e validação de resposta.
- [ ] Candidato informa atributo, valor, campo de origem e trecho literal; valor deve ser sustentado pela leitura PDM do trecho.
- [ ] Orçamento de chamadas explícito, uso registrado e nenhuma chamada padrão; candidatos seguem para complemento humano.

### 4. Diagnóstico, tratamento e revisão

- [ ] Separar status do classificador, conflitos dentro do registro/entre fontes e causas por atributo.
- [ ] Gerar perguntas direcionadas e mostrar causas/candidatos na pendência, com contrato/tipos atualizados.
- [ ] Integrar documentos novos e IA limitada ao batch/relatório sem publicação automática de candidatos de IA.
- [ ] Pacote congelado de revisão por atributo e avaliação SUPPORTED/UNSUPPORTED/INCONCLUSIVE com identidade/evidência vinculadas.

### 5. Verificação e publicação

- [ ] Medição integral comparada ao artefato anterior, com modelo desligado e amostras inspecionadas.
- [ ] Back, MCP e API completos; PostgreSQL para API/MCP; contratos, tipos, front, build e estilo.
- [ ] Revisão independente, correções verificadas, commit e push na branch do PR #272; atualizar descrição. Sem merge.

## Foco da revisão

Descrição curta contraditória/truncada; alias ambíguo; documento de outro dataset ou bytes alterados; trecho de IA ausente/não comprovante; propagação circular; fonte externa em material fictício; mudança de referência durante aprovação; pacote de avaliação alterado ou revisão inconclusiva.
