"use client";

import { Brand } from "@/components/brand";
import { Button } from "@/components/ui/button";

export default function ErrorPage({ reset }: { reset: () => void }) {
  return <main className="center-page"><section className="panel auth-panel">
    <Brand />
    <h1>Servicio no disponible</h1>
    <p>La aplicación no pudo recuperar la información. Intenta nuevamente.</p>
    <Button onClick={reset}>Reintentar</Button>
  </section></main>;
}
