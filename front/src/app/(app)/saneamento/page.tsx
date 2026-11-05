import { Guard } from "@/components/shell/Guard";
import { QueuePage } from "@/features/sanitization/QueuePage";

export default function Page() {
  return (
    <Guard perms={["queue:read", "queue:read_audit"]}>
      <QueuePage />
    </Guard>
  );
}
