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
  "/api/v1/batch/jobs": {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Listar os jobs mais recentes e o dataset que um novo job usaria. */
    get: operations["listBatchJobs"];
    put?: never;
    /** Iniciar processamento por manifesto sem token do usuário. */
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
    /** Reprocessar um job que falhou, continuando dos checkpoints, sem token do usuário. */
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
}
export type webhooks = Record<string, never>;
export interface components {
  schemas: {
    /** @enum {string} */
    Role: "ROLE_SOLICITANTE" | "ROLE_GOVERNANCA_PDM" | "ROLE_AUDITOR_FISCAL";
    /** @enum {string} */
    PersonaLabel: "SOLICITANTE_OPERACAO" | "GESTOR_CADASTRO" | "AUDITOR_FISCAL";
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
      | "audit:fiscal";
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
        | "enrich_from_trusted_source";
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
    };
    BatchJobList: {
      items: components["schemas"]["BatchJob"][];
      /** @description Dataset que um novo job usaria. */
      latest_dataset_id: string | null;
      next_cursor: string | null;
    };
    AuditEvent: {
      /** Format: uuid */
      id: string;
      actor: string;
      effective_role: components["schemas"]["Role"];
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
      };
      after: {
        materials_total: number;
        active: number;
        blocked: number;
        obsolete: number;
        missing_ncm: number;
        noncanonical_unit: number;
      } | null;
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
      query?: never;
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
  listBatchJobs: {
    parameters: {
      query?: {
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
      /** @description Resultado da operação. */
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
      /** @description Resultado da operação. */
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
        cursor?: string;
        limit?: number;
        status?: components["schemas"]["OrderStatus"];
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
}
