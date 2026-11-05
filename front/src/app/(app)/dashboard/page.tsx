import { Guard } from "@/components/shell/Guard";
import { DashboardPage } from "@/features/dashboard/DashboardPage";

export default function Page() {
  return (
    <Guard perms={["metrics:quality"]}>
      <DashboardPage />
    </Guard>
  );
}
