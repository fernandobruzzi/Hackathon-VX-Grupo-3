# Polegadas decimais menores que um

O extrator representa `0,5POL`, `0,25POL` e `0,75POL` como `1/2POL`, `1/4POL` e `3/4POL`. A parte inteira zero não forma uma medida mista. `1,5POL` continua como `1.1/2POL`. Valor original e regra permanecem na evidência. Decimais não suportados não são reinterpretados pelo sufixo inteiro depois da vírgula; não há aproximação para frações.

A revisão `7` preserva as regras de rótulos e identidade já integradas e muda a assinatura do índice. Reconstrua somente o índice com `docker compose run --rm --build index` após integrar. Não execute o saneamento para essa etapa: propostas pendentes antigas continuam disponíveis para revisão manual explícita.

`measurements/decimal-inches-151.json` conserva a medição histórica de antes/depois dos 23.554 materiais e dos 520 pedidos na base original desta implementação; não é uma recontagem da `homologacao` atual. Naquela medição, os resultados foram idênticos no kit, que não contém as grafias corrigidas: 10.846 materiais VALID, 7.111 INCOMPLETE e 5.597 SEM_CLASSE; pedidos 229 prontos com identidade, 205 incompletos, 86 fora do escopo. Pares conhecidos: 59 iguais, 1 diferente e 142 indecididos / 202. Estes números medem cobertura e comparação interna, não precisão independente. Regressões controladas verificam medidas, evidência e identidade equivalente, inclusive pelos fluxos chat e batch.
