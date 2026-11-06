# Notação métrica com passo explícito

`M12X1,75X50` inclui três termos: bitola, passo e comprimento. Quando a combinação bitola/passo não pertence aos valores do PDM, o extrator conserva a notação em `unresolved`, deixa bitola/comprimento/rosca pendentes e não produz identidade completa. Não reinterpreta o passo como comprimento nem presume rosca grossa. `M12X50` e o passo fino permitido `M12X1,5X50` continuam suportados.

Com rótulos como `BITOLA:` ou `DIAMETRO`, a notação inteira também chega ao leitor métrico: nem a busca por um enum contido nem o ajuste do maior prefixo podem reduzi-la a `M12`. O passo fino suportado é preservado; um comprimento informado separadamente continua disponível mesmo quando o passo fica pendente.

A revisão `8` do extrator invalida a assinatura do índice. Após integrar, reconstrua somente o índice com `docker compose run --rm --build index`; não execute o batch de propostas como parte dessa reconstrução. Nenhuma proposta pendente antiga foi modificada por esta correção; exige revisão manual explícita.

As medições históricas de antes/depois, na base original desta implementação, em `measurements/metric-thread-length-150.json` cobrem 23.554 materiais e 520 pedidos, sem mudanças no kit daquela base; não são uma recontagem da `homologacao` atual: 10.846 materiais completos e 229 pedidos prontos com identidade. São cobertura e comparações internas, não precisão independente. Os pares conhecidos têm 59 identidades iguais, 1 diferente e 142 indecididas entre 202. Regressões controladas reproduzem os passos inválidos antes da correção e verificam pendência/identidade bloqueada, além dos casos suportados; o fluxo MCP e batch usa o mesmo extrator.

## Conferência após o rebase em homologação

A [medição atual](measurements/metric-thread-length-rebase-150.json) compara o extrator da base `00f70cd` com a revisão `8`, incluindo a proteção de rótulos. O mesmo classificador e PDM foram usados dos dois lados, sem gravar no banco. A base de 23.554 materiais conserva os valores dos atributos, os estados (10.883 VALID, 7.074 INCOMPLETE e 5.597 SEM_CLASSE) e todas as chaves de identidade. Nove registros passam a conservar apenas a palavra do rótulo (`DIAMETRO` ou `BITOLA`) em `unresolved`; todos os nove deltas foram conferidos e estão no JSON, sem alteração dos campos técnicos.

Os 520 pedidos conservam atributos, identidades e resultados: 256 prontos para revisão, 178 incompletos e 86 fora do escopo. Isso é uma comparação de desenvolvimento, não precisão independente nem autorização para consolidar propostas. As regressões controladas demonstram a correção das entradas rotuladas que não aparecem no kit.
