import {
  Bell, Building2, ChartNoAxesCombined, CreditCard, DatabaseBackup, Headphones, Image,
  LayoutDashboard, Mail, Palette, Receipt, Settings, Shield, UsersRound, Wallet,
  CalendarClock, ClipboardList,
} from "lucide-react";

export const platformNavigation = [
  { heading: "Plataforma", items: [
    { section: "dashboard", label: "Dashboard", icon: LayoutDashboard, scope: "dashboard" },
    { section: "restaurants", label: "Restaurantes", icon: Building2, scope: "restaurants" },
    { section: "plans", label: "Planes", icon: CreditCard, scope: "plans" },
    { section: "subscriptions", label: "Suscripciones", icon: CalendarClock, scope: "subscriptions" },
    { section: "payments", label: "Pagos", icon: Wallet, scope: "payments" },
    { section: "audit", label: "Auditoría", icon: ClipboardList, scope: "audit" },
    { section: "users", label: "Usuarios", icon: UsersRound, scope: "users" },
    { section: "fel", label: "FEL general", icon: Receipt, scope: "fel" },
  ] },
  { heading: "Gestión comercial", items: [
    { section: "reports", label: "Reportes", icon: ChartNoAxesCombined, scope: "reports" },
    { section: "notifications", label: "Notificaciones", icon: Bell, scope: "notifications" },
    { section: "support", label: "Soporte", icon: Headphones, scope: "support" },
  ] },
  { heading: "Configuración", items: [
    { section: "settings", label: "Configuración general", icon: Settings, scope: "settings" },
    { section: "smtp", label: "Correo SMTP", icon: Mail, scope: "smtp" },
    { section: "branding", label: "Personalización", icon: Palette, scope: "branding" },
    { section: "login-logo", label: "Logo del login", icon: Image, scope: "branding" },
    { section: "backups", label: "Respaldos", icon: DatabaseBackup, scope: "backups" },
    { section: "security", label: "Seguridad", icon: Shield, scope: "settings" },
  ] },
];
