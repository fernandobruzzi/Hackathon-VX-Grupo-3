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

## Limites e integração pendente

Sem o snapshot oficial da #30, `exists_in_snapshot` e `valid_in_snapshot` são
`null`, com `OFFICIAL_SNAPSHOT_UNAVAILABLE`. Informar `ncm_version` é recusado,
pois essa versão não foi carregada. O PDM não é apresentado como tabela oficial.

A integração com a #20 ainda deve vincular a avaliação ao changeset persistido,
reavaliar atributos alterados e manter a proposta `PENDING` até todas as revisões
exigidas estarem aprovadas. Este trabalho não implementa nem modifica o fluxo
de aprovação. A #22 permanece aberta até essa integração ser verificada.

Verificação local: `uv run pytest` em `back/` e `mcp/`. Os testes do MCP chamam
a ferramenta pelo protocolo stdio real, sem AWS e sem credencial de escrita.
