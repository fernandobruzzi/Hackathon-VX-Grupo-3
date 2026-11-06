# Identidade de materiais compartilhada

## Regra aprovada

Só propor unificação quando as evidências representam a mesma peça, sem contradição técnica. Similaridade recupera candidatos; não comprova identidade. A decisão tem três resultados: mesmo material, materiais diferentes ou revisão necessária. Equivalência e substituição não autorizam unificação.

Pela especificação, comparar classe, substantivo/qualificador e atributos de identidade do PDM. Nas classes por referência, comparar fabricante e PN genuíno, preservando as restrições de modelo, revisão e evidência contraditória da #73. Fabricantes distintos permanecem separados. Dados ausentes não comprovam igualdade; referências coincidentes não vencem nomes ou atributos contraditórios.

TAMPA PRESSAO 25187467 e TAMPA MOLA 21290535 (SULZER/916678-994) exigem revisão. Óleos PETRONAS/MOBIL ficam separados; BUCHA/RODA GUIA não se identificam pelo modelo 6030. REV A continua pendente de evidência técnica, conforme decisão do usuário.

## Abordagem

Reutilizar a identity-v2 do PR #74 e acrescentar uma decisão de par no domínio, consumida pelo batch, busca e aprovação. Preservar o substantivo na pesquisa e na assinatura de reutilização do chat/API (#144). Uma chave igual, isoladamente, não vence contradições. A aprovação reavalia também evidências do cadastro atual.

Usar apenas a chave de fabricante/PN mantém a falha das tampas. Exigir revisão humana de todos os pares perde duplicidades já verificáveis; a regra conservadora retém somente os casos sem confirmação suficiente.

## Limites

Não adicionar LLM, dependências, migrações ou aprovação automática. Embeddings continuam apenas como recuperação de candidatos. Estoque original permanece imutável; conversão de unidades e NCM continuam com seus controles próprios. Nenhuma proposta aplicada será alterada e nenhuma pendência será cancelada automaticamente.

## Entrega e validação

Complemento da #144, atribuída a hugo-antunes19, usando a correção da #73 já integrada pelo PR #74. Registrar a regra de negócio, testes reais/controles positivos, medição sobre coortes congeladas e motivos de abstenção. Dados de desenvolvimento não são homologação independente. Entregar em PR próprio contra main, preservando a autoria e a implementação integrada do #74.
