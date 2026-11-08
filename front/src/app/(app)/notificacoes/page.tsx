import { Guard } from "@/components/shell/Guard";
import { NotificationsPage } from "@/features/notifications/NotificationsPage";

export default function Page() {
  return (
    <Guard perms={["requests:read_own"]}>
      <NotificationsPage />
    </Guard>
  );
}
