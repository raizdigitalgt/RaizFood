import { notFound } from "next/navigation";
import { Shell } from "@/components/shell";
import { Media } from "@/components/restaurant/media";
import { RestaurantAudit, RestaurantSettings, SubscriptionView } from "@/components/restaurant/panel";
import { MenuView, Records } from "@/components/restaurant/records";
import { restaurantNavigation } from "@/lib/restaurant-nav";
import { requireRestaurant } from "@/lib/session";

const extra: Record<string, string[]> = {
  areas: ["tables.view", "tables.manage", "settings.manage"],
  preparation: ["menu.view", "settings.manage"], "payment-methods": ["settings.manage"],
};

export default async function Page({ params, searchParams }: {
  params: Promise<{ slug: string; section: string }>;
  searchParams: Promise<{ new?: string; module?: string; parent?: string }>;
}) {
  const { slug, section } = await params;
  const query = await searchParams;
  const match = restaurantNavigation.flatMap((group) => group.items).find((item) => item.section === section);
  const scopes = match && !("phase" in match) ? match.scopes : extra[section];
  if (!scopes) notFound();
  const user = await requireRestaurant(slug, section, scopes);
  const props = { slug, permissions: user.permissions, initialOpen: query.new === "1" };
  const views: Record<string, React.ReactNode> = {
    menu: <MenuView key={`${query.module}-${query.parent}-${query.new}`} {...props} section={query.module} parent={query.parent} />,
    categories: <Records {...props} resource="categories" />,
    tables: <Records {...props} resource="tables" />,
    areas: <Records {...props} resource="areas" />,
    preparation: <Records {...props} resource="preparation" />,
    customers: <Records {...props} resource="customers" />,
    "payment-methods": <Records {...props} resource="payment-methods" />,
    media: <Media slug={slug} initialOpen={props.initialOpen} />,
    settings: <RestaurantSettings slug={slug} permissions={user.permissions} />,
    subscription: <SubscriptionView slug={slug} />,
    audit: <RestaurantAudit slug={slug} />,
  };
  if (!views[section]) notFound();
  return <Shell user={user}>{views[section]}</Shell>;
}
