import Link from "next/link";
import { Brand } from "@/components/brand";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return <main className="center-page"><section className="panel auth-panel">
    <Brand />
    <h1>Página no disponible</h1>
    <p>Revisa la dirección o vuelve a tu espacio de trabajo.</p>
    <Button asChild><Link href="/">Volver al inicio</Link></Button>
  </section></main>;
}
