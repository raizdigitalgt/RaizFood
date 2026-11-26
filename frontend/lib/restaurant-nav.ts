import {
  Armchair, Banknote, BookOpen, ClipboardList, CookingPot, Database, Files, Images,
  LayoutDashboard, ListTree, Receipt, Settings, ShoppingBag, Truck, UserRound, UsersRound,
  Wallet, ChartNoAxesCombined, Printer, Monitor, NotebookPen,
} from "lucide-react";

export const restaurantNavigation = [
  { heading: "Principal", items: [
    { section: "dashboard", label: "Dashboard", icon: LayoutDashboard, scopes: ["dashboard.view"] },
    { section: "pos", label: "Punto de venta", icon: Monitor, scopes: ["pos.access"] },
    { section: "tables", label: "Mesas", icon: Armchair, scopes: ["tables.view"] },
    { section: "orders", label: "Pedidos", icon: ClipboardList, scopes: ["orders.view"] },
    { section: "kitchen", label: "Comandas", icon: CookingPot, scopes: ["kitchen.view"] },
  ] },
  { heading: "Gestión", items: [
    { section: "menu", label: "Menú", icon: BookOpen, scopes: ["menu.view"] },
    { section: "categories", label: "Categorías", icon: ListTree, scopes: ["menu.view", "categories.view"] },
    { section: "inventory", label: "Inventario", icon: Database, scopes: ["inventory.view"], phase: 6 },
    { section: "recipes", label: "Recetas", icon: NotebookPen, scopes: ["recipes.manage"], phase: 6 },
    { section: "purchases", label: "Compras", icon: ShoppingBag, scopes: ["purchases.manage"], phase: 6 },
    { section: "suppliers", label: "Proveedores", icon: Truck, scopes: ["suppliers.manage"], phase: 6 },
    { section: "customers", label: "Clientes", icon: UserRound, scopes: ["customers.view", "customers.manage"] },
  ] },
  { heading: "Finanzas", items: [
    { section: "cash", label: "Caja", icon: Wallet, scopes: ["cash.open"], phase: 7 },
    { section: "receipts", label: "Comprobantes", icon: Receipt, scopes: ["receipts.print"], phase: 7 },
    { section: "fel", label: "Facturación FEL", icon: Files, scopes: ["fel.issue"], phase: 7 },
    { section: "reports", label: "Reportes", icon: ChartNoAxesCombined, scopes: ["reports.view"], phase: 8 },
  ] },
  { heading: "Administración", items: [
    { section: "team", label: "Usuarios y roles", icon: UsersRound,
      scopes: ["users.manage", "users.invite", "roles.manage"], accessible: "Equipo" },
    { section: "printers", label: "Impresoras", icon: Printer, scopes: ["printers.manage"], phase: 5 },
    { section: "media", label: "Multimedia", icon: Images, scopes: ["media.manage"] },
    { section: "settings", label: "Configuración", icon: Settings, scopes: ["settings.manage"] },
    { section: "subscription", label: "Mi suscripción", icon: Banknote, scopes: ["subscription.view"] },
    { section: "audit", label: "Auditoría", icon: ClipboardList, scopes: ["audit.view"] },
  ] },
];

export const restaurantRights = (permissions: string[], ...choices: string[]) =>
  choices.some((permission) => permissions.includes(permission));
