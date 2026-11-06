# Consistência de NCM pelo PDM

A função `domain.ncm_rules.check_ncm_consistency` e a tool MCP de mesmo nome
avaliam o formato do NCM e a coerência com `NCM_REFERENCIA` do PDM. Não escrevem
no cadastro, não concedem aprovação e não substituem o Auditor fiscal.

Exemplo da tool:

```json
{
  "pdm_class_id": "PDM003",
  "attributes": {"TIPO": "SEXTAVADA", "BITOLA": "M16"},
  "ncm": "7318.15.00",
  "pdm_version": "pdm-kit-v1"
}
```

O resultado é `INCONSISTENT`, sugere `7318.16.00` e exige revisão fiscal.
NCM vazio ou malformado mantém o original e recebe `UNDETERMINED`. Uma mudança
de formatação também exige revisão se for persistida. `CONSISTENT` significa
somente concordância com o PDM, sem confirmar a tabela oficial.

As 11 classes com múltiplos códigos usam condições explícitas: material e reforço
de mangueiras; comprimento externo de correias; material de juntas; substantivo,
material e conexão de conexões; material, costura e diâmetro de tubos; material
de luvas; biqueira; tipo de disco; substantivo de filtros; aplicação e exceções
por substantivo em sobressalentes. Informe `item_name` quando houver vários nomes.
Falta de informação, valores não previstos e regras alteradas deixam a decisão
pendente. Não se deduz circunferência de uma referência comercial de correia.

O resultado registra versão e hash do PDM, aba de origem, versão do avaliador e
`evaluation_hash`, calculado sobre classe, atributos, substantivo, NCM original
e versões. Mudar esses dados exige nova avaliação. As regras condicionais são
vinculadas ao hash de seu texto de referência; uma atualização exige revisão.

## Referência adotada e limites

Sem o snapshot oficial da #30, `exists_in_snapshot` e `valid_in_snapshot` são
`null`, com `OFFICIAL_SNAPSHOT_UNAVAILABLE`. Informar `ncm_version` é recusado,
pois essa versão não foi carregada. O PDM não é apresentado como tabela oficial.

## Do batch às revisões

`sanitize-report` inclui `NCM_CORRECTION` nas contagens de correções. `sanitize`
persiste essas propostas pelo mesmo contrato `proposal-v1`, inclusive nos jobs
retomáveis. Só materiais ativos, de classe confirmada pelo nome inicial e com
PDM completo recebem proposta. Condição não resolvida ou vários códigos possíveis
não são escolhidos por suposição.

O original permanece no membro e em `changes.before`; `changes.after` traz o
código proposto. `ncm_before_assessment` e `ncm_assessment` registram as avaliações,
origem, versão, hash e atributos, vinculados ao hash da proposta. A proposta exige
revisão fiscal e técnica: a interpretação PDM que sustenta o NCM também deve ser
conferida. O batch não aprova, altera cadastros nem muda os snapshots originais.

Na interface, entre como Governança e abra Saneamento para a revisão técnica.
Depois entre como Fiscal: a fila abre na área fiscal. O detalhe diferencia formato,
coerência e existência/vigência desconhecidas, e mostra a origem e versão do PDM.
As decisões continuam no endpoint da #20, com sessão, RBAC, escopo, justificativa,
versão observada e idempotência. O estado só passa a `APPLIED` com todas as
revisões exigidas aprovadas, em qualquer ordem.

A API reavalia classe, nome, atributos e NCM antes de cada aprovação. Um código
da união de referências da classe não basta se sua condição é incompatível.
Alterar uma base fiscal sem renovar a avaliação retorna `NCM_ASSESSMENT_CHANGED`.
Mudanças de conteúdo após uma primeira decisão também invalidam o vínculo da
aprovação anterior; é necessário gerar outra proposta e revisar novamente.
Propostas legadas sem avaliação armazenada são conferidas pelo mesmo motor,
preservando o vínculo existente do hash aos atributos e à referência PDM.
Cada evento de aprovação registra a avaliação efetivamente conferida na auditoria.

## Reprodução local

Do diretório `back/`, sem banco, AWS ou credenciais:

```bash
uv run vx-back sanitize-report ../data/desafio01/01_base_materiais.csv --pdm-workbook ../data/desafio01/03_padrao_cadastro_PDM.xlsx
```

Com o Compose e as três contas locais configurados conforme
[`aprovacoes.md`](aprovacoes.md), execute `docker compose run --rm --build batch`
para popular a fila. Os números são propostas, não mudanças aplicadas nem ganhos.

Verificação: `uv run pytest` em `back/`, `mcp/` e `api/`; configure o PostgreSQL
de teste para verificar o ciclo completo. Os testes da API exercitam a proposta
da porca produzida pelo batch, ambas as ordens de revisão, ausência de autorização
fiscal, atributo alterado e avaliação na auditoria. A ferramenta MCP é chamada
pelo protocolo stdio real, sem AWS e sem credencial de escrita no cadastro.
