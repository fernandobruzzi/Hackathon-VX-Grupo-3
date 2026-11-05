import { Suspense } from "react";
import { Guard } from "@/components/shell/Guard";
import { RemoteProposalReview } from "@/features/sanitization/RemoteProposalReview";

export default function Page() {
  return (
    <Guard perms={["queue:read", "queue:read_audit"]}>
      <Suspense fallback={<p>Carregando proposta…</p>}>
        <RemoteProposalReview />
      </Suspense>
    </Guard>
  );
}
