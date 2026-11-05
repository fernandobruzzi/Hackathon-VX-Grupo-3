import { Guard } from "@/components/shell/Guard";
import { AuditPage } from "@/features/audit/AuditPage";

export default function Page() {
  return (
    <Guard perms={["audit:own", "audit:technical", "audit:fiscal"]}>
      <AuditPage />
    </Guard>
  );
}
