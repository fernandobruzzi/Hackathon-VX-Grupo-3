"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Guard } from "@/components/shell/Guard";
import { RequestTracking } from "@/features/requests/RequestTracking";

function Detail() {
  return <RequestTracking id={useSearchParams().get("id")} />;
}

export default function Page() {
  return (
    <Guard perms={["requests:read_own"]}>
      <Suspense fallback={<p role="status">Carregando solicitação…</p>}>
        <Detail />
      </Suspense>
    </Guard>
  );
}
