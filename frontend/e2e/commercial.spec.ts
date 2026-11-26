import { expect, test, type Page } from "@playwright/test";

async function enter(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Correo electrónico").fill("platform@example.org");
  await page.getByLabel("Contraseña", { exact: true }).fill("Cuenta ficticia de Playwright");
  await page.getByRole("button", { name: "Ingresar" }).click();
  await expect(page.getByRole("heading", { name: "Resumen de plataforma" })).toBeVisible();
}

test("edición comercial, cobro y respaldo verificado", async ({ page }) => {
  test.setTimeout(90_000);
  await enter(page);
  await page.getByRole("link", { name: "Crear plan" }).click();
  const plan = page.getByRole("dialog", { name: "Crear plan" });
  await plan.getByLabel("Código").fill("cafe-plan");
  await plan.getByLabel("Nombre", { exact: true }).fill("Plan Cafetería");
  await plan.getByLabel("Precio mensual (Q)").fill("165");
  await plan.getByRole("button", { name: "Crear plan" }).click();
  await expect(page.getByRole("heading", { name: "Plan Cafetería" })).toBeVisible();
  await page.getByRole("link", { name: "Restaurantes", exact: true }).click();
  await page.getByRole("button", { name: "Nuevo restaurante" }).click();
  const restaurant = page.getByRole("dialog", { name: "Registrar restaurante" });
  await restaurant.getByLabel("Nombre comercial").fill("Café Comercial");
  await restaurant.getByLabel("Identificador").fill("cafe-comercial");
  await restaurant.getByLabel("Plan").selectOption("cafe-plan");
  await restaurant.getByRole("button", { name: "Registrar restaurante" }).click();
  await page.getByRole("link", { name: "Café Comercial", exact: true }).click();
  await page.getByLabel("Razón social").fill("Café Comercial SA");
  await page.getByRole("button", { name: "Guardar cambios" }).click();
  await expect(page.locator("main").getByRole("status").filter({ hasText: "Cambios guardados" })).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Suspender", exact: true }).click();
  await expect(page.getByRole("button", { name: "Reactivar", exact: true })).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Reactivar", exact: true }).click();
  await expect(page.getByRole("button", { name: "Suspender", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Suscripción", exact: true }).click();
  await page.getByRole("link", { name: "Asignar suscripción" }).click();
  const subscription = page.getByRole("dialog", { name: "Nueva suscripción" });
  await expect(subscription.getByRole("combobox", { name: "Restaurante" })).toHaveValue("cafe-comercial");
  await subscription.getByRole("combobox", { name: "Plan", exact: true }).selectOption("cafe-plan");
  const start = await subscription.getByLabel("Inicio", { exact: true }).inputValue();
  const end = new Date(Date.parse(start) + 31 * 86_400_000).toISOString().slice(0, 10);
  await subscription.getByLabel("Vencimiento", { exact: true }).fill(end);
  await subscription.getByRole("button", { name: "Crear suscripción" }).click();
  await page.getByRole("button", { name: "Ver historial" }).click();
  await page.getByRole("button", { name: "Editar vigencia y gracia" }).click();
  await page.getByRole("spinbutton", { name: "Días de gracia" }).fill("5");
  await page.getByRole("button", { name: "Guardar condiciones" }).click();
  await expect(page.getByText("Suscripción actualizada.", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Registrar pago" }).click();
  const payment = page.getByRole("dialog", { name: "Registrar pago" });
  await payment.getByLabel("Monto (Q)").fill("165");
  await payment.getByRole("combobox", { name: "Método" }).selectOption("Efectivo");
  await payment.getByRole("button", { name: "Registrar pago" }).click();
  await page.getByRole("row", { name: /Café Comercial/ }).getByRole("button", { name: "Ver pago" }).click();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Confirmar pago" }).click();
  await expect(page.getByRole("row", { name: /Café Comercial/ })).toContainText("Confirmado");
  await page.getByRole("link", { name: "Auditoría", exact: true }).click();
  await expect(page.getByText("payment.confirm", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Respaldos", exact: true }).click();
  await page.getByRole("button", { name: "Generar respaldo", exact: true }).click();
  await page.getByRole("button", { name: "Generar y verificar" }).click();
  await expect(page.getByRole("cell", { name: "Verificado" })).toBeVisible();
  await page.getByRole("button", { name: "Verificar", exact: true }).click();
  await expect(page.getByText("Integridad verificada.", { exact: true })).toBeVisible();
});

test("SMTP simulado y personalización del logotipo", async ({ page }) => {
  test.setTimeout(70_000);
  await enter(page);
  await page.getByRole("link", { name: "Correo SMTP", exact: true }).click();
  await page.getByLabel("Servidor SMTP").fill("smtp.example.org");
  await page.getByLabel("Usuario SMTP").fill("envios");
  await page.getByLabel("Contraseña SMTP").fill("Clave solo de pruebas");
  await page.getByLabel("Correo del remitente").fill("envios@example.org");
  await page.getByLabel("Servicio habilitado").check();
  await page.getByRole("button", { name: "Guardar SMTP" }).click();
  await expect(page.getByText("Configuración SMTP guardada.", { exact: true })).toBeVisible();
  await page.getByLabel("Correo destinatario").fill("destino@example.org");
  await page.getByRole("button", { name: "Enviar correo de prueba" }).click();
  await expect(page.getByText(/Prueba simulada/)).toBeVisible();
  await page.getByRole("link", { name: "Logo del login", exact: true }).click();
  const logo = page.locator("section").filter({ has: page.getByRole("heading", { name: "Logo del login", exact: true }) }).first();
  await logo.getByLabel("Archivo para Logo del login").setInputFiles({
    name: "logo.png", mimeType: "image/png",
    buffer: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAAE0lEQVR4nGP8v5QBK2DCLjxYJQBM7gG0qfKk0wAAAABJRU5ErkJggg==", "base64"),
  });
  await logo.getByRole("button", { name: "Guardar imagen" }).click();
  await expect(logo.getByRole("img", { name: "Logo del login" })).toBeVisible();
  const [preview] = await Promise.all([
    page.waitForEvent("popup"), page.getByRole("link", { name: "Previsualizar pantalla de acceso" }).click(),
  ]);
  await expect(preview.getByText("Vista previa del acceso", { exact: true })).toBeVisible();
  await expect(preview.locator(".login-content .brand-image img")).toBeVisible();
});
