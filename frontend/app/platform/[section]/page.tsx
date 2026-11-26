import { notFound } from "next/navigation";
import { Shell } from "@/components/shell";
import {
  Audit, Backups, Customize, Fel, General, Notifications, Security, Smtp, Support, Users,
} from "@/components/platform/admin";
import { Payments, Subscriptions } from "@/components/platform/commerce";
import { Overview } from "@/components/platform/overview";
import { platformNavigation } from "@/lib/platform-nav";
import { requirePlatform } from "@/lib/session";

export default async function Page({ params, searchParams }: {
  params: Promise<{ section: string }>;
  searchParams: Promise<{ new?: string; restaurant?: string; subscription?: string; period?: string }>;
}) {
  const { section } = await params;
  const query = await searchParams;
  const route = platformNavigation.flatMap((group) => group.items).find((item) => item.section === section);
  if (!route) notFound();
  const user = await requirePlatform(`/platform/${section}`, route.scope);
  const open = query.new === "1";
  const views: Record<string, React.ReactNode> = {
    subscriptions: <Subscriptions open={open} restaurant={query.restaurant} />,
    payments: <Payments open={open} subscription={query.subscription} period={query.period} />,
    audit: <Audit />, users: <Users open={open} />, fel: <Fel />,
    reports: <Overview scopes={user.platform_permissions} reports />,
    notifications: <Notifications />, support: <Support />, settings: <General />, smtp: <Smtp />,
    branding: <Customize />, "login-logo": <Customize login />, backups: <Backups open={open} user={user} />,
    security: <Security />,
  };
  if (!views[section]) notFound();
  return <Shell user={user}>{views[section]}</Shell>;
}
