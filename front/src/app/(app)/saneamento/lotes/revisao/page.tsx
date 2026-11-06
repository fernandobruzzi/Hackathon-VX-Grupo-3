import { Suspense } from "react";
import { Guard } from "@/components/shell/Guard";
import { LotReviewPage } from "@/features/sanitization/LotReviewPage";

export default function Page() {
  return (
    <Guard perms={["merge:decide"]}>
      <Suspense fallback={<p>Carregando lote…</p>}>
        <LotReviewPage />
      </Suspense>
    </Guard>
  );
}
