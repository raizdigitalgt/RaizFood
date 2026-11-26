import { redirect } from "next/navigation";
import { Login } from "@/components/auth";
import { home } from "@/lib/api";
import { identity } from "@/lib/session";

export default async function LoginPage({ searchParams }: {
  searchParams: Promise<{ restablecida?: string; preview?: string }>;
}) {
  const user = await identity();
  const { restablecida, preview } = await searchParams;
  const previewMode = preview === "1" && user?.platform_permissions.includes("branding");
  if (user && !previewMode) redirect(home(user));
  return <Login resetComplete={restablecida === "1"} preview={Boolean(previewMode)} />;
}
