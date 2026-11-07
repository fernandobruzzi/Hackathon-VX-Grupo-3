"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Search } from "lucide-react";
import {
  Badge,
  Button,
  Code,
  EmptyState,
  Input,
  PageHeader,
  Select,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { MaterialStatusBadge } from "@/components/ui/status";
import { ApiError, createApiClient } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Material, MaterialStatus } from "@/types/api";

const flagLabel = {
  SEM_NCM: "sem NCM",
  DUPLICIDADE_SUSPEITA: "duplicidade suspeita",
  UNIDADE_NAO_CANONICA: "unidade fora do padrão",
  ATRIBUTO_FALTANDO: "atributo faltando",
} as const;
const PAGE_SIZE = 20;
const DEBOUNCE_MS = 300;

function errorMessage(error: unknown) {
  if (error instanceof ApiError && error.status === 403)
    return "Seu perfil não pode consultar materiais.";
  if (error instanceof ApiError) return error.message;
  return "Não foi possível falar com o servidor.";
}

/** Busca no cadastro mestre por código ou descrição, com estoque só dos centros autorizados. */
export function MaterialsPage() {
  const { me } = useAuth();
  const api = useMemo(() => createApiClient({ getCsrfToken: () => me?.csrf_token ?? null }), [me]);
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<MaterialStatus | "ALL">("ALL");
  const [rows, setRows] = useState<Material[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Ignora respostas de buscas antigas que chegam depois da atual.
  const latest = useRef(0);

  useEffect(() => {
    const timer = setTimeout(() => setQuery(q.trim()), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [q]);

  const load = useCallback(
    async (after: string | null) => {
      const id = ++latest.current;
      setLoading(true);
      setError(null);
      try {
        const page = await api.request("get", "/api/v1/materials", {
          query: {
            q: query || undefined,
            status: status === "ALL" ? undefined : status,
            limit: PAGE_SIZE,
            cursor: after ?? undefined,
          },
        });
        if (id !== latest.current) return;
        setRows((current) => (after ? [...current, ...page.items] : page.items));
        setCursor(page.next_cursor);
      } catch (e) {
        if (id !== latest.current) return;
        setError(errorMessage(e));
        if (!after) setRows([]);
      } finally {
        if (id === latest.current) setLoading(false);
      }
    },
    [api, query, status],
  );

  useEffect(() => {
    void load(null);
  }, [load]);

  const firstLoad = loading && rows.length === 0 && !error;

  return (
    <>
      <PageHeader
        n="01"
        eyebrow="Materiais e estoque"
        title="Procure antes de pedir"
        description="Busca por código ou descrição no cadastro. Códigos bloqueados mostram para qual código ativo apontam. O estoque aparece só nos seus centros."
      />
      <div className="mb-4 flex flex-wrap gap-3">
        <div className="relative min-w-72 flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Ex.: valvula esfera 2pol, LF9009, 10293847"
            className="pl-9"
            aria-label="Buscar materiais"
          />
        </div>
        <Select
          value={status}
          onChange={(e) => setStatus(e.target.value as MaterialStatus | "ALL")}
          className="w-44"
          aria-label="Status"
        >
          <option value="ALL">Todos os status</option>
          <option value="ATIVO">Ativo</option>
          <option value="BLOQUEADO">Bloqueado</option>
          <option value="OBSOLETO">Obsoleto</option>
        </Select>
      </div>
      {error && (
        <div role="alert" className="mb-4 flex flex-wrap items-center gap-3 text-sm text-alerta">
          {error}
          <Button variant="ghost" size="sm" onClick={() => void load(rows.length ? cursor : null)}>
            Tentar de novo
          </Button>
        </div>
      )}
      {firstLoad ? (
        <p aria-live="polite" className="text-sm text-muted">
          Buscando materiais…
        </p>
      ) : !error && rows.length === 0 ? (
        <EmptyState title="Nenhum material encontrado">
          {query
            ? "Nenhum código ou descrição tem todos os termos buscados. Tente menos palavras ou outro status."
            : "Não há materiais com esse status."}
        </EmptyState>
      ) : rows.length > 0 ? (
        <>
          <Table>
            <thead>
              <tr>
                <Th>Código</Th>
                <Th>Descrição</Th>
                <Th>Classe</Th>
                <Th>Un.</Th>
                <Th>NCM</Th>
                <Th>Estoque nos seus centros</Th>
                <Th>Sinais</Th>
              </tr>
            </thead>
            <tbody aria-busy={loading}>
              {rows.map((m) => (
                <tr key={m.material_code} className="hover:bg-ink/60">
                  <Td>
                    <Code>{m.material_code}</Code>
                    <div className="mt-1">
                      <MaterialStatusBadge value={m.status} />
                    </div>
                    {m.active_code_target && (
                      <p className="mt-1 font-mono text-[11px] font-semibold text-verde">
                        usar {m.active_code_target}
                      </p>
                    )}
                  </Td>
                  <Td className="font-mono text-[13px]">{m.description}</Td>
                  <Td className="text-xs text-muted">{m.pdm_class ?? "—"}</Td>
                  <Td>
                    <Code>{m.unit}</Code>
                  </Td>
                  <Td>
                    <Code className={m.ncm ? "" : "font-bold text-aviso"}>
                      {m.ncm ?? "sem NCM"}
                    </Code>
                  </Td>
                  <Td>
                    {m.inventory.length ? (
                      m.inventory.map((i) => (
                        <Code key={`${i.center_code}-${i.unit}`} className="block">
                          {i.center_name || i.center_code}: {i.quantity} {i.unit}
                        </Code>
                      ))
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </Td>
                  <Td>
                    <div className="flex flex-wrap gap-1">
                      {m.flags.map((f) => (
                        <Badge key={f} tone="warning">
                          {flagLabel[f]}
                        </Badge>
                      ))}
                    </div>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
          <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-muted">
            <span aria-live="polite">
              {loading ? "Carregando…" : `Mostrando ${rows.length} materiais`}
            </span>
            {cursor && !loading && (
              <Button variant="ghost" size="sm" onClick={() => void load(cursor)}>
                Carregar mais
              </Button>
            )}
          </div>
        </>
      ) : null}
    </>
  );
}
