import { redirect } from "next/navigation";
import { home } from "@/lib/api";
import { identity } from "@/lib/session";

export default async function Index() {
  const user = await identity();
  redirect(user ? home(user) : "/session");
}
