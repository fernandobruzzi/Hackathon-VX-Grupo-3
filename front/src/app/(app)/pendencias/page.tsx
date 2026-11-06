import { Suspense } from "react";
import { Guard } from "@/components/shell/Guard";
import { ManualReviewsPage } from "@/features/manual-reviews/ManualReviewsPage";

export default function Page() {
  return (
    <Guard perms={["merge:decide"]}>
      <Suspense fallback={<p>Carregando pendências…</p>}>
        <ManualReviewsPage />
      </Suspense>
    </Guard>
  );
}
