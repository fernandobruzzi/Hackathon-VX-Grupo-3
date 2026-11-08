export interface paths {
  "/api/v1/auth/sso-start": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Iniciar login com state, nonce e PKCE. */
    get: operations["startSso"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/auth/config": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** getAuthConfig */
    get: operations["getAuthConfig"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/auth/local-session": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** createLocalSession */
    post: operations["createLocalSession"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/auth/logout": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** logout */
    post: operations["logout"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/auth/sso-callback": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Trocar código e criar sessão BFF. */
    post: operations["completeSso"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/auth/me": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Consultar identidade, permissões, escopo e CSRF. */
    get: operations["getMe"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/auth/demo/switch": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Trocar para sessão demo já autenticada do mesmo navegador. */
    post: operations["switchDemoSession"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/chat/message": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Executar turno e retornar chamadas MCP reais; não publica material. */
    post: operations["sendChatMessage"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/sanitization/queue": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Consultar propostas no escopo autorizado. */
    get: operations["listProposals"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/sanitization/{id}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Consultar detalhes da proposta e evidências. */
    get: operations["getProposal"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/sanitization/{id}/decide": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Decidir proposta persistida com auditoria e concorrência otimista. */
    post: operations["decideProposal"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/dashboard/metrics": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Consultar qualidade; executive exige metrics:financial. */
    get: operations["getMetrics"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/dashboard/snapshots": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Gerar snapshot posterior com as propostas aplicadas; exige batch:run. */
    post: operations["createQualitySnapshot"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/batch/jobs": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /**
     * Listar os jobs mais recentes e o dataset que um novo job usaria.
     * @description Histórico por created_at DESC e id ASC, com cursor opaco vinculado ao tenant e filtro de status. Cursor inválido recebe 422 INVALID_CURSOR. active_job acompanha o job ativo autorizado independentemente do filtro ou página.
     */
    get: operations["listBatchJobs"];
    put?: never;
    /**
     * Iniciar processamento por manifesto sem token do usuário.
     * @description Exige Idempotency-Key UUID. A mesma chave, usuário, tenant, recurso e corpo recuperam o mesmo job e seu estado atual, inclusive após conclusão ou falha de disparo, sem novo manifesto ou lançamento. Reuso em outro comando recebe 409 IDEMPOTENCY_CONFLICT. Acesso é revalidado em cada tentativa. Novos comandos de processamento suportam exatamente um dataset por empresa no MVP; múltiplas importações recebem 422 MULTIPLE_DATASETS_NOT_SUPPORTED antes de criar job, manifesto ou task. A retomada verifica a mesma condição. Repetir um comando já aceito somente recupera seu job, sem iniciar processamento.
     */
    post: operations["startBatchJob"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/batch/jobs/{id}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Consultar progresso, heartbeat, contagens e erro. */
    get: operations["getBatchJob"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/batch/jobs/{id}/resume": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /**
     * Reprocessar um job que falhou, continuando dos checkpoints, sem token do usuário.
     * @description Exige Idempotency-Key UUID. A mesma chave, usuário, tenant, recurso e corpo recuperam o mesmo job e seu estado atual, inclusive após conclusão ou falha de disparo, sem novo manifesto ou lançamento. Reuso em outro comando recebe 409 IDEMPOTENCY_CONFLICT. Acesso é revalidado em cada tentativa. Novos comandos de processamento suportam exatamente um dataset por empresa no MVP; múltiplas importações recebem 422 MULTIPLE_DATASETS_NOT_SUPPORTED antes de criar job, manifesto ou task. A retomada verifica a mesma condição. Repetir um comando já aceito somente recupera seu job, sem iniciar processamento.
     */
    post: operations["resumeBatchJob"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/registration-orders": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Listar pedidos próprios ou vinculados à revisão autorizada. */
    get: operations["listOrders"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/registration-orders/{id}/submit": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Encaminhar pedido próprio à revisão. */
    post: operations["submitOrder"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/registration-orders/{id}/decide": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Decidir publicação com nova checagem de duplicidade e requisitos fiscais. */
    post: operations["decideOrder"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/enrichment": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Listar propostas de enriquecimento autorizadas. */
    get: operations["listEnrichments"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/enrichment/{proposal_id}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Consultar atributos, fontes e divergências. */
    get: operations["getEnrichment"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/materials": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Buscar materiais e estoque dos centros autorizados. */
    get: operations["listMaterials"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/audit": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Consultar auditoria no escopo da sessão. */
    get: operations["listAuditEvents"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/internal/v1/chat/run": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Executar turno interno no Agent; API valida o retorno e persiste o turno. */
    post: operations["runAgentTurn"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/chat/{session_id}/submit": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Enviar a ficha persistida do chat para revisão, sem publicar material. */
    post: operations["submitChatOrder"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/sanitization/lots": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Listar lotes de correções de forma elegíveis para aprovação por amostra (Governança). */
    get: operations["listProposalLots"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/sanitization/lots/reviews": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Abrir a revisão de um lote e sortear a amostra; repetir devolve a revisão já aberta. */
    post: operations["openLotReview"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/sanitization/lots/reviews/{id}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Consultar a revisão de um lote e sua amostra. */
    get: operations["getLotReview"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/sanitization/lots/reviews/{id}/decide": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Decidir o lote: zero erros na amostra aplica cada proposta com auditoria própria; qualquer erro devolve o lote para a revisão individual. */
    post: operations["decideLotReview"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/chat/sessions": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Retomar conversas persistidas do usuário autenticado. */
    get: operations["listChatSessions"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/chat/sessions/{session_id}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Retomar conversas persistidas do usuário autenticado. */
    get: operations["readChatSession"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/manual-reviews": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Listar pendências por motivo e material, separadas das propostas. */
    get: operations["listManualReviews"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/manual-reviews/{review_id}/propose": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Encaminhar pendência à aprovação sem alterar o material. */
    post: operations["proposeManualReview"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/manual-reviews/catalog": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Consultar classes e atributos do PDM para revisão manual. */
    get: operations["manualReviewCatalog"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/registration-orders/{id}/complement": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Complementar pedido próprio ou importado no escopo da Governança, preservando os originais. */
    post: operations["complementOrder"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/registration-orders/{id}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Consultar ficha técnica, duplicidade e condições fiscais antes de decidir. */
    get: operations["getOrderReview"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/registration-orders/{id}/reopen-technical-review": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Governança reavalia pedido pendente fiscal e o devolve para nova revisão técnica. */
    post: operations["reopenOrderTechnicalReview"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/batch/jobs/{id}/automatic-corrections": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Consultar correções automáticas e motivos por proposta */
    get: operations["getAutomaticCorrections"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/batch/jobs/{id}/automatic-corrections/retry": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /**
     * Retomar erros e indexação sem rearmar o job
     * @description Exige Idempotency-Key UUID. A mesma chave, usuário, tenant, recurso e corpo recuperam o mesmo job e seu estado atual, inclusive após conclusão ou falha de disparo, sem novo manifesto ou lançamento. Reuso em outro comando recebe 409 IDEMPOTENCY_CONFLICT. Acesso é revalidado em cada tentativa. Novos comandos de processamento suportam exatamente um dataset por empresa no MVP; múltiplas importações recebem 422 MULTIPLE_DATASETS_NOT_SUPPORTED antes de criar job, manifesto ou task. A retomada verifica a mesma condição. Repetir um comando já aceito somente recupera seu job, sem iniciar processamento.
     */
    post: operations["retryAutomaticCorrections"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/material-requests": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Listar solicitações próprias e pendências da fila autorizada, limitadas aos centros. */
    get: operations["listMaterialRequests"];
    put?: never;
    /** Criar solicitação sem movimentar estoque; estado derivado no servidor. */
    post: operations["createMaterialRequest"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/material-requests/{id}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Consultar solicitação e histórico de transições no próprio escopo. */
    get: operations["getMaterialRequest"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/material-requests/{id}/cancel": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Cancelar solicitação própria e liberar suas reservas ativas; versão e motivo obrigatórios. */
    post: operations["cancelMaterialRequest"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/material-requests/{id}/reservations": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Listar reservas e parcelas da solicitação: próprio solicitante ou Almoxarifado do centro. */
    get: operations["listStockReservations"];
    put?: never;
    /** Reservar saldo do centro para a solicitação em atendimento; transacional, recusa (409) acima do disponível ou do pendente. */
    post: operations["reserveStock"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/stock/reservations/{id}/deliveries": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Confirmar a entrega total ou parcial de uma reserva ativa; move a quantidade de reservado para entregue sem alterar o disponível. */
    post: operations["deliverStockReservation"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/stock/reservations/{id}/cancel": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Cancelar uma reserva ativa, liberando só a parte reservada e não entregue. */
    post: operations["cancelStockReservation"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/stock/movements/{id}/reversal": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Reverter parte ou toda uma entrega com um movimento compensatório; nada é editado nem apagado. */
    post: operations["reverseStockDelivery"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/stock/availability": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Consultar a disponibilidade de um material num centro autorizado; não cria registros. */
    get: operations["getStockAvailability"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/material-requests/{id}/purchase-forwards": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Encaminhar para compras a quantidade pendente de material existente sem saldo; não cria pedido de cadastro. */
    post: operations["forwardMaterialRequestToPurchasing"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/material-requests/{id}/fulfillment-options": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Consultar a divisão entre reserva e compras do próprio solicitante; não grava nada. */
    get: operations["previewMaterialRequestFulfillment"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/material-requests/{id}/fulfillment": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Confirmar a escolha do solicitante na falta parcial (D1): reservar o disponível e encaminhar o restante para compras, ou encaminhar tudo; a divisão é recalculada na transação. */
    post: operations["confirmMaterialRequestFulfillment"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/purchase-forwards": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Fila de Compras: encaminhamentos dos centros autorizados (purchasing:read). */
    get: operations["listPurchaseForwards"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/purchase-forwards/{id}": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Consultar encaminhamento para compras de centro autorizado. */
    get: operations["getPurchaseForward"];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/purchase-forwards/{id}/accept": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Compras aceita a demanda encaminhada; não registra pedido ao fornecedor nem recebimento. */
    post: operations["acceptPurchaseForward"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/purchase-forwards/{id}/return": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Compras devolve o encaminhamento com motivo; a quantidade volta a ficar pendente na solicitação. */
    post: operations["returnPurchaseForward"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  "/api/v1/chat/{session_id}/request-material": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /**
     * Confirmar necessidade: material identificado, cadastro novo ou identificação em revisão, sem movimentar estoque.
     * @description Quantidade e unidade obrigatórias; centro e identidade vêm da sessão. Se há dúvida técnica de identidade, segue para identificação sem cadastro automático. Uma solicitação por conversa, com idempotência, versão, auditoria e transação única. Catálogo alterado exige novo turno.
     */
    post: operations["submitChatMaterialRequest"];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
}
export type webhooks = Record<string, never>;
export interface components {
  schemas: {
    NcmAssessment: {
      input_ncm: string | null;
      normalized_ncm: string | null;
      syntax_valid: boolean;
      exists_in_snapshot: boolean | null;
      valid_in_snapshot: boolean | null;
      technical_consistency: string;
      suggested_ncm_codes: string[];
      missing_attributes: string[];
      rule_id: string;
      requires_fiscal_review: boolean;
      fiscal_approval_status: string;
      pdm_version: string;
      pdm_source_sha256: string;
      reference_source: string;
      rules_version: string;
      evaluation_hash: string;
      pending_checks: string[];
      ncm_version: string | null;
      ncm_source_sha256: string | null;
      ncm_snapshot_date: string | null;
      ncm_source_kind: ("OFFICIAL_DOWNLOAD" | "IMPORTED_UNVERIFIED" | "SIMULATED") | null;
    };
    /** @enum {string} */
    Role:
      | "ROLE_SOLICITANTE"
      | "ROLE_GOVERNANCA_PDM"
      | "ROLE_AUDITOR_FISCAL"
      | "ROLE_DEV_TI"
      | "ROLE_ALMOXARIFADO"
      | "ROLE_COMPRAS";
    /** @enum {string} */
    PersonaLabel:
      | "SOLICITANTE_OPERACAO"
      | "GESTOR_CADASTRO"
      | "AUDITOR_FISCAL"
      | "DEV_TI"
      | "ALMOXARIFADO"
      | "COMPRAS";
    /** @enum {string} */
    Permission:
      | "chat:use"
      | "materials:read"
      | "inventory:read"
      | "orders:create"
      | "orders:read_own"
      | "orders:update_own"
      | "orders:decide"
      | "queue:read"
      | "queue:read_audit"
      | "merge:decide"
      | "enrichment:decide"
      | "ncm:decide"
      | "batch:run"
      | "metrics:quality"
      | "metrics:financial"
      | "audit:own"
      | "audit:technical"
      | "audit:fiscal"
      | "chat:diagnostics"
      | "requests:create"
      | "requests:read_own"
      | "requests:cancel_own"
      | "requests:read_queue"
      | "requests:read_fiscal"
      | "stock:reserve"
      | "stock:deliver"
      | "stock:reverse"
      | "purchasing:read"
      | "purchasing:handle";
    Me: {
      user: {
        /** Format: uuid */
        id: string;
        display_name: string;
        roles: components["schemas"]["Role"][];
      };
      permissions: components["schemas"]["Permission"][];
      scope: {
        center_codes: string[];
        /** @description Nomes dos centros autorizados no dataset vigente, indexados pelo código. Ausentes ou contraditórios usam o código na interface. */
        center_names?: {
          [key: string]: string;
        };
      };
      demo: {
        enabled: boolean;
        active_persona: components["schemas"]["PersonaLabel"] | null;
      };
      csrf_token: string;
    };
    /** @enum {string} */
    MaterialStatus: "ATIVO" | "BLOQUEADO" | "OBSOLETO";
    /** @enum {string} */
    ValidationStatus: "VALID" | "INCOMPLETE" | "INVALID" | "OUT_OF_SCOPE";
    /** @enum {string} */
    ChatStatus: "NEEDS_INPUT" | "EXISTING" | "READY_TO_SUBMIT" | "SUBMITTED" | "OUT_OF_SCOPE";
    ToolCall: {
      id: string;
      /** @enum {string} */
      name:
        | "search_similar_materials"
        | "get_pdm_template"
        | "validate_and_format_pdm"
        | "check_ncm_consistency"
        | "enrich_from_trusted_source"
        | "retrieve_material_context";
      /** @constant */
      transport: "MCP_STDIO";
      input: {
        [key: string]: unknown;
      };
      /** @enum {string} */
      status: "SUCCEEDED" | "FAILED" | "PENDING";
      duration_ms?: number;
      result: {
        [key: string]: unknown;
      };
    };
    InventoryRow: {
      center_code: string;
      quantity: components["schemas"]["Decimal"];
      unit: string;
      /** @description Nome do centro preservado na origem, quando disponível. */
      center_name?: string | null;
    };
    ExistingMatch: {
      material_code: string;
      status: components["schemas"]["MaterialStatus"];
      pdm_description: string;
      match_type: string;
      reason: string;
      inventory: components["schemas"]["InventoryRow"][];
    };
    MaterialCardData: {
      pdm_class_id: string | null;
      pdm_class_name?: string;
      attributes: {
        [key: string]: string | null;
      };
      pdm_description: string | null;
      validation_status: components["schemas"]["ValidationStatus"];
      missing_attributes: string[];
      ncm: {
        suggested: string | null;
        /** @enum {string} */
        status: "PENDING_VALIDATION" | "CONSISTENT" | "REVIEW_REQUIRED";
      };
      /** @enum {string} */
      duplicate_check_status: "PENDING" | "NO_MATCH" | "MATCH_FOUND";
      existing?: components["schemas"]["ExistingMatch"];
      similar_candidates?: components["schemas"]["SimilarCandidate"][];
      can_submit: boolean;
    };
    ChatMessage: {
      /** Format: uuid */
      id: string;
      /** @enum {string} */
      author: "user" | "assistant";
      content: string;
      created_at: components["schemas"]["UtcDateTime"];
    };
    ChatTurnResponse: {
      request_id: string;
      /** Format: uuid */
      session_id: string;
      session_version: number;
      order_id: string | null;
      status: components["schemas"]["ChatStatus"];
      assistant_message: string;
      /** @description Chamadas MCP do turno. Diagnóstico técnico: vem vazio para quem não tem a permissão chat:diagnostics (role Dev/TI). */
      tool_calls: components["schemas"]["ToolCall"][];
      material_card: components["schemas"]["MaterialCardData"];
    };
    /** @enum {string} */
    ProposalType:
      | "MERGE"
      | "PDM_CORRECTION"
      | "UNIT_CORRECTION"
      | "NCM_CORRECTION"
      | "ENRICHMENT"
      | "COMPOSITE";
    /** @enum {string} */
    ReviewStatus: "PENDING" | "APPROVED" | "REJECTED" | "NOT_REQUIRED";
    /** @enum {string} */
    ProposalStatus: "PENDING" | "APPLIED" | "REJECTED" | "STALE";
    ProposalMember: {
      material_code: string;
      status: components["schemas"]["MaterialStatus"];
      description: string;
      unit: string | null;
      ncm: string | null;
      inventory: components["schemas"]["ProposalInventoryRow"][];
      /** @description Disponível somente com metrics:financial. */
      value_brl?: components["schemas"]["Decimal"];
    };
    Proposal: {
      ncm_assessment?: components["schemas"]["NcmAssessment"] | null;
      /** Format: uuid */
      id: string;
      version: number;
      proposal_type: components["schemas"]["ProposalType"];
      status: components["schemas"]["ProposalStatus"];
      title: string;
      material_codes: string[];
      suggested_primary_code: string | null;
      identity: components["schemas"]["ProposalIdentity"];
      members: components["schemas"]["ProposalMember"][];
      after: {
        description: string;
        ncm: string | null;
        unit: string;
        attributes: {
          [key: string]: string;
        };
      };
      changes: {
        field: string;
        before: string | null;
        after: string;
        source: string;
      }[];
      technical_review_status: components["schemas"]["ReviewStatus"];
      fiscal_review_status: components["schemas"]["ReviewStatus"];
      conflicts: string[];
      ranking_score: number | null;
      created_at: components["schemas"]["UtcDateTime"];
      allowed_actions: components["schemas"]["Decision"][];
      consolidated_inventory?: components["schemas"]["ConsolidatedInventoryRow"][];
      /** @description Omitido sem metrics:financial; nulo se o valor nao estiver disponivel. */
      consolidated_value_brl?: components["schemas"]["Decimal"] | null;
      /** @enum {string} */
      application_mode?: "HUMAN" | "AUTOMATIC";
      automation?: components["schemas"]["ProposalAutomation"] | null;
      origin: components["schemas"]["ProposalOrigin"];
      llm_audit?: components["schemas"]["LlmAuditSuggestion"] | null;
      confidence_band?: components["schemas"]["ConfidenceBand"] | null;
    };
    EvidenceItem: {
      attribute: string;
      current_value: string | null;
      proposed_value: string;
      source_title: string;
      source_url: string;
      source_excerpt: string;
      source_page: string | null;
      /** @enum {string} */
      confidence: "ALTA" | "MEDIA" | "BAIXA";
      divergence: string | null;
      source_sha256?: string | null;
      confidence_basis?: string[];
      simulated?: boolean;
      included_in_proposal?: boolean;
    };
    EnrichmentProposal: {
      /** Format: uuid */
      proposal_id: string;
      version: number;
      material_code: string;
      original_description: string;
      proposed_description: string;
      pdm_class_id: string;
      status: components["schemas"]["ProposalStatus"];
      evidence: components["schemas"]["EvidenceItem"][];
      technical_review_status?: components["schemas"]["ReviewStatus"];
      fiscal_review_status?: components["schemas"]["ReviewStatus"];
      allowed_actions?: ("APPROVE" | "REJECT")[];
      pending_attributes?: string[];
    };
    /** @enum {string} */
    OrderStatus:
      | "DRAFT"
      | "INCOMPLETE"
      | "READY_FOR_REVIEW"
      | "EXISTING"
      | "OUT_OF_SCOPE"
      | "PENDING_FISCAL"
      | "REGISTERED"
      | "REJECTED";
    RegistrationOrder: {
      /** Format: uuid */
      id: string;
      /** @enum {string} */
      origin: "CHAT" | "IMPORT";
      requester: string | null;
      original_text: string;
      center_code: string;
      pdm_class_id: string | null;
      status: components["schemas"]["OrderStatus"];
      missing_attributes: string[];
      material_code: string | null;
      updated_at: components["schemas"]["UtcDateTime"];
      version: number;
      supplements?: components["schemas"]["OrderSupplement"][];
      /** @description A identidade atual pode complementar este pedido no estado e escopo atuais. */
      can_complement?: boolean;
    };
    BatchJob: {
      /** Format: uuid */
      id: string;
      /** @enum {string} */
      job_type: "SANITIZE" | "IMPORT_ORDERS" | "ENRICH_REAL_PRODUCTS";
      /** @enum {string} */
      status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED";
      requested_by: string;
      pdm_version: string;
      ncm_version: string;
      progress: {
        processed: number;
        total: number;
      };
      counts: {
        proposals: number;
        merges: number;
        ncm: number;
        enrichment: number;
      };
      started_at: components["schemas"]["UtcDateTime"] | null;
      finished_at: components["schemas"]["UtcDateTime"] | null;
      heartbeat_at: components["schemas"]["UtcDateTime"] | null;
      error: {
        code: string;
        message: string;
      } | null;
      automatic_corrections?: components["schemas"]["AutomaticCorrectionSummary"] | null;
    };
    BatchJobList: {
      items: components["schemas"]["BatchJob"][];
      /** @description Dataset que um novo job usaria. */
      latest_dataset_id: string | null;
      next_cursor: string | null;
      /** @description Job ativo do tenant, mesmo fora da página ou do filtro; null quando não há execução ativa. */
      active_job: components["schemas"]["BatchJob"] | null;
      /** @enum {string} */
      automatic_correction_mode?: "OFF" | "SIMULATE" | "APPLY";
    };
    AuditEvent: {
      /** Format: uuid */
      id: string;
      actor: string;
      effective_role: components["schemas"]["Role"] | null;
      action: string;
      entity: string;
      reason: string | null;
      request_id: string;
      created_at: components["schemas"]["UtcDateTime"];
      before?: {
        [key: string]: unknown;
      };
      after?: {
        [key: string]: unknown;
      };
      /** @enum {string} */
      actor_type: "USER" | "SYSTEM";
    };
    DashboardMetrics: {
      /** Format: uuid */
      dataset_id: string;
      /** @enum {string} */
      comparison_status: "AFTER_SNAPSHOT_NOT_AVAILABLE" | "AVAILABLE";
      before: {
        materials_total: number;
        active: number;
        blocked: number;
        obsolete: number;
        missing_ncm: number;
        noncanonical_unit: number;
        /** @description Ativos apontados como duplicados por unificações pendentes ou aplicadas. */
        duplicate_codes: number;
      };
      after: {
        materials_total: number;
        active: number;
        blocked: number;
        obsolete: number;
        missing_ncm: number;
        noncanonical_unit: number;
        /** @description Ativos apontados como duplicados por unificações pendentes ou aplicadas. */
        duplicate_codes: number;
      } | null;
      after_snapshot: components["schemas"]["QualitySnapshot"] | null;
      pipeline: {
        proposals_total: number;
        pending: number;
        applied: number;
        rejected: number;
        stale: number;
      };
      evaluation: {
        reviewed_pairs: number;
        merge_precision: number | null;
        duplicate_recall: number | null;
        validated_class_ids?: string[];
      };
      financial?: {
        /** @constant */
        currency: "BRL";
        data_origin: string;
        /** @description Soma dos valores originais dos centros autorizados; indisponível se qualquer valor faltar. */
        inventory_book_value: components["schemas"]["Decimal"] | null;
        realized_savings: components["schemas"]["Decimal"] | null;
        estimated_savings: components["schemas"]["Decimal"] | null;
        assumptions?: string[];
      };
    };
    /** @description Quantidade ou valor decimal, sem conversão para ponto flutuante. */
    Decimal: string;
    /**
     * Format: date-time
     * @description Data ISO 8601 em UTC.
     */
    UtcDateTime: string;
    /** @enum {string} */
    ReviewArea: "TECHNICAL" | "FISCAL";
    /** @enum {string} */
    Decision: "APPROVE" | "REJECT";
    ProposalIdentity: {
      /** @enum {string} */
      mode: "MANUFACTURER_REFERENCE" | "TECHNICAL_ATTRIBUTES";
      summary?: string;
      manufacturer?: string | null;
      manufacturer_reference?: string | null;
      attributes?: {
        [key: string]: string;
      };
    };
    ProposalSummary: {
      /** Format: uuid */
      id: string;
      version: number;
      proposal_type: components["schemas"]["ProposalType"];
      status: components["schemas"]["ProposalStatus"];
      material_codes: string[];
      suggested_primary_code: string | null;
      identity: components["schemas"]["ProposalIdentity"];
      technical_review_status: components["schemas"]["ReviewStatus"];
      fiscal_review_status: components["schemas"]["ReviewStatus"];
      conflicts: string[];
      allowed_actions: components["schemas"]["Decision"][];
      title?: string;
      ranking_score?: number | null;
      created_at?: components["schemas"]["UtcDateTime"];
      /** @enum {string} */
      application_mode?: "HUMAN" | "AUTOMATIC";
      automation?: components["schemas"]["ProposalAutomation"] | null;
      origin: components["schemas"]["ProposalOrigin"];
      confidence_band?: components["schemas"]["ConfidenceBand"] | null;
    };
    Material: {
      material_code: string;
      status: components["schemas"]["MaterialStatus"];
      description: string;
      pdm_class: string | null;
      unit: string;
      ncm: string | null;
      active_code_target: string | null;
      inventory: components["schemas"]["InventoryRow"][];
      flags: ("SEM_NCM" | "DUPLICIDADE_SUSPEITA" | "UNIDADE_NAO_CANONICA" | "ATRIBUTO_FALTANDO")[];
    };
    SsoCallbackRequest: {
      code: string;
      state: string;
    };
    SsoCallbackResponse: {
      /** @constant */
      authenticated: true;
      expires_in_seconds: number;
      redirect_path: string;
    };
    DemoSwitchRequest: {
      session_handle: string;
    };
    ChatMessageRequest: {
      session_id: string | null;
      /** Format: uuid */
      client_message_id: string;
      expected_session_version: number;
      message: string;
      center_code: string;
      action?: components["schemas"]["ChatAction"];
    };
    ProposalDecisionRequest: {
      expected_version: number;
      review_area: components["schemas"]["ReviewArea"];
      decision: components["schemas"]["Decision"];
      primary_material_code?: string | null;
      reason: string;
    };
    ProposalDecisionResponse: {
      /** Format: uuid */
      proposal_id: string;
      version: number;
      status: components["schemas"]["ProposalStatus"];
      technical_review_status: components["schemas"]["ReviewStatus"];
      fiscal_review_status: components["schemas"]["ReviewStatus"];
      result: {
        primary_material_code: string | null;
        blocked_material_codes: string[];
      } | null;
      /** Format: uuid */
      audit_event_id: string;
    };
    BatchJobRequest: {
      /** Format: uuid */
      dataset_id: string;
      /** @enum {string} */
      job_type: "SANITIZE" | "IMPORT_ORDERS" | "ENRICH_REAL_PRODUCTS";
      pdm_version: string;
      ncm_version: string;
      scope: {
        pdm_class_ids: string[];
        /** @description O batch atual exige ATIVO, BLOQUEADO e OBSOLETO. Subconjuntos e lista vazia recebem 422 SCOPE_NOT_SUPPORTED antes de criar o job. */
        include_statuses: components["schemas"]["MaterialStatus"][];
      };
    };
    /** @description Sem campos: o job reprocessado é o da rota. */
    BatchJobResumeRequest: Record<string, never>;
    OrderSubmitRequest: {
      expected_version: number;
    };
    OrderDecisionRequest: {
      expected_version: number;
      decision: components["schemas"]["Decision"];
      reason: string;
      ncm_code?: string | null;
      ncm_source?: string | null;
      ncm_evaluation_hash?: string | null;
    };
    ApiError: {
      error: {
        code: string;
        message: string;
        request_id: string;
        details: {
          [key: string]: unknown;
        };
      };
    };
    ProposalQueue: {
      items: components["schemas"]["ProposalSummary"][];
      next_cursor: string | null;
    };
    OrderList: {
      items: components["schemas"]["RegistrationOrder"][];
      next_cursor: string | null;
    };
    MaterialList: {
      items: components["schemas"]["Material"][];
      next_cursor: string | null;
    };
    AuditList: {
      items: components["schemas"]["AuditEvent"][];
      next_cursor: string | null;
    };
    EnrichmentList: {
      items: components["schemas"]["EnrichmentProposal"][];
      next_cursor: string | null;
    };
    BatchManifest: {
      /** Format: uuid */
      job_id: string;
      /** Format: uuid */
      dataset_id: string;
      pipeline_version: string;
      pdm_version: string;
      ncm_version: string;
      input_manifest_key: string;
      output_prefix: string;
    };
    AgentRunRequest: {
      /** Format: uuid */
      turn_id: string;
      /** Format: uuid */
      session_id: string;
      session_version: number;
      message: string;
      action?: components["schemas"]["ChatAction"] | null;
      context: {
        pdm_version: string;
        ncm_version: string;
        center_code: string;
        history: components["schemas"]["ChatMessage"][];
        confirmed_attributes: {
          [key: string]: string | null;
        };
        /** @description Classe da última ficha persistida pela API; não é a classificação da mensagem atual. */
        pdm_class_id?: string | null;
        /** @description Nome do item da última ficha persistida pela API, para separar materiais da mesma classe. */
        item_name?: string | null;
        /** @description Códigos parecidos mostrados no turno anterior, lidos do contexto persistido pela API. */
        offered_material_codes?: string[];
        /** @description Códigos que o solicitante confirmou não serem o item dele, validados pela API. */
        dismissed_material_codes?: string[];
        /** @description Lida pela API do contexto persistido. Enquanto a ficha não muda, o Agent decide sem nova busca. */
        duplicate_check?: components["schemas"]["DuplicateCheckState"] | null;
      };
    };
    AgentRunResponse: {
      assistant_message: string;
      tool_calls: components["schemas"]["ToolCall"][];
      context_patch: {
        [key: string]: unknown;
      };
      material_card: components["schemas"]["MaterialCardData"];
    };
    /** @description Item parecido, sem identidade verificada, que o solicitante confirma ou descarta. Obsoletos nunca aparecem. */
    SimilarCandidate: {
      material_code: string;
      status: components["schemas"]["MaterialStatus"];
      pdm_description: string;
      active_code_target: string | null;
    };
    AuthConfig: {
      /** @enum {unknown} */
      mode: "disabled" | "local" | "cognito";
    };
    LocalSessionRequest: {
      persona: components["schemas"]["PersonaLabel"];
    };
    EmptyRequest: Record<string, never>;
    LogoutResponse: {
      /** @constant */
      logged_out: true;
      /**
       * Format: uri
       * @description Somente no Cognito: o navegador deve seguir este endereço para encerrar também a sessão do provedor.
       */
      provider_logout_url?: string;
    };
    ProposalInventoryRow: {
      center_code: string;
      quantity: components["schemas"]["Decimal"];
      unit: string | null;
    };
    ConsolidatedInventoryRow: {
      center_code: string;
      quantity: components["schemas"]["Decimal"];
      unit: string;
      total_value?: components["schemas"]["Decimal"] | null;
    };
    /** @description Ação dos botões do chat. Só vale para códigos oferecidos antes nesta conversa; o texto exibido no botão não importa. */
    ChatAction: {
      /** @enum {string} */
      type: "PICK_CANDIDATE" | "DISMISS_CANDIDATES";
      /** @description Obrigatório em PICK_CANDIDATE. */
      material_code?: string | null;
    };
    /** @description Última verificação de duplicidade aceita pela API, com a assinatura da ficha (classe e atributos preenchidos). Vale só enquanto a ficha não muda. */
    DuplicateCheckState: {
      signature: string;
      /** @enum {string} */
      status: "PENDING" | "NO_MATCH" | "MATCH_FOUND";
      existing?: components["schemas"]["ExistingMatch"];
      similar_candidates?: components["schemas"]["SimilarCandidate"][];
    };
    /** @description Snapshot posterior gerado só com propostas aplicadas; imutável. */
    QualitySnapshot: {
      /** Format: uuid */
      id: string;
      /** Format: uuid */
      dataset_id: string;
      /** Format: date-time */
      created_at: string;
      applied_proposals: number;
      materials_changed: number;
      inventory_value_conserved: boolean;
      export_key: string;
    };
    /** @description Sem dataset_id, usa o dataset importado mais recentemente. */
    QualitySnapshotRequest: {
      dataset_id?: string | null;
    };
    ChatSubmitRequest: {
      expected_session_version: number;
    };
    ChatSubmitResponse: {
      /** Format: uuid */
      session_id: string;
      session_version: number;
      /** Format: uuid */
      order_id: string;
      /** @enum {string} */
      status: "READY_FOR_REVIEW" | "EXISTING";
    };
    /** @enum {integer} */
    LotTier: 1 | 2;
    /** @description Lote elegível: propostas pendentes com o mesmo review_lane.lot_key e nível 1 ou 2. */
    LotSummary: {
      lot_key: string;
      tier: components["schemas"]["LotTier"];
      /** @enum {string} */
      proposal_type: "UNIT_CORRECTION" | "PDM_CORRECTION";
      rule: string;
      pdm_class_id: string | null;
      pdm_class_name: string | null;
      size: number;
      sample_size: number;
      open_review_id: string | null;
    };
    LotList: {
      items: components["schemas"]["LotSummary"][];
      min_lot_size: number;
    };
    LotReviewOpenRequest: {
      lot_key: string;
      tier: components["schemas"]["LotTier"];
    };
    LotSampleItem: {
      /** Format: uuid */
      proposal_id: string;
      /** @enum {string} */
      proposal_type: "UNIT_CORRECTION" | "PDM_CORRECTION";
      status: components["schemas"]["ProposalStatus"];
      material_code: string | null;
      original_description: string | null;
      current_description: string | null;
      proposed_description: string | null;
      changes: {
        field: string;
        before: string | null;
        after: string;
        source: string;
      }[];
    };
    LotItemOutcome: {
      /** Format: uuid */
      proposal_id: string;
      /** @enum {string} */
      status: "APPLIED" | "STALE" | "SKIPPED";
      code?: string;
    };
    /** @description Aprovado: contagens e resultado de cada item. Devolvido: itens marcados como errados e a regra. */
    LotResult: {
      counts?: {
        APPLIED: number;
        STALE: number;
        SKIPPED: number;
      };
      items?: components["schemas"]["LotItemOutcome"][];
      wrong_ids?: string[];
      rule?: string;
    };
    /** @description Revisão de um lote: amostra sorteada pelo servidor, igual em toda leitura. */
    LotReview: {
      /** Format: uuid */
      id: string;
      lot_key: string;
      tier: components["schemas"]["LotTier"];
      /** @enum {string} */
      proposal_type: "UNIT_CORRECTION" | "PDM_CORRECTION";
      rule: string;
      pdm_class_id: string | null;
      pdm_class_name: string | null;
      /** @enum {string} */
      status: "OPEN" | "APPROVED" | "RETURNED";
      version: number;
      size: number;
      sample: components["schemas"]["LotSampleItem"][];
      marks: {
        [key: string]: "CORRECT" | "WRONG";
      };
      result: components["schemas"]["LotResult"] | null;
      created_at: string | null;
      decided_at: string | null;
    };
    LotDecisionRequest: {
      expected_version: number;
      marks: {
        /** Format: uuid */
        proposal_id: string;
        /** @enum {string} */
        verdict: "CORRECT" | "WRONG";
      }[];
      reason: string;
    };
    LotDecisionResponse: {
      /** Format: uuid */
      lot_review_id: string;
      /** @enum {string} */
      status: "APPROVED" | "RETURNED";
      version: number;
      result: components["schemas"]["LotResult"];
      /** Format: uuid */
      audit_event_id: string;
    };
    ChatSessionSummary: {
      /** Format: uuid */
      id: string;
      title: string;
      /** Format: date-time */
      updated_at: string;
    };
    ChatSessionList: {
      items: components["schemas"]["ChatSessionSummary"][];
      next_cursor: string | null;
    };
    SavedToolCall: {
      turn: number;
      call: components["schemas"]["ToolCall"];
    };
    ChatSessionDetail: {
      /** Format: uuid */
      session_id: string;
      session_version: number;
      processing: boolean;
      center_code: string | null;
      messages: components["schemas"]["ChatMessage"][];
      /** @description Chamadas MCP salvas na conversa. Vazio sem a permissão chat:diagnostics (role Dev/TI). */
      calls: components["schemas"]["SavedToolCall"][];
      material_card: components["schemas"]["MaterialCardData"] | null;
      /** Format: uuid */
      order_id: string | null;
      submission: components["schemas"]["ChatSubmitResponse"] | null;
      /** @description Solicitação criada explicitamente nesta conversa; presente nos três caminhos e recuperada do banco. */
      material_request_submission?: components["schemas"]["ChatMaterialRequestResponse"] | null;
    };
    ManualReview: {
      /** Format: uuid */
      id: string;
      /** Format: uuid */
      run_id: string;
      /** Format: uuid */
      job_id: string | null;
      /** Format: uuid */
      material_id: string;
      expected_material_version: number;
      reasons: string[];
      observation: {
        material_code: string;
        status: components["schemas"]["MaterialStatus"];
        description: string;
        unit: string;
        ncm: string | null;
        pdm_class_id: string | null;
        item_name: string | null;
        attributes: {
          [key: string]: string | null;
        };
        completeness?: components["schemas"]["MaterialCompletenessReview"] | null;
      };
      rules_signature: string;
      pdm_version: string;
      pdm_source_sha256: string;
      /** Format: uuid */
      proposal_id: string | null;
      proposal_status: components["schemas"]["ProposalStatus"] | null;
      /** Format: date-time */
      created_at: string;
    };
    ManualReviewList: {
      /** Format: uuid */
      run_id: string | null;
      /** Format: uuid */
      job_id: string | null;
      items: components["schemas"]["ManualReview"][];
      counts_by_reason: {
        [key: string]: number;
      };
      materials_total: number;
      /** Format: uuid */
      next_cursor: string | null;
    };
    /** UnitConversion */
    ManualUnitConversion: {
      /** From Unit */
      from_unit: string;
      /** To Unit */
      to_unit: string;
      /** Factor */
      factor: string;
      /** Source */
      source: string;
    };
    /** ManualReviewResolution */
    ManualReviewResolution: {
      /** Expected Material Version */
      expected_material_version: number;
      /** Pdm Class Id */
      pdm_class_id: string;
      /** Item Name */
      item_name: string;
      /** Attributes */
      attributes: {
        [key: string]: string;
      };
      /** Unit */
      unit: string;
      /** Ncm */
      ncm: string | null;
      /** Conversions */
      conversions?: components["schemas"]["ManualUnitConversion"][];
      /** Source */
      source: string;
      /** Reason */
      reason: string;
    };
    ManualReviewProposed: {
      /** Format: uuid */
      review_id: string;
      /** Format: uuid */
      proposal_id: string;
      /** @constant */
      status: "PENDING";
    };
    ManualReviewAttribute: {
      name: string;
      required: boolean;
      format: string;
      allowed_values: string[];
    };
    ManualReviewClass: {
      id: string;
      item_names: string[];
      unit: string;
      attributes: components["schemas"]["ManualReviewAttribute"][];
      ncm_codes: string[];
    };
    ManualReviewCatalog: {
      pdm_version: string;
      classes: components["schemas"]["ManualReviewClass"][];
    };
    OrderComplementRequest: {
      expected_version: number;
      text: string;
      source: string;
      reason: string;
    };
    OrderSupplement: {
      text: string;
      source: string;
      reason: string;
      /** Format: uuid */
      actor_user_id: string;
      /** Format: date-time */
      created_at: string;
    };
    OrderReview: {
      order: components["schemas"]["RegistrationOrder"];
      attachment_text: string | null;
      item_name: string | null;
      attributes: {
        [key: string]: string;
      };
      formatted_description: string | null;
      candidate_material_ids: string[];
      pdm_version: string;
      pdm_source_sha256: string;
      index_version: string;
      ncm_assessment: components["schemas"]["NcmAssessment"];
      ncm_proposed: string | null;
      ncm_references: {
        codes: string[];
        condition: string;
      }[];
      review_data: {
        [key: string]: unknown;
      };
      fiscal_decision: components["schemas"]["OrderFiscalDecision"] | null;
      technical_review_current: boolean;
    };
    OrderFiscalDecision: {
      ncm_code: string;
      source: string;
      reason: string;
      /** Format: uuid */
      actor_user_id: string;
      approved_version: number;
      assessment: components["schemas"]["NcmAssessment"];
    };
    OrderReopenReviewRequest: {
      expected_version: number;
      reason: string;
    };
    AutomaticCorrectionSummary: {
      /** @enum {string} */
      mode: "OFF" | "SIMULATE" | "APPLY";
      /** @enum {string} */
      configured_mode: "OFF" | "SIMULATE" | "APPLY";
      policy_version: string;
      execution_id: string | null;
      /** @enum {string} */
      status: "DISABLED" | "WAITING" | "RUNNING" | "COMPLETED" | "POLICY_CHANGED" | "PAUSED";
      counts: {
        [key: string]: number;
      };
      reasons: {
        [key: string]: number;
      };
    };
    AutomaticCorrectionItem: {
      /** Format: uuid */
      id: string;
      /** Format: uuid */
      proposal_id: string;
      material_id: string | null;
      /** @enum {string} */
      status: "ELIGIBLE" | "APPLIED" | "REVIEW" | "STALE" | "ERROR" | "SKIPPED";
      eligible: boolean;
      reasons: string[];
      attempts: number;
      /** @enum {string} */
      index_status: "NOT_REQUIRED" | "PENDING" | "CURRENT" | "FAILED";
      index_error: string | null;
    };
    AutomaticCorrectionReport: {
      /** @enum {string} */
      mode: "OFF" | "SIMULATE" | "APPLY";
      /** @enum {string} */
      configured_mode: "OFF" | "SIMULATE" | "APPLY";
      policy_version: string;
      execution_id: string | null;
      /** @enum {string} */
      status: "DISABLED" | "WAITING" | "RUNNING" | "COMPLETED" | "POLICY_CHANGED" | "PAUSED";
      counts: {
        [key: string]: number;
      };
      reasons: {
        [key: string]: number;
      };
      items: components["schemas"]["AutomaticCorrectionItem"][];
      next_cursor: string | null;
    };
    AutomaticCorrectionRetryRequest: Record<string, never>;
    ProposalAutomation: {
      /** @enum {string} */
      mode: "SIMULATE" | "APPLY";
      /** @enum {string} */
      status: "ELIGIBLE" | "APPLIED" | "REVIEW" | "STALE" | "ERROR" | "SKIPPED";
      policy_version: string;
      /** Format: uuid */
      execution_id: string;
      reasons: string[];
      /** @enum {string} */
      index_status: "NOT_REQUIRED" | "PENDING" | "CURRENT" | "FAILED";
    };
    MaterialCompleteness: {
      /** @enum {string} */
      status: "VALID" | "INCOMPLETE" | "INVALID" | "OUT_OF_SCOPE";
      missing_required: string[];
      not_applicable: string[];
      conditional_pending: string[];
      optional_missing: string[];
      invalid: {
        name: string;
        reason: string;
      }[];
    };
    MaterialCompletenessReview: {
      before: components["schemas"]["MaterialCompleteness"];
      after_suggestions: components["schemas"]["MaterialCompleteness"];
      suggestions: {
        [key: string]: string;
      };
      conflicts: {
        [key: string]: string[];
      };
      classification?: components["schemas"]["EnrichmentClassification"];
      gaps?: components["schemas"]["EnrichmentGap"][];
      record_conflicts?: {
        [key: string]: string[];
      };
      assisted_candidates?: components["schemas"]["AssistedAttributeCandidate"][];
    };
    EnrichmentClassification: {
      /** @enum {string} */
      status: "CLASSIFIED" | "UNRESOLVED" | "OUT_OF_SCOPE";
      candidate_class_ids: string[];
    };
    EnrichmentGap: {
      attribute: string | null;
      /** @enum {string} */
      reason:
        | "CLASS_UNRESOLVED"
        | "CLASS_OUT_OF_SCOPE"
        | "CONTRADICTORY_OBSERVATIONS"
        | "CONFLICTING_SOURCES"
        | "IDENTITY_NOT_CONFIRMED"
        | "TEXT_NOT_RECOGNIZED"
        | "NO_SUPPORTED_EVIDENCE"
        | "CONDITION_UNRESOLVED"
        | "INVALID_VALUE";
      question: string;
    };
    /** @description Leitura assistida a conferir manualmente. Não preenche o cadastro nem autoriza aprovação. */
    AssistedAttributeCandidate: {
      attribute: string;
      value: string;
      source_field: string;
      excerpt: string;
      extraction_rule?: string;
      /** @constant */
      manual_confirmation_required?: true;
    };
    /** CreateMaterialRequest */
    CreateMaterialRequest: {
      /** Original Text */
      original_text: string;
      /** Quantity */
      quantity: string;
      /** Unit */
      unit: string;
      /** Center Code */
      center_code: string;
      /**
       * Material Id
       * @default null
       */
      material_id: string | null;
      /**
       * Chat Session Id
       * @default null
       */
      chat_session_id: string | null;
      /**
       * Registration Order Id
       * @default null
       */
      registration_order_id: string | null;
      /**
       * Acknowledge Open Requests
       * @description Confirma a criação mesmo com solicitação aberta do mesmo material e centro, após o aviso OPEN_REQUESTS_EXIST. A confirmação fica na auditoria da criação.
       * @default false
       */
      acknowledge_open_requests: boolean;
    };
    /** CancelMaterialRequest */
    CancelMaterialRequest: {
      /** Expected Version */
      expected_version: number;
      /** Reason */
      reason: string;
    };
    /** @description Solicitação aberta que o usuário já pode ler; nunca inclui solicitante nem texto. */
    OpenMaterialRequestRef: {
      /** Format: uuid */
      id: string;
      protocol: string;
      /** @enum {string} */
      status: "EM_IDENTIFICACAO" | "AGUARDANDO_CADASTRO" | "EM_ATENDIMENTO";
      quantity: string;
      unit: string;
      /** Format: date-time */
      created_at: string;
    };
    /** @description Solicitações não encerradas do mesmo tenant, material e centro. As que o usuário não pode ler aparecem só em hidden_count. */
    OpenMaterialRequestsWarning: {
      total_count: number;
      hidden_count: number;
      open_requests: components["schemas"]["OpenMaterialRequestRef"][];
    };
    OpenMaterialRequestsConflict: {
      error: {
        /** @constant */
        code: "OPEN_REQUESTS_EXIST";
        message: string;
        request_id: string;
        details: components["schemas"]["OpenMaterialRequestsWarning"];
      };
    };
    /** MaterialRequestSummary */
    MaterialRequestSummary: {
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /** Protocol */
      protocol: string;
      /**
       * Requester User Id
       * Format: uuid
       */
      requester_user_id: string;
      /** Original Text */
      original_text: string;
      /** Material Id */
      material_id: string | null;
      /** Quantity */
      quantity: string;
      /** Unit */
      unit: string;
      /** Center Code */
      center_code: string;
      /**
       * Status
       * @enum {string}
       */
      status: "EM_IDENTIFICACAO" | "AGUARDANDO_CADASTRO" | "EM_ATENDIMENTO" | "ENCERRADA";
      /** Closure Reason */
      closure_reason: string | null;
      /** Chat Session Id */
      chat_session_id: string | null;
      /** Registration Order Id */
      registration_order_id: string | null;
      /** Version */
      version: number;
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
      /**
       * Updated At
       * Format: date-time
       */
      updated_at: string;
      /** Can Cancel */
      can_cancel: boolean;
    };
    /** MaterialRequestTransition */
    MaterialRequestTransition: {
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /** Action */
      action: string;
      /**
       * Actor User Id
       * Format: uuid
       */
      actor_user_id: string;
      /** Before Status */
      before_status:
        ("EM_IDENTIFICACAO" | "AGUARDANDO_CADASTRO" | "EM_ATENDIMENTO" | "ENCERRADA") | null;
      /**
       * After Status
       * @enum {string}
       */
      after_status: "EM_IDENTIFICACAO" | "AGUARDANDO_CADASTRO" | "EM_ATENDIMENTO" | "ENCERRADA";
      /** Reason */
      reason: string | null;
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
    };
    /** MaterialRequestDetail */
    MaterialRequestDetail: {
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /** Protocol */
      protocol: string;
      /**
       * Requester User Id
       * Format: uuid
       */
      requester_user_id: string;
      /** Original Text */
      original_text: string;
      /** Material Id */
      material_id: string | null;
      /** Quantity */
      quantity: string;
      /** Unit */
      unit: string;
      /** Center Code */
      center_code: string;
      /**
       * Status
       * @enum {string}
       */
      status: "EM_IDENTIFICACAO" | "AGUARDANDO_CADASTRO" | "EM_ATENDIMENTO" | "ENCERRADA";
      /** Closure Reason */
      closure_reason: string | null;
      /** Chat Session Id */
      chat_session_id: string | null;
      /** Registration Order Id */
      registration_order_id: string | null;
      /** Version */
      version: number;
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
      /**
       * Updated At
       * Format: date-time
       */
      updated_at: string;
      /** Can Cancel */
      can_cancel: boolean;
      /** Pending Quantity */
      pending_quantity: string;
      /** Reserved Quantity */
      reserved_quantity: string;
      /** Delivered Quantity */
      delivered_quantity: string;
      /** Forwarded Quantity */
      forwarded_quantity: string;
      /** Reservations */
      reservations: components["schemas"]["StockReservation"][];
      /** Purchase Forwards */
      purchase_forwards: components["schemas"]["PurchaseForward"][];
      /** History */
      history: components["schemas"]["MaterialRequestTransition"][];
    };
    /** MaterialRequestList */
    MaterialRequestList: {
      /** Items */
      items: components["schemas"]["MaterialRequestSummary"][];
      /** Next Cursor */
      next_cursor: string | null;
    };
    /**
     * StockAvailability
     * @description Disponível = saldo importado do dataset vigente (com consolidações aprovadas) - reservas ATIVA - entregas menos reversões do mesmo dataset, no centro e na unidade do material. Sem preço nem valor.
     */
    StockAvailability: {
      /**
       * Material Id
       * Format: uuid
       */
      material_id: string;
      /** Material Code */
      material_code: string;
      /** Center Code */
      center_code: string;
      /** Unit */
      unit: string | null;
      /** Dataset Id */
      dataset_id: string | null;
      imported: components["schemas"]["Decimal"];
      reserved: components["schemas"]["Decimal"];
      delivered: components["schemas"]["Decimal"];
      available: components["schemas"]["Decimal"];
      /** Unconverted Units */
      unconverted_units: string[];
      /** Reservable */
      reservable: boolean;
      /** Blocked Reason */
      blocked_reason:
        | (
            | "INACTIVE_MATERIAL"
            | "MATERIAL_WITHOUT_UNIT"
            | "NO_INVENTORY_DATASET"
            | "RECONCILIATION_REQUIRED"
          )
        | null;
    };
    /** CreateStockReservation */
    CreateStockReservation: {
      /** Expected Version */
      expected_version: number;
      /** Quantity */
      quantity: string;
    };
    /**
     * StockReservation
     * @description `quantity` é a quantidade reservada original; `open_quantity` ainda conta em `R`.
     */
    StockReservation: {
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /**
       * Request Id
       * Format: uuid
       */
      request_id: string;
      /**
       * Material Id
       * Format: uuid
       */
      material_id: string;
      /** Center Code */
      center_code: string;
      /** Quantity */
      quantity: string;
      /** Delivered Quantity */
      delivered_quantity: string;
      /** Open Quantity */
      open_quantity: string;
      /** Unit */
      unit: string;
      /**
       * Status
       * @enum {string}
       */
      status: "ATIVA" | "CONSUMIDA" | "CANCELADA";
      /**
       * Dataset Id
       * Format: uuid
       */
      dataset_id: string;
      /**
       * Created By User Id
       * Format: uuid
       */
      created_by_user_id: string;
      /** Version */
      version: number;
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
      /**
       * Updated At
       * Format: date-time
       */
      updated_at: string;
    };
    /**
     * RequestFulfillment
     * @description Parcelas da solicitação: pendente = solicitado - reservado - entregue - encaminhado para compras. reservado conta só a parte ainda não entregue das reservas ativas, e entregue desconta reversões.
     */
    RequestFulfillment: {
      requested: components["schemas"]["Decimal"];
      reserved: components["schemas"]["Decimal"];
      delivered: components["schemas"]["Decimal"];
      forwarded: components["schemas"]["Decimal"];
      pending: components["schemas"]["Decimal"];
    };
    /** StockReservationResult */
    StockReservationResult: {
      reservation: components["schemas"]["StockReservation"];
      request: components["schemas"]["MaterialRequestSummary"];
      fulfillment: components["schemas"]["RequestFulfillment"];
      availability: components["schemas"]["StockAvailability"];
    };
    /**
     * DeliverStockReservation
     * @description Saída física de parte ou de toda a reserva; expected_version é a versão da solicitação.
     */
    DeliverStockReservation: {
      /** Expected Version */
      expected_version: number;
      /** Quantity */
      quantity: string;
    };
    /**
     * CancelStockReservation
     * @description Libera a parte reservada e não entregue; expected_version é a versão da solicitação.
     */
    CancelStockReservation: {
      /** Expected Version */
      expected_version: number;
      /** Reason */
      reason: string;
    };
    /**
     * ReverseStockMovement
     * @description Movimento compensatório de uma entrega, limitado ao que ainda não foi revertido; expected_version é a versão da solicitação.
     */
    ReverseStockMovement: {
      /** Expected Version */
      expected_version: number;
      /** Quantity */
      quantity: string;
      /** Reason */
      reason: string;
    };
    /**
     * StockMovement
     * @description Entrega ou reversão; somente inserção. reversed_quantity só existe na entrega.
     */
    StockMovement: {
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /**
       * Reservation Id
       * Format: uuid
       */
      reservation_id: string;
      /**
       * Request Id
       * Format: uuid
       */
      request_id: string;
      /**
       * Movement Type
       * @enum {string}
       */
      movement_type: "ENTREGA" | "REVERSAO";
      /** Quantity */
      quantity: string;
      /** Reverses Movement Id */
      reverses_movement_id: string | null;
      /** Reversed Quantity */
      reversed_quantity: string | null;
      /** Unit */
      unit: string;
      /**
       * Dataset Id
       * Format: uuid
       */
      dataset_id: string;
      /**
       * Created By User Id
       * Format: uuid
       */
      created_by_user_id: string;
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
    };
    /** StockMovementResult */
    StockMovementResult: {
      movement: components["schemas"]["StockMovement"];
      reservation: components["schemas"]["StockReservation"];
      request: components["schemas"]["MaterialRequestSummary"];
      fulfillment: components["schemas"]["RequestFulfillment"];
      availability: components["schemas"]["StockAvailability"];
    };
    /** StockReservationList */
    StockReservationList: {
      /** Items */
      items: components["schemas"]["StockReservation"][];
      /** Movements */
      movements: components["schemas"]["StockMovement"][];
      fulfillment: components["schemas"]["RequestFulfillment"];
    };
    /**
     * ForwardToPurchasing
     * @description Encaminha a quantidade pendente inteira; a divisão com reserva parcial é da #242.
     */
    ForwardToPurchasing: {
      /** Expected Version */
      expected_version: number;
    };
    /**
     * ConfirmFulfillment
     * @description Escolha do solicitante na falta parcial (D1); a divisão é recalculada no servidor.
     */
    ConfirmFulfillment: {
      /** Expected Version */
      expected_version: number;
      /**
       * Option
       * @enum {string}
       */
      option: "PARTIAL" | "PURCHASING_ONLY";
    };
    /**
     * FulfillmentSplit
     * @description Quanto seria reservado do estoque e quanto seria encaminhado para compras.
     */
    FulfillmentSplit: {
      /**
       * Option
       * @enum {string}
       */
      option: "PARTIAL" | "PURCHASING_ONLY";
      /** Reserve Quantity */
      reserve_quantity: string;
      /** Forward Quantity */
      forward_quantity: string;
    };
    /**
     * FulfillmentPreview
     * @description Consulta da divisão; não reserva, não encaminha e não grava nada.
     */
    FulfillmentPreview: {
      /**
       * Request Id
       * Format: uuid
       */
      request_id: string;
      /** Request Version */
      request_version: number;
      /** Unit */
      unit: string;
      /** Center Code */
      center_code: string;
      /** Requested */
      requested: string;
      /** Reserved */
      reserved: string;
      /** Delivered */
      delivered: string;
      /** Forwarded */
      forwarded: string;
      /** Pending */
      pending: string;
      /** Available */
      available: string;
      /** Blocked Reason */
      blocked_reason:
        | (
            | "REQUEST_NOT_IN_SERVICE"
            | "INACTIVE_MATERIAL"
            | "UNIT_MISMATCH"
            | "NOTHING_PENDING"
            | "NO_INVENTORY_DATASET"
            | "RECONCILIATION_REQUIRED"
            | "STOCK_UNIT_UNRESOLVED"
            | "STOCK_AVAILABLE"
          )
        | null;
      /** Default Option */
      default_option: ("PARTIAL" | "PURCHASING_ONLY") | null;
      /** Options */
      options: components["schemas"]["FulfillmentSplit"][];
    };
    /**
     * FulfillmentResult
     * @description Parcelas efetivamente gravadas, calculadas com o disponível lido dentro do bloqueio.
     */
    FulfillmentResult: {
      /**
       * Option
       * @enum {string}
       */
      option: "PARTIAL" | "PURCHASING_ONLY";
      /** Reserved Quantity */
      reserved_quantity: string;
      /** Forwarded Quantity */
      forwarded_quantity: string;
      /** Available At Confirmation */
      available_at_confirmation: string;
      /** Reservation Id */
      reservation_id: string | null;
      /**
       * Purchase Forward Id
       * Format: uuid
       */
      purchase_forward_id: string;
      request: components["schemas"]["MaterialRequestDetail"];
    };
    /** AcceptPurchaseForward */
    AcceptPurchaseForward: {
      /** Expected Version */
      expected_version: number;
    };
    /** ReturnPurchaseForward */
    ReturnPurchaseForward: {
      /** Expected Version */
      expected_version: number;
      /** Reason */
      reason: string;
    };
    /**
     * PurchaseForward
     * @description Demanda para Compras; não indica pedido ao fornecedor, recebimento nem entrega.
     */
    PurchaseForward: {
      /**
       * Id
       * Format: uuid
       */
      id: string;
      /**
       * Material Request Id
       * Format: uuid
       */
      material_request_id: string;
      /** Request Protocol */
      request_protocol: string;
      /**
       * Material Id
       * Format: uuid
       */
      material_id: string;
      /** Material Code */
      material_code: string;
      /** Material Description */
      material_description: string | null;
      /** Quantity */
      quantity: string;
      /** Unit */
      unit: string;
      /** Center Code */
      center_code: string;
      /**
       * Status
       * @enum {string}
       */
      status: "ENCAMINHADO" | "ACEITO" | "DEVOLVIDO" | "CANCELADO";
      /** Reason */
      reason: string | null;
      /**
       * Forwarded By User Id
       * Format: uuid
       */
      forwarded_by_user_id: string;
      /** Handled By User Id */
      handled_by_user_id: string | null;
      /** Handled At */
      handled_at: string | null;
      /** Version */
      version: number;
      /**
       * Created At
       * Format: date-time
       */
      created_at: string;
      /**
       * Updated At
       * Format: date-time
       */
      updated_at: string;
      /** Can Handle */
      can_handle: boolean;
    };
    /** PurchaseForwardList */
    PurchaseForwardList: {
      /** Items */
      items: components["schemas"]["PurchaseForward"][];
      /** Next Cursor */
      next_cursor: string | null;
    };
    /**
     * @description RULES: regras do batch. LLM_AUDITOR: sugestão do auditor LLM, sempre com revisão técnica e fiscal.
     * @enum {string}
     */
    ProposalOrigin: "RULES" | "LLM_AUDITOR";
    /** @description Evidência do auditor LLM (#290) para a revisão humana; nada é aplicado por ela. */
    LlmAuditSuggestion: {
      model: string;
      prompt_version: string;
      policy_version: string;
      simulated: boolean;
      selection_reasons: string[];
      /** @enum {string} */
      class_source: "RULES" | "LLM";
      attributes: {
        name: string;
        value: string;
        quote: string;
        /** @enum {string} */
        basis: "LITERAL" | "INFERIDO";
      }[];
      evidence: string[];
      rationale: string;
      confidence?: components["schemas"]["LlmAuditConfidence"] | null;
    };
    /** ChatMaterialRequest */
    ChatMaterialRequest: {
      /** Expected Session Version */
      expected_session_version: number;
      /** Quantity */
      quantity: string;
      /** Unit */
      unit: string;
      /**
       * @description Confirma criar outra necessidade após o aviso de solicitações abertas do mesmo material e centro.
       * @default false
       */
      acknowledge_open_requests: boolean;
    };
    /** ChatMaterialRequestResponse */
    ChatMaterialRequestResponse: {
      /**
       * Session Id
       * Format: uuid
       */
      session_id: string;
      /** Session Version */
      session_version: number;
      material_request: components["schemas"]["MaterialRequestDetail"];
    };
    /**
     * @description Faixa de confiança da sugestão do auditor LLM (#297). Só ordena a revisão; nunca aprova, aplica nem coloca em lote.
     * @enum {string}
     */
    ConfidenceBand: "ALTA" | "MEDIA" | "BAIXA";
    /** @description Confiança da sugestão (#297): validação pelo domínio e, com pontuador, probabilidades entre os códigos de referência do PDM. */
    LlmAuditConfidence: {
      domain_validated: boolean;
      band: components["schemas"]["ConfidenceBand"] | null;
      probability: number | null;
      chosen: string;
      candidates: {
        code: string;
        probability: number | null;
      }[];
      scorer_model: string | null;
      scorer_simulated: boolean;
      version: string;
      error: string | null;
    };
  };
  responses: never;
  parameters: {
    /** @description Obrigatório nas escritas com cookie. A API também verifica a origem. */
    CsrfToken: string;
    /** @description Reutilizar a mesma chave e o mesmo payload ao repetir uma operação. */
    IdempotencyKey: string;
  };
  requestBodies: never;
  headers: never;
  pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
  startSso: {
    parameters: {
      query?: {
        /** @description Com DEMO_MODE, `login` pede nova autenticação para entrar com outra conta demo no mesmo navegador. */
        prompt?: "login";
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Resultado da operação. */
      302: {
        headers: {
          /** @description Endereço do login gerenciado do Cognito. */
          Location?: string;
          [name: string]: unknown;
        };
        content?: never;
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  getAuthConfig: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Sucesso */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["AuthConfig"];
        };
      };
    };
  };
  createLocalSession: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["LocalSessionRequest"];
      };
    };
    responses: {
      /** @description Sucesso */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["Me"];
        };
      };
    };
  };
  logout: {
    parameters: {
      query?: never;
      header: {
        /** @description Obrigatório nas escritas com cookie. A API também verifica a origem. */
        "X-CSRF-Token"?: components["parameters"]["CsrfToken"];
        /** @description Reutilizar a mesma chave e o mesmo payload ao repetir uma operação. */
        "Idempotency-Key": components["parameters"]["IdempotencyKey"];
      };
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["EmptyRequest"];
      };
    };
    responses: {
      /** @description Sucesso */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["LogoutResponse"];
        };
      };
    };
  };
  completeSso: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["SsoCallbackRequest"];
      };
    };
    responses: {
      /** @description Resultado da operação. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["SsoCallbackResponse"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  getMe: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Resultado da operação. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["Me"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  switchDemoSession: {
    parameters: {
      query?: never;
      header: {
        /** @description Obrigatório nas escritas com cookie. A API também verifica a origem. */
        "X-CSRF-Token"?: components["parameters"]["CsrfToken"];
        /** @description Reutilizar a mesma chave e o mesmo payload ao repetir uma operação. */
        "Idempotency-Key": components["parameters"]["IdempotencyKey"];
      };
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["DemoSwitchRequest"];
      };
    };
    responses: {
      /** @description Resultado da operação. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["Me"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  sendChatMessage: {
    parameters: {
      query?: never;
      header: {
        /** @description Obrigatório nas escritas com cookie. A API também verifica a origem. */
        "X-CSRF-Token"?: components["parameters"]["CsrfToken"];
        /** @description Reutilizar a mesma chave e o mesmo payload ao repetir uma operação. */
        "Idempotency-Key": components["parameters"]["IdempotencyKey"];
      };
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["ChatMessageRequest"];
      };
    };
    responses: {
      /** @description Resultado da operação. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ChatTurnResponse"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  listProposals: {
    parameters: {
      query?: {
        cursor?: string;
        limit?: number;
        review_area?: components["schemas"]["ReviewArea"];
        status?: "PENDING" | "APPLIED" | "REJECTED" | "STALE" | "DECIDED";
        proposal_type?: components["schemas"]["ProposalType"];
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Resultado da operação. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ProposalQueue"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  getProposal: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Resultado da operação. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["Proposal"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  decideProposal: {
    parameters: {
      query?: never;
      header: {
        /** @description Obrigatório nas escritas com cookie. A API também verifica a origem. */
        "X-CSRF-Token"?: components["parameters"]["CsrfToken"];
        /** @description Reutilizar a mesma chave e o mesmo payload ao repetir uma operação. */
        "Idempotency-Key": components["parameters"]["IdempotencyKey"];
      };
      path: {
        id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["ProposalDecisionRequest"];
      };
    };
    responses: {
      /** @description Resultado da operação. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ProposalDecisionResponse"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  getMetrics: {
    parameters: {
      query?: {
        view?: "quality" | "executive";
        /** @description Dataset importado; por padrão, o mais recente visível nos centros da sessão. */
        dataset_id?: string;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Resultado da operação. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["DashboardMetrics"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  createQualitySnapshot: {
    parameters: {
      query?: never;
      header: {
        /** @description Obrigatório nas escritas com cookie. A API também verifica a origem. */
        "X-CSRF-Token"?: components["parameters"]["CsrfToken"];
        /** @description Reutilizar a mesma chave e o mesmo payload ao repetir uma operação. */
        "Idempotency-Key": components["parameters"]["IdempotencyKey"];
      };
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["QualitySnapshotRequest"];
      };
    };
    responses: {
      /** @description Resultado da operação. */
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["QualitySnapshot"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  listBatchJobs: {
    parameters: {
      query?: {
        limit?: number;
        /** @description Cursor opaco retornado em next_cursor. Reiniciar ao trocar tenant ou status. */
        cursor?: string;
        status?: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED";
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Resultado da operação. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["BatchJobList"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  startBatchJob: {
    parameters: {
      query?: never;
      header: {
        /** @description Obrigatório nas escritas com cookie. A API também verifica a origem. */
        "X-CSRF-Token"?: components["parameters"]["CsrfToken"];
        /** @description Reutilizar a mesma chave e o mesmo payload ao repetir uma operação. */
        "Idempotency-Key": components["parameters"]["IdempotencyKey"];
      };
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["BatchJobRequest"];
      };
    };
    responses: {
      /** @description Job criado ou recuperado pela mesma chave, no estado atual. */
      202: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["BatchJob"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  getBatchJob: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Resultado da operação. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["BatchJob"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  resumeBatchJob: {
    parameters: {
      query?: never;
      header: {
        /** @description Obrigatório nas escritas com cookie. A API também verifica a origem. */
        "X-CSRF-Token"?: components["parameters"]["CsrfToken"];
        /** @description Reutilizar a mesma chave e o mesmo payload ao repetir uma operação. */
        "Idempotency-Key": components["parameters"]["IdempotencyKey"];
      };
      path: {
        id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["BatchJobResumeRequest"];
      };
    };
    responses: {
      /** @description Job criado ou recuperado pela mesma chave, no estado atual. */
      202: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["BatchJob"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  listOrders: {
    parameters: {
      query?: {
        /** @description Deslocamento decimal não negativo na coleção autorizada e filtrada; inválidos recebem 422. */
        cursor?: string;
        limit?: number;
        status?: components["schemas"]["OrderStatus"];
        /** @description Somente pedidos do usuário autenticado, identificado pela sessão. */
        mine?: boolean;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Resultado da operação. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["OrderList"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  submitOrder: {
    parameters: {
      query?: never;
      header: {
        /** @description Obrigatório nas escritas com cookie. A API também verifica a origem. */
        "X-CSRF-Token"?: components["parameters"]["CsrfToken"];
        /** @description Reutilizar a mesma chave e o mesmo payload ao repetir uma operação. */
        "Idempotency-Key": components["parameters"]["IdempotencyKey"];
      };
      path: {
        id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["OrderSubmitRequest"];
      };
    };
    responses: {
      /** @description Resultado da operação. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["RegistrationOrder"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  decideOrder: {
    parameters: {
      query?: never;
      header: {
        /** @description Obrigatório nas escritas com cookie. A API também verifica a origem. */
        "X-CSRF-Token"?: components["parameters"]["CsrfToken"];
        /** @description Reutilizar a mesma chave e o mesmo payload ao repetir uma operação. */
        "Idempotency-Key": components["parameters"]["IdempotencyKey"];
      };
      path: {
        id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["OrderDecisionRequest"];
      };
    };
    responses: {
      /** @description Resultado da operação. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["RegistrationOrder"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  listEnrichments: {
    parameters: {
      query?: {
        cursor?: string;
        limit?: number;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Resultado da operação. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["EnrichmentList"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  getEnrichment: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        proposal_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Resultado da operação. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["EnrichmentProposal"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  listMaterials: {
    parameters: {
      query?: {
        cursor?: string;
        limit?: number;
        q?: string;
        status?: components["schemas"]["MaterialStatus"];
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Resultado da operação. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["MaterialList"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  listAuditEvents: {
    parameters: {
      query?: {
        cursor?: string;
        limit?: number;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Resultado da operação. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["AuditList"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  runAgentTurn: {
    parameters: {
      query?: never;
      header: {
        "X-Request-ID": string;
      };
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["AgentRunRequest"];
      };
    };
    responses: {
      /** @description Resultado do Agent, sem publicação nem alteração do ator autenticado. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["AgentRunResponse"];
        };
      };
      /** @description Erro interno padronizado. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Erro interno padronizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Erro interno padronizado. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Erro interno padronizado. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Erro interno padronizado. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Erro interno padronizado. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  submitChatOrder: {
    parameters: {
      query?: never;
      header: {
        /** @description Obrigatório nas escritas com cookie. A API também verifica a origem. */
        "X-CSRF-Token"?: components["parameters"]["CsrfToken"];
        /** @description Reutilizar a mesma chave e o mesmo payload ao repetir uma operação. */
        "Idempotency-Key": components["parameters"]["IdempotencyKey"];
      };
      path: {
        session_id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["ChatSubmitRequest"];
      };
    };
    responses: {
      /** @description Resultado da operação. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ChatSubmitResponse"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  listProposalLots: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Resultado da operação. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["LotList"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  openLotReview: {
    parameters: {
      query?: never;
      header: {
        /** @description Obrigatório nas escritas com cookie. A API também verifica a origem. */
        "X-CSRF-Token"?: components["parameters"]["CsrfToken"];
        /** @description Reutilizar a mesma chave e o mesmo payload ao repetir uma operação. */
        "Idempotency-Key": components["parameters"]["IdempotencyKey"];
      };
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["LotReviewOpenRequest"];
      };
    };
    responses: {
      /** @description Revisão já aberta deste lote. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["LotReview"];
        };
      };
      /** @description Revisão aberta com a amostra sorteada. */
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["LotReview"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  getLotReview: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Resultado da operação. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["LotReview"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  decideLotReview: {
    parameters: {
      query?: never;
      header: {
        /** @description Obrigatório nas escritas com cookie. A API também verifica a origem. */
        "X-CSRF-Token"?: components["parameters"]["CsrfToken"];
        /** @description Reutilizar a mesma chave e o mesmo payload ao repetir uma operação. */
        "Idempotency-Key": components["parameters"]["IdempotencyKey"];
      };
      path: {
        id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["LotDecisionRequest"];
      };
    };
    responses: {
      /** @description Resultado da operação. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["LotDecisionResponse"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  listChatSessions: {
    parameters: {
      query?: {
        limit?: number;
        cursor?: string;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Resultado da operação. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ChatSessionList"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  readChatSession: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        session_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Resultado da operação. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ChatSessionDetail"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  listManualReviews: {
    parameters: {
      query?: {
        run_id?: string;
        reason?: string;
        material_code?: string;
        cursor?: string;
        limit?: number;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Resultado da operação. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ManualReviewList"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  proposeManualReview: {
    parameters: {
      query?: never;
      header: {
        /** @description Obrigatório nas escritas com cookie. A API também verifica a origem. */
        "X-CSRF-Token"?: components["parameters"]["CsrfToken"];
        /** @description Reutilizar a mesma chave e o mesmo payload ao repetir uma operação. */
        "Idempotency-Key": components["parameters"]["IdempotencyKey"];
      };
      path: {
        review_id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["ManualReviewResolution"];
      };
    };
    responses: {
      /** @description Resultado da operação. */
      202: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ManualReviewProposed"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  manualReviewCatalog: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Resultado da operação. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ManualReviewCatalog"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  complementOrder: {
    parameters: {
      query?: never;
      header: {
        /** @description Obrigatório nas escritas com cookie. A API também verifica a origem. */
        "X-CSRF-Token"?: components["parameters"]["CsrfToken"];
        /** @description Reutilizar a mesma chave e o mesmo payload ao repetir uma operação. */
        "Idempotency-Key": components["parameters"]["IdempotencyKey"];
      };
      path: {
        id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["OrderComplementRequest"];
      };
    };
    responses: {
      /** @description Resultado da operação. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["RegistrationOrder"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  getOrderReview: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Resultado da operação. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["OrderReview"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  reopenOrderTechnicalReview: {
    parameters: {
      query?: never;
      header: {
        /** @description Obrigatório nas escritas com cookie. A API também verifica a origem. */
        "X-CSRF-Token"?: components["parameters"]["CsrfToken"];
        /** @description Reutilizar a mesma chave e o mesmo payload ao repetir uma operação. */
        "Idempotency-Key": components["parameters"]["IdempotencyKey"];
      };
      path: {
        id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["OrderReopenReviewRequest"];
      };
    };
    responses: {
      /** @description Resultado da operação. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["RegistrationOrder"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  getAutomaticCorrections: {
    parameters: {
      query?: {
        limit?: number;
        cursor?: string;
      };
      header?: never;
      path: {
        id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Resultado da operação. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["AutomaticCorrectionReport"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  retryAutomaticCorrections: {
    parameters: {
      query?: never;
      header: {
        /** @description Obrigatório nas escritas com cookie. A API também verifica a origem. */
        "X-CSRF-Token"?: components["parameters"]["CsrfToken"];
        /** @description Reutilizar a mesma chave e o mesmo payload ao repetir uma operação. */
        "Idempotency-Key": components["parameters"]["IdempotencyKey"];
      };
      path: {
        id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["AutomaticCorrectionRetryRequest"];
      };
    };
    responses: {
      /** @description Job criado ou recuperado pela mesma chave, no estado atual. */
      202: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["AutomaticCorrectionReport"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  listMaterialRequests: {
    parameters: {
      query?: {
        cursor?: string;
        limit?: number;
        mine?: boolean;
        status?: "EM_IDENTIFICACAO" | "AGUARDANDO_CADASTRO" | "EM_ATENDIMENTO" | "ENCERRADA";
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Solicitação de material no escopo autorizado. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["MaterialRequestList"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  createMaterialRequest: {
    parameters: {
      query?: never;
      header: {
        /** @description Obrigatório nas escritas com cookie. A API também verifica a origem. */
        "X-CSRF-Token"?: components["parameters"]["CsrfToken"];
        /** @description Reutilizar a mesma chave e o mesmo payload ao repetir uma operação. */
        "Idempotency-Key": components["parameters"]["IdempotencyKey"];
      };
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["CreateMaterialRequest"];
      };
    };
    responses: {
      /** @description Solicitação de material no escopo autorizado. */
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["MaterialRequestDetail"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de idempotência ou aviso OPEN_REQUESTS_EXIST: há solicitação aberta do mesmo material e centro. O aviso não grava nada; reenvie com acknowledge_open_requests=true para criar mesmo assim. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json":
            | components["schemas"]["OpenMaterialRequestsConflict"]
            | components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  getMaterialRequest: {
    parameters: {
      query?: {
        /** @description Restringe ao solicitante autenticado, inclusive para revisores. */
        mine?: boolean;
      };
      header?: never;
      path: {
        id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Solicitação de material no escopo autorizado. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["MaterialRequestDetail"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  cancelMaterialRequest: {
    parameters: {
      query?: never;
      header: {
        /** @description Obrigatório nas escritas com cookie. A API também verifica a origem. */
        "X-CSRF-Token"?: components["parameters"]["CsrfToken"];
        /** @description Reutilizar a mesma chave e o mesmo payload ao repetir uma operação. */
        "Idempotency-Key": components["parameters"]["IdempotencyKey"];
      };
      path: {
        id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["CancelMaterialRequest"];
      };
    };
    responses: {
      /** @description Solicitação de material no escopo autorizado. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["MaterialRequestDetail"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  listStockReservations: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Reservas da solicitação. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["StockReservationList"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  reserveStock: {
    parameters: {
      query?: never;
      header: {
        /** @description Obrigatório nas escritas com cookie. A API também verifica a origem. */
        "X-CSRF-Token"?: components["parameters"]["CsrfToken"];
        /** @description Reutilizar a mesma chave e o mesmo payload ao repetir uma operação. */
        "Idempotency-Key": components["parameters"]["IdempotencyKey"];
      };
      path: {
        id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["CreateStockReservation"];
      };
    };
    responses: {
      /** @description Reserva criada, com a disponibilidade depois dela. */
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["StockReservationResult"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  deliverStockReservation: {
    parameters: {
      query?: never;
      header: {
        /** @description Obrigatório nas escritas com cookie. A API também verifica a origem. */
        "X-CSRF-Token"?: components["parameters"]["CsrfToken"];
        /** @description Reutilizar a mesma chave e o mesmo payload ao repetir uma operação. */
        "Idempotency-Key": components["parameters"]["IdempotencyKey"];
      };
      path: {
        id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["DeliverStockReservation"];
      };
    };
    responses: {
      /** @description Entrega registrada como movimento, com a reserva, as parcelas e a disponibilidade depois dela. */
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["StockMovementResult"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  cancelStockReservation: {
    parameters: {
      query?: never;
      header: {
        /** @description Obrigatório nas escritas com cookie. A API também verifica a origem. */
        "X-CSRF-Token"?: components["parameters"]["CsrfToken"];
        /** @description Reutilizar a mesma chave e o mesmo payload ao repetir uma operação. */
        "Idempotency-Key": components["parameters"]["IdempotencyKey"];
      };
      path: {
        id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["CancelStockReservation"];
      };
    };
    responses: {
      /** @description Reserva cancelada, com as parcelas e a disponibilidade depois dela. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["StockReservationResult"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  reverseStockDelivery: {
    parameters: {
      query?: never;
      header: {
        /** @description Obrigatório nas escritas com cookie. A API também verifica a origem. */
        "X-CSRF-Token"?: components["parameters"]["CsrfToken"];
        /** @description Reutilizar a mesma chave e o mesmo payload ao repetir uma operação. */
        "Idempotency-Key": components["parameters"]["IdempotencyKey"];
      };
      path: {
        id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["ReverseStockMovement"];
      };
    };
    responses: {
      /** @description Reversão registrada; a quantidade volta ao disponível do centro e ao pendente da solicitação. */
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["StockMovementResult"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  getStockAvailability: {
    parameters: {
      query: {
        material_id: string;
        center_code: string;
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Disponibilidade no centro. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["StockAvailability"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  forwardMaterialRequestToPurchasing: {
    parameters: {
      query?: never;
      header: {
        /** @description Obrigatório nas escritas com cookie. A API também verifica a origem. */
        "X-CSRF-Token"?: components["parameters"]["CsrfToken"];
        /** @description Reutilizar a mesma chave e o mesmo payload ao repetir uma operação. */
        "Idempotency-Key": components["parameters"]["IdempotencyKey"];
      };
      path: {
        id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["ForwardToPurchasing"];
      };
    };
    responses: {
      /** @description Encaminhamento registrado; representa a demanda para Compras, não compra realizada nem item recebido. */
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["MaterialRequestDetail"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  previewMaterialRequestFulfillment: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Opções de atendimento com a divisão calculada agora; a opção padrão é PARTIAL. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["FulfillmentPreview"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  confirmMaterialRequestFulfillment: {
    parameters: {
      query?: never;
      header: {
        /** @description Obrigatório nas escritas com cookie. A API também verifica a origem. */
        "X-CSRF-Token"?: components["parameters"]["CsrfToken"];
        /** @description Reutilizar a mesma chave e o mesmo payload ao repetir uma operação. */
        "Idempotency-Key": components["parameters"]["IdempotencyKey"];
      };
      path: {
        id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["ConfirmFulfillment"];
      };
    };
    responses: {
      /** @description Parcelas gravadas na mesma solicitação; o encaminhamento é a demanda para Compras, não compra realizada. */
      201: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["FulfillmentResult"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  listPurchaseForwards: {
    parameters: {
      query?: {
        cursor?: string;
        limit?: number;
        center_code?: string;
        status?: "ENCAMINHADO" | "ACEITO" | "DEVOLVIDO" | "CANCELADO";
      };
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Encaminhamentos para compras no escopo autorizado. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["PurchaseForwardList"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  getPurchaseForward: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Encaminhamento para compras no escopo autorizado. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["PurchaseForward"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  acceptPurchaseForward: {
    parameters: {
      query?: never;
      header: {
        /** @description Obrigatório nas escritas com cookie. A API também verifica a origem. */
        "X-CSRF-Token"?: components["parameters"]["CsrfToken"];
        /** @description Reutilizar a mesma chave e o mesmo payload ao repetir uma operação. */
        "Idempotency-Key": components["parameters"]["IdempotencyKey"];
      };
      path: {
        id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["AcceptPurchaseForward"];
      };
    };
    responses: {
      /** @description Encaminhamento aceito por Compras. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["PurchaseForward"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  returnPurchaseForward: {
    parameters: {
      query?: never;
      header: {
        /** @description Obrigatório nas escritas com cookie. A API também verifica a origem. */
        "X-CSRF-Token"?: components["parameters"]["CsrfToken"];
        /** @description Reutilizar a mesma chave e o mesmo payload ao repetir uma operação. */
        "Idempotency-Key": components["parameters"]["IdempotencyKey"];
      };
      path: {
        id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["ReturnPurchaseForward"];
      };
    };
    responses: {
      /** @description Encaminhamento devolvido com motivo. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["PurchaseForward"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
  submitChatMaterialRequest: {
    parameters: {
      query?: never;
      header: {
        /** @description Obrigatório nas escritas com cookie. A API também verifica a origem. */
        "X-CSRF-Token"?: components["parameters"]["CsrfToken"];
        /** @description Reutilizar a mesma chave e o mesmo payload ao repetir uma operação. */
        "Idempotency-Key": components["parameters"]["IdempotencyKey"];
      };
      path: {
        session_id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["ChatMaterialRequest"];
      };
    };
    responses: {
      /** @description Resultado da operação. */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ChatMaterialRequestResponse"];
        };
      };
      /** @description Sessão inválida ou expirada. */
      401: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Ação ou recurso não autorizado. */
      403: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Recurso inexistente ou não visível. */
      404: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Conflito de versão, turno ou idempotência. */
      409: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Payload inválido. */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Limite de chamadas excedido. */
      429: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
      /** @description Dependência indisponível. */
      503: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          "application/json": components["schemas"]["ApiError"];
        };
      };
    };
  };
}
