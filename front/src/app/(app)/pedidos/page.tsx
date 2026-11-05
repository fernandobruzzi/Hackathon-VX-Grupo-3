import { Guard } from "@/components/shell/Guard";
import { OrdersPage } from "@/features/orders/OrdersPage";

export default function Page() {
  return (
    <Guard perms={["orders:read_own"]}>
      <OrdersPage />
    </Guard>
  );
}
