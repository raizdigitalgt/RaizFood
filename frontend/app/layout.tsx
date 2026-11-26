import "@fontsource-variable/plus-jakarta-sans";
import "@/app/globals.css";
import "@/app/pos.css";

import type { Metadata } from "next";
import type { ReactNode } from "react";
import { BrandingChrome } from "@/components/brand";
import { Providers } from "@/components/providers";

export const metadata: Metadata = {
  title: { default: "Raíz Food", template: "%s | Raíz Food" },
  description: "Plataforma de gestión para restaurantes de Raíz Digital.",
};

export default function Layout({ children }: { children: ReactNode }) {
  return <html lang="es-GT"><body><Providers><BrandingChrome />{children}</Providers></body></html>;
}
