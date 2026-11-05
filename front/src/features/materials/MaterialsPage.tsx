"use client";

import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import { Badge, Code, Input, PageHeader, Select, Table, Td, Th } from "@/components/ui";
import { MaterialStatusBadge } from "@/components/ui/status";
import { materials } from "@/mocks/data";
import type { MaterialStatus } from "@/types/api";

const flagLabel = {
  SEM_NCM: "sem NCM",
  DUPLICIDADE_SUSPEITA: "duplicidade suspeita",
  UNIDADE_NAO_CANONICA: "unidade fora do padrão",
  ATRIBUTO_FALTANDO: "atributo faltando",
} as const;

/** Busca híbrida (código, texto, atributos). Integração: endpoint de catálogo da API — busca + estoque por centro autorizado. */
export function MaterialsPage() {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<MaterialStatus | "ALL">("ALL");
  const rows = useMemo(() => {
    const t = q.trim().toLowerCase().replace(/"/g, "");
    return materials.filter(
      (m) =>
        (status === "ALL" || m.status === status) &&
        (!t ||
          m.material_code.includes(t) ||
          m.description.toLowerCase().includes(t) ||
          m.pdm_class?.toLowerCase().includes(t)),
    );
  }, [q, status]);

  return (
    <>
      <PageHeader
        n="01"
        eyebrow="Materiais e estoque"
        title="Procure antes de pedir"
        description="Busca por código, descrição ou classe. Códigos bloqueados mostram para qual código ativo apontam."
      />
      <div className="mb-4 flex flex-wrap gap-3">
        <div className="relative min-w-72 flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Ex.: valvula esfera 2pol, LF9009, 6206…"
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
      <Table>
        <thead>
          <tr>
            <Th>Código</Th>
            <Th>Descrição</Th>
            <Th>Classe</Th>
            <Th>Un.</Th>
            <Th>NCM</Th>
            <Th>Estoque por centro</Th>
            <Th>Sinais</Th>
          </tr>
        </thead>
        <tbody>
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
              <Td className="text-xs text-muted">{m.pdm_class}</Td>
              <Td>
                <Code>{m.unit}</Code>
              </Td>
              <Td>
                <Code className={m.ncm ? "" : "font-bold text-aviso"}>{m.ncm ?? "sem NCM"}</Code>
              </Td>
              <Td>
                {m.inventory.length ? (
                  m.inventory.map((i) => (
                    <Code key={i.center_code} className="block">
                      {i.center_code}: {i.quantity} {i.unit}
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
      <p className="mt-3 text-xs text-muted">
        Mostrando {rows.length} de 23.554 registros (amostra do wireframe).
      </p>
    </>
  );
}
