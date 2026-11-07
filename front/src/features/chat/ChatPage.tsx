"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { ArrowUp, RotateCcw } from "lucide-react";
import { Button, Eyebrow, Select, Tabs, Seta } from "@/components/ui";
import { cn } from "@/lib/format";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import type { ChatAction, ChatMessage, ChatTurnResponse, ToolCall } from "@/types/api";
import { MaterialCard } from "./MaterialCard";
import { ChatHistory } from "./ChatHistory";
import { ToolCallsPanel } from "./ToolCallsPanel";
import { CandidateList } from "./SimilarCandidates";

const SUGGESTIONS = [
  "Preciso de parafuso sextavado M12x50, aço carbono, zincado branco, DIN 933.",
  "Rolamento rígido de esferas 6205 2RS",
];

function errorMessage(error: unknown) {
  if (error instanceof ApiError && error.status === 409)
    return "Esta conversa mudou em outra aba ou ainda está processando. Atualize a conversa para continuar.";
  if (error instanceof ApiError && error.status === 503)
    return "O assistente não respondeu a tempo. Tente enviar de novo.";
  if (error instanceof ApiError) return error.message;
  return "Não foi possível falar com o servidor.";
}

export function ChatPage() {
  const { me } = useAuth();
  if (!me) return null;
  // Chamadas MCP são diagnóstico técnico: só a role Dev/TI as vê. A API também as omite para os demais.
  const diagnostics = can(me, "chat:diagnostics");
  return <Conversation key={`${me.user.id}:${diagnostics}`} diagnostics={diagnostics} />;
}

function Conversation({ diagnostics }: { diagnostics: boolean }) {
  const { me, api } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [session, setSession] = useState<{ id: string; version: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [last, setLast] = useState<ChatTurnResponse | null>(null);
  const [calls, setCalls] = useState<{ turn: number; call: ToolCall }[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState("");
  const [loading, setLoading] = useState(false);
  const [processing, setProcessing] = useState(false);
  const historyRequest = useRef<AbortController | null>(null);
  const [center, setCenter] = useState("1200");
  const [panel, setPanel] = useState<"ficha" | "mcp">("ficha");
  const [submitted, setSubmitted] = useState<{
    id: string;
    status: "READY_FOR_REVIEW" | "EXISTING";
  } | null>(null);
  const submissionAttempt = useRef<{ sessionId: string; version: number; key: string } | null>(
    null,
  );
  const operationBusy = useRef(false);
  const endRef = useRef<HTMLDivElement>(null);
  const pendingTurn = useRef<AbortController | null>(null);
  const draftRef = useRef<HTMLTextAreaElement>(null);
  const composing = useRef(false);
  const draftGuardRef = useRef<HTMLDivElement>(null);
  // Troca que apagaria texto não enviado: espera a pessoa continuar editando ou descartar.
  const [pendingSwitch, setPendingSwitch] = useState<
    { kind: "new" } | { kind: "open"; id: string } | null
  >(null);
  useEffect(() => {
    if (pendingSwitch) draftGuardRef.current?.querySelector("button")?.focus();
  }, [pendingSwitch]);
  useEffect(
    () => () => {
      historyRequest.current?.abort();
      historyRequest.current = null;
      pendingTurn.current?.abort();
      pendingTurn.current = null;
    },
    [],
  );
  const height = useViewportHeight();
  useEffect(() => {
    // Rola só a área de mensagens: scrollIntoView rolaria a página e esconderia o campo de texto.
    const end = endRef.current;
    const list = end?.closest("[data-chat-scroll]");
    if (list) list.scrollTo({ top: list.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  const send = async (msg: string, action?: ChatAction) => {
    const content = msg.trim();
    if (
      !content ||
      operationBusy.current ||
      submitted ||
      loading ||
      processing ||
      (selected && !session)
    )
      return;
    operationBusy.current = true;
    const turn = new AbortController();
    pendingTurn.current = turn;
    const clientMessageId = crypto.randomUUID();
    setMessages((m) => [
      ...m,
      { id: clientMessageId, author: "user", content, created_at: new Date().toISOString() },
    ]);
    setText("");
    setError(null);
    setBusy(true);
    try {
      const res = await api.request("post", "/api/v1/chat/message", {
        signal: turn.signal,
        body: {
          session_id: session?.id ?? null,
          client_message_id: clientMessageId,
          expected_session_version: session?.version ?? 0,
          message: content,
          center_code: center,
          ...(action ? { action } : {}),
        },
      });
      if (pendingTurn.current !== turn) return;
      setSelected(res.session_id);
      setSession({ id: res.session_id, version: res.session_version });
      setLast(res);
      if (diagnostics)
        setCalls((c) => [
          ...c,
          ...res.tool_calls.map((call) => ({ turn: res.session_version, call })),
        ]);
      setMessages((m) => [
        ...m,
        {
          id: crypto.randomUUID(),
          author: "assistant",
          content: res.assistant_message,
          created_at: new Date().toISOString(),
        },
      ]);
    } catch (e) {
      if (pendingTurn.current !== turn) return;
      // A mensagem não foi gravada: sai da conversa e volta para a caixa de texto.
      setMessages((m) => m.filter((item) => item.id !== clientMessageId));
      setText(content);
      setError(errorMessage(e));
    } finally {
      if (pendingTurn.current === turn) {
        pendingTurn.current = null;
        operationBusy.current = false;
        setBusy(false);
      }
    }
  };

  const submit = async () => {
    if (
      !session ||
      operationBusy.current ||
      submitted ||
      loading ||
      processing ||
      !last?.material_card.can_submit
    )
      return;
    operationBusy.current = true;
    setBusy(true);
    setError(null);
    const previous = submissionAttempt.current;
    const attempt =
      previous?.sessionId === session.id && previous.version === session.version
        ? previous
        : { sessionId: session.id, version: session.version, key: crypto.randomUUID() };
    submissionAttempt.current = attempt;
    try {
      const response = await api.request("post", "/api/v1/chat/{session_id}/submit", {
        params: { session_id: attempt.sessionId },
        body: { expected_session_version: attempt.version },
        idempotencyKey: attempt.key,
      });
      setSession({ id: response.session_id, version: response.session_version });
      setLast(
        (current) =>
          current && {
            ...current,
            order_id: response.order_id,
            session_version: response.session_version,
          },
      );
      setSubmitted({ id: response.order_id, status: response.status });
    } catch (error) {
      setError(errorMessage(error));
    } finally {
      operationBusy.current = false;
      setBusy(false);
    }
  };

  const reset = (keepDraft = false) => {
    // Abortar poupa a conexão; a identidade do turno também barra respostas já recebidas.
    historyRequest.current?.abort();
    historyRequest.current = null;
    setSelected("");
    setLoading(false);
    setProcessing(false);
    pendingTurn.current?.abort();
    pendingTurn.current = null;
    operationBusy.current = false;
    setBusy(false);
    if (!keepDraft) setText("");
    setPendingSwitch(null);
    setMessages([]);
    setSession(null);
    setError(null);
    setLast(null);
    setCalls([]);
    setSubmitted(null);
    submissionAttempt.current = null;
    setPanel("ficha");
  };

  const restore = async (id: string) => {
    if (operationBusy.current && !pendingTurn.current) return;
    // Atualizar a mesma conversa não troca de assunto: o texto em edição continua no campo.
    reset(id !== "" && id === selected);
    if (!id) return;
    const request = new AbortController();
    historyRequest.current = request;
    setSelected(id);
    setLoading(true);
    try {
      const saved = await api.request("get", "/api/v1/chat/sessions/{session_id}", {
        params: { session_id: id },
        signal: request.signal,
      });
      if (historyRequest.current !== request) return;
      setSession({ id: saved.session_id, version: saved.session_version });
      setMessages(saved.messages);
      setCalls(diagnostics ? saved.calls : []);
      setProcessing(saved.processing);
      if (saved.center_code) setCenter(saved.center_code);
      if (saved.submission)
        setSubmitted({ id: saved.submission.order_id, status: saved.submission.status });
      if (saved.material_card)
        setLast({
          request_id: "Histórico",
          session_id: saved.session_id,
          session_version: saved.session_version,
          order_id: saved.order_id,
          status: saved.order_id
            ? "SUBMITTED"
            : saved.material_card.can_submit
              ? "READY_TO_SUBMIT"
              : "NEEDS_INPUT",
          assistant_message: "",
          tool_calls: [],
          material_card: saved.material_card,
        });
    } catch (error) {
      if (historyRequest.current === request) setError(errorMessage(error));
    } finally {
      if (historyRequest.current === request) {
        historyRequest.current = null;
        setLoading(false);
      }
    }
  };

  const run = (action: { kind: "new" } | { kind: "open"; id: string }) =>
    action.kind === "new" ? reset() : restore(action.id);
  const guardDraft = (action: { kind: "new" } | { kind: "open"; id: string }) => {
    const sameConversation = action.kind === "open" && action.id === selected;
    if (!text.trim() || sameConversation) return run(action);
    setPendingSwitch(action);
  };
  const keepEditing = () => {
    setPendingSwitch(null);
    draftRef.current?.focus();
  };
  const discardDraft = () => {
    if (!pendingSwitch) return;
    const action = pendingSwitch;
    setPendingSwitch(null);
    void run(action);
  };

  const replyBusy = busy || loading || processing || submitted !== null || (!!selected && !session);
  // Mesmos itens e regra da ficha: só a última resposta lista a escolha; após o envio, desabilitada.
  const inlineCandidates =
    last && !last.material_card.existing ? (last.material_card.similar_candidates ?? []) : [];

  return (
    <div
      ref={height.ref}
      style={height.value ? { height: height.value } : undefined}
      className="grid grid-cols-[minmax(0,1fr)] gap-6 xl:grid-cols-[minmax(0,1fr)_420px]"
    >
      {/* Conversa */}
      <section className="flex min-h-[calc(100dvh-10rem)] flex-col rounded-lg bg-surface xl:min-h-0">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-surface-2 px-6 py-4">
          <Eyebrow n="01" rule={false}>
            Novo pedido de material
          </Eyebrow>
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-xs font-semibold text-muted" htmlFor="center">
              Centro
            </label>
            <Select
              disabled={busy || session !== null}
              id="center"
              value={center}
              onChange={(e) => setCenter(e.target.value)}
              className="h-9 w-full text-sm sm:w-80"
            >
              {me?.scope.center_codes.map((c) => (
                <option key={c} value={c}>
                  {me.scope.center_names?.[c] || c}
                </option>
              ))}
            </Select>
            {selected && (
              <Button
                size="sm"
                variant="ghost"
                aria-label="Atualizar conversa"
                disabled={loading || busy}
                onClick={() => restore(selected)}
              >
                Atualizar conversa
              </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              disabled={busy && pendingTurn.current === null}
              onClick={() => guardDraft({ kind: "new" })}
            >
              <RotateCcw className="size-4" /> Nova conversa
            </Button>
          </div>
        </div>

        <ChatHistory
          selected={selected}
          onSelect={(id) => guardDraft({ kind: "open", id })}
          revision={session?.version ?? 0}
        />
        {(loading || processing) && (
          <p role="status" className="px-6 py-3 text-sm text-muted">
            {loading
              ? "Carregando conversa…"
              : "Esta conversa está processando um turno. Atualize para acompanhar."}
          </p>
        )}
        <div data-chat-scroll className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
          {messages.length === 0 ? (
            <div className="mx-auto flex max-w-xl flex-col items-start gap-5 pt-8">
              <Seta className="h-12 w-11" />
              <h1 className="text-[28px] leading-tight font-extrabold">O que você precisa?</h1>
              <p className="text-[15px] leading-6 text-muted">
                Descreva o item do seu jeito. O assistente confere se ele já existe, pergunta o que
                faltar e monta o cadastro no padrão PDM antes de ir para revisão.
              </p>
              <div className="flex flex-col gap-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    className="rounded-md bg-ink px-4 py-3 text-left text-sm leading-5 ring-1 ring-surface-2 ring-inset hover:ring-verde"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <ol
              aria-label="Mensagens da conversa"
              className="mx-auto flex max-w-2xl flex-col gap-4"
            >
              {messages.map((m, index) => (
                <li
                  key={m.id}
                  className={cn("flex", m.author === "user" ? "justify-end" : "justify-start")}
                >
                  <div
                    className={cn(
                      "max-w-[85%] rounded-lg px-4 py-3 text-[15px] leading-6",
                      m.author === "user" ? "bg-profundo text-on-profundo" : "bg-ink",
                    )}
                  >
                    {m.author === "assistant" && (
                      <p className="mb-1 text-[11px] font-extrabold tracking-[0.06em] text-verde uppercase">
                        Assistente de cadastro
                      </p>
                    )}
                    <p className="break-words whitespace-pre-line">{m.content}</p>
                    {index === messages.length - 1 &&
                      m.author === "assistant" &&
                      inlineCandidates.length > 0 && (
                        <div className="mt-3">
                          <CandidateList
                            candidates={inlineCandidates}
                            onReply={send}
                            disabled={replyBusy}
                          />
                        </div>
                      )}
                  </div>
                </li>
              ))}
              {busy && (
                <li className="flex">
                  <div className="rounded-lg bg-ink px-4 py-3 font-mono text-xs text-muted">
                    consultando PDM e base de materiais…
                  </div>
                </li>
              )}
              <div ref={endRef} />
            </ol>
          )}
        </div>

        {pendingSwitch && (
          <div
            ref={draftGuardRef}
            role="group"
            aria-labelledby="draft-guard-title"
            onKeyDown={(e) => {
              if (e.key === "Escape") keepEditing();
            }}
            className="mx-4 mt-4 flex flex-wrap items-center gap-3 rounded-md bg-ink p-4 ring-1 ring-aviso ring-inset"
          >
            <p id="draft-guard-title" role="alert" className="min-w-0 flex-1 text-sm leading-5">
              Você tem uma mensagem não enviada.{" "}
              {pendingSwitch.kind === "new"
                ? "Iniciar uma nova conversa apaga esse texto."
                : "Abrir outra conversa apaga esse texto."}
            </p>
            <div className="flex flex-wrap gap-2">
              <Button type="button" size="sm" onClick={keepEditing}>
                Continuar editando
              </Button>
              <Button type="button" size="sm" variant="ghost" onClick={discardDraft}>
                Descartar mensagem
              </Button>
            </div>
          </div>
        )}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(text);
          }}
          className="border-t border-surface-2 p-4"
        >
          {error && (
            <p role="alert" className="mx-auto mb-2 max-w-2xl text-sm text-alerta">
              {error}
            </p>
          )}
          <div className="mx-auto flex max-w-2xl items-end gap-2 rounded-md bg-ink p-2 ring-1 ring-surface-2 ring-inset focus-within:ring-2 focus-within:ring-verde">
            <textarea
              ref={draftRef}
              disabled={
                busy || loading || processing || submitted !== null || (!!selected && !session)
              }
              value={text}
              onChange={(e) => setText(e.target.value)}
              onCompositionStart={() => {
                composing.current = true;
              }}
              onCompositionEnd={() => {
                composing.current = false;
              }}
              onKeyDown={(e) => {
                // Safari pode encerrar a composição antes do Enter que confirma o candidato.
                if (composing.current || e.nativeEvent.isComposing || e.nativeEvent.keyCode === 229)
                  return;
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send(text);
                }
              }}
              rows={2}
              placeholder={
                last?.material_card.missing_attributes.length
                  ? `Ex.: ${last.material_card.missing_attributes[0].toLowerCase()}…`
                  : "Ex.: preciso de 10 parafusos sextavados M16 x 60 galvanizados…"
              }
              aria-label="Mensagem"
              className="flex-1 resize-none bg-transparent px-2 py-1.5 text-[15px] outline-none placeholder:text-muted"
            />
            <Button
              type="submit"
              size="sm"
              disabled={
                !text.trim() ||
                busy ||
                loading ||
                processing ||
                submitted !== null ||
                (!!selected && !session)
              }
              aria-label="Enviar"
            >
              <ArrowUp className="size-4" />
            </Button>
          </div>
          <p className="mx-auto mt-2 max-w-2xl text-[11px] text-muted">
            Validar no chat não publica o material: o pedido passa por Governança PDM e, se mexer em
            NCM, pelo Fiscal.
          </p>
        </form>
      </section>

      {/* Painel lateral */}
      <aside className="flex flex-col gap-4 xl:min-h-0 xl:overflow-y-auto xl:pr-1">
        {diagnostics && (
          <Tabs
            value={panel}
            onChange={setPanel}
            items={[
              { value: "ficha", label: "Ficha" },
              { value: "mcp", label: "Chamadas MCP", count: calls.length },
            ]}
          />
        )}
        {!diagnostics || panel === "ficha" ? (
          last ? (
            <MaterialCard
              card={last.material_card}
              submitted={submitted ?? undefined}
              onSubmit={submit}
              onReply={send}
              busy={replyBusy}
            />
          ) : (
            <div className="rounded-md bg-surface p-6 text-sm leading-6 text-muted">
              A ficha do item aparece aqui: classe PDM, atributos, o que falta, checagem de
              duplicidade e NCM.
            </div>
          )
        ) : (
          <ToolCallsPanel calls={calls} />
        )}
        {last && (
          <p className="font-mono text-[11px] text-muted">
            {last.request_id} · sessão v{last.session_version} · pedido{" "}
            {last.order_id?.slice(0, 8) ?? "não criado"}
          </p>
        )}
      </aside>
    </div>
  );
}

const WIDE = "(min-width: 1280px)";
const BOTTOM_GAP = 32;

/**
 * No desktop, conversa e ficha ocupam exatamente a altura que sobra da janela: o campo de
 * mensagem fica sempre visível e cada coluna rola sozinha. Mede o topo real, porque os avisos
 * acima do chat variam por ambiente e persona. Em telas estreitas as colunas se empilham e a
 * página rola normalmente.
 */
function useViewportHeight() {
  const ref = useRef<HTMLDivElement>(null);
  const [value, setValue] = useState<number | null>(null);
  useLayoutEffect(() => {
    const wide = window.matchMedia(WIDE);
    const measure = () => {
      const element = ref.current;
      if (!element || !wide.matches) return setValue(null);
      const top = element.getBoundingClientRect().top + window.scrollY;
      setValue(Math.max(480, window.innerHeight - top - BOTTOM_GAP));
    };
    measure();
    window.addEventListener("resize", measure);
    wide.addEventListener("change", measure);
    return () => {
      window.removeEventListener("resize", measure);
      wide.removeEventListener("change", measure);
    };
  }, []);
  return { ref, value };
}
