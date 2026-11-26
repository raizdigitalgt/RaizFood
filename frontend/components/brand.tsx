"use client";

import Image from "next/image";
import { Sprout } from "lucide-react";
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Branding } from "@/components/platform/admin";

export const useBranding = () => useQuery({
  queryKey: ["commercial", "/branding"], queryFn: () => api<Branding>("/branding"),
});

export function BrandingChrome() {
  const { data } = useBranding();
  useEffect(() => {
    if (!data) return;
    const root = document.documentElement;
    root.style.setProperty("--primary", data.primary);
    const rgb = [1, 3, 5].map((index) => parseInt(data.primary.slice(index, index + 2), 16) / 255)
      .map((part) => part <= .04045 ? part / 12.92 : ((part + .055) / 1.055) ** 2.4);
    root.style.setProperty("--primary-ink", rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722 > .18 ? "#090909" : "#fff");
    const favicon = document.createElement("link");
    if (data.assets.includes("favicon")) {
      favicon.rel = "icon";
      favicon.href = "/api/branding/assets/favicon";
      document.head.appendChild(favicon);
    }
    return () => {
      root.style.removeProperty("--primary");
      root.style.removeProperty("--primary-ink");
      favicon.remove();
    };
  }, [data]);
  return null;
}

export function Brand({ compact = false, login = false }: { compact?: boolean; login?: boolean }) {
  const { data } = useBranding();
  const asset = login && data?.assets.includes("login-logo") ? "login-logo" : data?.assets.includes("logo") ? "logo" : "";
  return <div className="brand">
    <span className={`brand-mark ${asset ? "brand-image" : ""}`}>
      {asset ? <Image unoptimized alt="" width={42} height={42} src={`/api/branding/assets/${asset}`} /> : <Sprout size={23} aria-hidden />}
    </span>
    {!compact && <span className="brand-name">{data && data.name !== "Raíz Food" ? data.name :
      <>Raíz<span>Food</span></>}<small>por Raíz Digital</small></span>}
  </div>;
}
