import { Guard } from "@/components/shell/Guard";
import { ChatPage } from "@/features/chat/ChatPage";

export default function Page() {
  return (
    <Guard perms={["chat:use"]}>
      <ChatPage />
    </Guard>
  );
}
