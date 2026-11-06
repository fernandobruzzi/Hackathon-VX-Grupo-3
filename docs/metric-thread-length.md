# Notação métrica com passo explícito

`M12X1,75X50` inclui três termos: bitola, passo e comprimento. Quando a combinação bitola/passo não pertence aos valores do PDM, o extrator conserva a notação em `unresolved`, deixa bitola/comprimento/rosca pendentes e não produz identidade completa. Não reinterpreta o passo como comprimento nem presume rosca grossa. `M12X50` e o passo fino permitido `M12X1,5X50` continuam suportados.

A revisão `8` do extrator invalida a assinatura do índice. Após integrar, reconstrua somente o índice com `docker compose run --rm --build index`; não execute o batch de propostas como parte dessa reconstrução. Nenhuma proposta pendente antiga foi modificada por esta correção; exige revisão manual explícita.

As medições históricas de antes/depois, na base original desta implementação, em `measurements/metric-thread-length-150.json` cobrem 23.554 materiais e 520 pedidos, sem mudanças no kit daquela base; não são uma recontagem da `homologacao` atual: 10.846 materiais completos e 229 pedidos prontos com identidade. São cobertura e comparações internas, não precisão independente. Os pares conhecidos têm 59 identidades iguais, 1 diferente e 142 indecididas entre 202. Regressões controladas reproduzem os passos inválidos antes da correção e verificam pendência/identidade bloqueada, além dos casos suportados; o fluxo MCP e batch usa o mesmo extrator.
