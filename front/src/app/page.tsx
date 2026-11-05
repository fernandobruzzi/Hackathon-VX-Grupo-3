"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

export default function Home() {
  const { me, ready } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (ready) router.replace(me ? "/chat/" : "/login/");
  }, [ready, me, router]);
  return null;
}
