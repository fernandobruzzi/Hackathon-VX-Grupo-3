"use client";

import Link from "next/link";
import { useState } from "react";
import { Plus } from "lucide-react";
import { Button, Code, PageHeader, Table, Tabs, Td, Th } from "@/components/ui";
import { OrderStatusBadge } from "@/components/ui/status";
import { useAuth } from "@/lib/auth";
import { can } from "@/lib/permissions";
import { fmtDate } from "@/lib/format";
import { orders } from "@/mocks/data";

/** Pedidos de cadastro. Solicitante vê os próprios; Governança também vê a fila de publicação (READY_FOR_REVIEW). */
export function OrdersPage() {
  const { me } = useAuth();
  const gov = can(me, "orders:decide");
  const [tab, setTab] = useState<"mine" | "review">("mine");
  const rows =
    tab === "mine"
      ? orders.filter((o) => o.origin === "CHAT")
      : orders.filter((o) => o.status === "READY_FOR_REVIEW" || o.origin === "IMPORT");
  return (
    <>
      <PageHeader
        n="01"
        eyebrow="Pedidos de cadastro"
        title={tab === "mine" ? "Seus pedidos" : "Pedidos para publicar"}
        description="Todo pedido passa pela checagem de duplicidade antes de virar cadastro. Pedidos incompletos voltam com os campos que faltam."
        actions={
          <Link href="/chat/">
            <Button>
              <Plus className="size-4" /> Novo pedido
            </Button>
          </Link>
        }
      />
      {gov && (
        <div className="mb-4">
          <Tabs
            value={tab}
            onChange={setTab}
            items={[
              { value: "mine", label: "Meus pedidos" },
              {
                value: "review",
                label: "Para publicar",
                count: orders.filter((o) => o.status === "READY_FOR_REVIEW").length,
              },
            ]}
          />
        </div>
      )}
      <Table>
        <thead>
          <tr>
            <Th>Pedido</Th>
            <Th>Texto original</Th>
            <Th>Centro</Th>
            <Th>Classe</Th>
            <Th>Status</Th>
            <Th>Resultado</Th>
            <Th>Atualizado</Th>
          </tr>
        </thead>
        <tbody>
          {rows.map((o) => (
            <tr key={o.id} className="hover:bg-ink/60">
              <Td>
                <Code>{o.id}</Code>
                <p className="mt-1 text-[11px] font-semibold tracking-[0.06em] text-muted uppercase">
                  {o.origin === "IMPORT" ? "importado" : "chat"}
                </p>
              </Td>
              <Td className="max-w-md text-sm">{o.original_text}</Td>
              <Td>
                <Code>{o.center_code}</Code>
              </Td>
              <Td>
                <Code className="text-muted">{o.pdm_class_id ?? "—"}</Code>
              </Td>
              <Td>
                <OrderStatusBadge value={o.status} />
              </Td>
              <Td className="text-sm">
                {o.missing_attributes.length > 0 && (
                  <span className="font-semibold text-aviso">
                    Falta: {o.missing_attributes.join(", ")}
                  </span>
                )}
                {o.material_code && (
                  <span>
                    Use <Code className="text-verde">{o.material_code}</Code>
                  </span>
                )}
                {o.status === "READY_FOR_REVIEW" && gov && tab === "review" && (
                  <Button size="sm" className="mt-1">
                    Publicar cadastro
                  </Button>
                )}
              </Td>
              <Td>
                <Code className="text-muted">{fmtDate(o.updated_at)}</Code>
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
    </>
  );
}
