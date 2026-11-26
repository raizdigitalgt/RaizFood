"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { zodResolver } from "@hookform/resolvers/zod";
import { Building2, Eye, EyeOff, KeyRound, LayoutGrid, LoaderCircle, ShieldCheck } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Brand, useBranding } from "@/components/brand";
import { Button } from "@/components/ui/button";
import { ApiError, api, home, renewSession, type Identity } from "@/lib/api";

export function Field({ label, error, children }: { label: string; error?: string; children: ReactNode }) {
  return <label className="field">
    <span>{label}</span>{children}{error && <small className="field-error">{error}</small>}
  </label>;
}

export function Message({ children }: { children: ReactNode }) {
  return <div className="error-message" role="alert">{children}</div>;
}

function AuthCard({ children }: { children: ReactNode }) {
  return <main className="center-page"><section className="panel auth-panel"><Brand />{children}</section></main>;
}

function Submit({ loading, children }: { loading: boolean; children: ReactNode }) {
  return <Button type="submit" disabled={loading} className="fill">
    {loading && <LoaderCircle className="spin" size={17} />}{children}
  </Button>;
}

const loginSchema = z.object({
  email: z.email("Ingresa un correo válido."),
  password: z.string().min(1, "Ingresa tu contraseña.").max(128),
  remember: z.boolean(),
  otp: z.string().regex(/^(|[0-9]{6})$/, "Ingresa los seis dígitos."),
});

export function Login({ resetComplete = false, preview = false }: { resetComplete?: boolean; preview?: boolean }) {
  const { data: brand } = useBranding();
  const router = useRouter();
  const [shown, setShown] = useState(false);
  const [otpRequired, setOtpRequired] = useState(false);
  const [error, setError] = useState("");
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<z.infer<typeof loginSchema>>({
    resolver: zodResolver(loginSchema), defaultValues: { email: "", password: "", remember: false, otp: "" },
  });
  const signIn = handleSubmit(async (values) => {
    setError("");
    try {
      const user = await api<Identity>("/auth/login", {
        method: "POST", body: JSON.stringify({ ...values, otp: values.otp || undefined }),
      }, false);
      router.replace(home(user));
      router.refresh();
    } catch (reason) {
      if (reason instanceof ApiError && reason.message === "Ingresa el código de autenticación.") {
        setOtpRequired(true);
      } else {
        setError(reason instanceof ApiError ? reason.message : "No se pudo conectar. Intenta nuevamente.");
      }
    }
  });

  return <main className="login-grid">
    <section className="login-content">
      <Brand login />
      <div className="login-main">
        <span className="login-icon"><KeyRound size={22} /></span>
        <h1>Iniciar sesión</h1>
        <p>Ingresa a tu espacio de trabajo de Raíz Food.</p>
        {resetComplete && <div className="success-message" role="status">Contraseña actualizada.</div>}
        <form onSubmit={preview ? (event) => event.preventDefault() : signIn} noValidate>
          {error && <Message>{error}</Message>}
          <Field label="Correo electrónico" error={errors.email?.message}>
            <input type="email" autoComplete="username" placeholder="nombre@restaurante.com" {...register("email")} />
          </Field>
          <Field label="Contraseña" error={errors.password?.message}>
            <span className="password-input">
              <input type={shown ? "text" : "password"} autoComplete="current-password" {...register("password")} />
              <button type="button" className="icon-button" onClick={() => setShown(!shown)}
                aria-label={shown ? "Ocultar contraseña" : "Mostrar contraseña"}>
                {shown ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </span>
          </Field>
          {otpRequired && <Field label="Código de autenticación" error={errors.otp?.message}>
            <input autoFocus inputMode="numeric" autoComplete="one-time-code" maxLength={6} {...register("otp")} />
          </Field>}
          <div className="login-options">
            <label className="check"><input type="checkbox" {...register("remember")} /> Recordar sesión</label>
            <Link href="/forgot-password">¿Olvidaste tu contraseña?</Link>
          </div>
          {!preview && <Submit loading={isSubmitting}>Ingresar</Submit>}
          {preview && <p>Vista previa del acceso</p>}
        </form>
      </div>
      <footer className="login-footer"><ShieldCheck size={16} /><span>{brand?.footer || "Acceso para personal autorizado"}</span>
        {brand?.support_email && <a className="text-link" href={`mailto:${brand.support_email}`}>Soporte</a>}
        {brand?.contact && <span>{brand.contact}</span>}
      </footer>
    </section>
    <aside className={`login-art ${brand?.assets.includes("login-background") ? "custom-login-art" : ""}`}>
      <div className="art-grid" aria-hidden="true">
        <div className="art-tile art-orange"><LayoutGrid size={63} strokeWidth={1.15} /></div>
        <div className="art-tile"><Building2 size={68} strokeWidth={1.15} /></div>
        <div className="art-tile art-wide"><ShieldCheck size={50} strokeWidth={1.15} /><div><i /><i /></div></div>
      </div>
      <div className="art-copy"><p>Gestión de restaurantes</p><h2>Un espacio para cada equipo.</h2></div>
    </aside>
  </main>;
}

const passwordSchema = z.object({ password: z.string().min(12, "Usa al menos 12 caracteres.").max(128) });

export function ResetPassword({ invitation = false }: { invitation?: boolean }) {
  const router = useRouter();
  const [error, setError] = useState("");
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<z.infer<typeof passwordSchema>>({
    resolver: zodResolver(passwordSchema),
  });
  const submit = handleSubmit(async ({ password }) => {
    setError("");
    const token = new URLSearchParams(window.location.hash.slice(1)).get("token");
    if (!token) { setError("Abre el enlace completo que te entregó soporte."); return; }
    try {
      await api(invitation ? "/auth/invitations/accept" : "/auth/reset", { method: "POST", body: JSON.stringify({ token, password }) }, false);
      router.replace(invitation ? "/login" : "/login?restablecida=1");
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "No se pudo conectar. Intenta nuevamente.");
    }
  });
  return <AuthCard><h1>{invitation ? "Aceptar invitación" : "Nueva contraseña"}</h1>
    <form onSubmit={submit} noValidate>
      {error && <Message>{error}</Message>}
      <Field label="Contraseña nueva" error={errors.password?.message}>
        <input type="password" autoComplete="new-password" {...register("password")} />
      </Field>
      <Submit loading={isSubmitting}>{invitation ? "Activar mi cuenta" : "Guardar contraseña"}</Submit>
    </form>
    <Link href="/login">Volver al inicio de sesión</Link>
  </AuthCard>;
}

export function AcceptInvitation() {
  return <ResetPassword invitation />;
}

export function RecoveryInfo() {
  const [notice, setNotice] = useState(false);
  const [error, setError] = useState("");
  const schema = z.object({ email: z.email("Ingresa un correo válido.") });
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
  });
  const submit = handleSubmit(async (body) => {
    setError("");
    try {
      await api("/auth/recover", { method: "POST", body: JSON.stringify(body) }, false);
      setNotice(true);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "No se pudo conectar.");
    }
  });
  return <AuthCard><h1>Recuperar contraseña</h1>
    {notice ? <p role="status">Si tu cuenta está habilitada y el servicio de correo está activo, recibirás un enlace de 15 minutos.</p> :
      <form onSubmit={submit} noValidate>
        {error && <Message>{error}</Message>}
        <Field label="Correo electrónico" error={errors.email?.message}>
          <input type="email" autoComplete="email" {...register("email")} />
        </Field>
        <Submit loading={isSubmitting}>Solicitar enlace</Submit>
      </form>}
    <Link href="/login">Volver al inicio de sesión</Link>
  </AuthCard>;
}

export function Resume({ destination }: { destination?: string }) {
  const router = useRouter();
  const [error, setError] = useState(false);
  useEffect(() => {
    let active = true;
    renewSession().then((user) => {
      if (!active) return;
      router.replace(destination || home(user));
      router.refresh();
    }).catch((reason) => {
      if (!active) return;
      if (reason instanceof ApiError && reason.status === 401) router.replace("/login");
      else setError(true);
    });
    return () => { active = false; };
  }, [destination, router]);
  return <AuthCard><h1>{error ? "Servicio no disponible" : "Verificando sesión"}</h1>
    {error ? <Button onClick={() => window.location.reload()}>Reintentar</Button>
      : <p role="status"><LoaderCircle size={18} className="spin" /> Cargando tu espacio de trabajo…</p>}
  </AuthCard>;
}

export function TenantPicker({ user }: { user: Identity }) {
  const router = useRouter();
  const cache = useQueryClient();
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  async function select(slug: string) {
    setBusy(slug);
    setError("");
    try {
      const current = await api<Identity>("/auth/tenant", { method: "POST", body: JSON.stringify({ slug }) });
      router.replace(home(current));
      router.refresh();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "No se pudo conectar.");
      setBusy("");
    }
  }
  async function logout() {
    setBusy("logout");
    setError("");
    try {
      await api("/auth/logout", { method: "POST" }, false);
      cache.clear();
      router.replace("/login");
      router.refresh();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "No se pudo conectar.");
      setBusy("");
    }
  }
  return <AuthCard><h1>Elige un restaurante</h1>
    {error && <Message>{error}</Message>}
    <div className="tenant-choices">
      {user.restaurants.length === 0 && <p>Tu cuenta todavía no tiene un restaurante activo.</p>}
      {user.restaurants.map((tenant) => <Button key={tenant.slug} variant="outline"
        disabled={Boolean(busy)} onClick={() => select(tenant.slug)}>
        {busy === tenant.slug ? <LoaderCircle size={17} className="spin" /> : <Building2 size={17} />}
        {tenant.name}
      </Button>)}
    </div>
    <Button variant="ghost" disabled={Boolean(busy)} onClick={logout}>Cerrar sesión</Button>
  </AuthCard>;
}
