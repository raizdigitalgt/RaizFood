import { expect, test, type BrowserContext } from "@playwright/test";

const password = "Cuenta ficticia de Playwright";
const slug = "comedor-pos";
const root = `/api/restaurants/${slug}`;
const route = `/app/${slug}`;
const email = (role: string) => `${role}@${slug}.example.org`;

async function signIn(context: BrowserContext, origin: string, username: string) {
  const response = await context.request.post("/api/auth/login", {
    headers: { Origin: origin }, data: { email: username, password },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
}

test("POS de mesero, cocina por estación, cuenta dividida y recuperación móvil", async ({ page, browser, baseURL }) => {
  test.setTimeout(120_000);
  const origin = new URL(baseURL!).origin;
  const admin = page.context();
  const waiter = await browser.newContext({ baseURL });
  const cook = await browser.newContext({ baseURL, viewport: { width: 1440, height: 900 } });
  const cashier = await browser.newContext({ baseURL, viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const headers = { Origin: origin };
  async function save(path: string, data: object, method: "POST" | "PUT" = "POST") {
    const response = await admin.request.fetch(path, { method, data, headers });
    expect(response.ok(), await response.text()).toBeTruthy();
    return response.json();
  }
  const record = (resource: string, body: object) => save(`${root}/records/${resource}`, body);
  try {
    await signIn(admin, origin, "platform@example.org");
    await save("/api/platform/restaurants", { slug, name: "Comedor POS", plan_code: "basic" });
    for (const role of ["admin", "waiter", "cook", "cashier"]) {
      await save(`/api/platform/restaurants/${slug}/members`, {
        email: email(role), name: { admin: "Administración POS", waiter: "Mesera POS", cook: "Cocinera POS", cashier: "Caja POS" }[role],
        password, role_code: role,
      });
    }
    await admin.request.post("/api/auth/logout", { headers });
    await signIn(admin, origin, email("admin"));
    const room = await record("areas", { name: "Terraza" });
    const first = await record("tables", { number: "01", area_id: room.id, capacity: 4 });
    const second = await record("tables", { number: "02", area_id: room.id, capacity: 4 });
    const kitchen = await record("preparation", { name: "Cocina" });
    const bar = await record("preparation", { name: "Barra" });
    const category = await record("categories", { name: "Clásicos" });
    const group = await record("groups", { name: "Complemento", minimum: 1, maximum: 1 });
    await record("modifiers", { name: "Queso extra", group_id: group.id, price_cents: 300 });
    const taco = await record("items", {
      name: "Taco de la casa", category_id: category.id, code: "TC-01", price_cents: 1500,
      preparation_id: kitchen.id, group_ids: [group.id],
    });
    const variant = await record("variants", {
      name: "Grande", item_id: taco.id, code: "TC-01-G", price_cents: 500, pricing: "adjust",
    });
    await record("items", {
      name: "Limonada", category_id: category.id, code: "BR-01", price_cents: 900, preparation_id: bar.id,
    });
    const options = await (await admin.request.get(`${root}/pos/options`)).json();
    const cookId = options.station_staff.find((member: { name: string }) => member.name === "Cocinera POS").id;
    await page.goto(`${route}/pos-settings`);
    await page.getByRole("combobox", { name: "Integrante de cocina" }).selectOption(cookId);
    await page.getByRole("checkbox", { name: "Cocina", exact: true }).check();
    await page.getByRole("button", { name: "Guardar estaciones" }).click();
    await expect(page.getByText("Estaciones guardadas.", { exact: true })).toBeVisible();
    await Promise.all([signIn(waiter, origin, email("waiter")), signIn(cook, origin, email("cook")),
      signIn(cashier, origin, email("cashier"))]);
    const waiterPage = await waiter.newPage();
    const kitchenPage = await cook.newPage();
    const cashierPage = await cashier.newPage();
    await kitchenPage.goto(`${route}/kitchen`);
    await expect(kitchenPage.getByRole("heading", { name: "Pantalla de cocina" })).toBeVisible();
    await expect(kitchenPage.getByText("En vivo", { exact: true })).toBeVisible({ timeout: 15000 });
    await waiterPage.goto(`${route}/tables`);
    const floor = waiterPage.locator(".pos-floor");
    await floor.locator("article").filter({ hasText: "Mesa 01" }).getByRole("link", { name: "Seleccionar mesa" }).click();
    const start = waiterPage.getByRole("dialog", { name: "Nuevo pedido" });
    await expect(start.getByLabel("Mesa disponible")).toHaveValue(first.id);
    await start.getByLabel("Comensales").fill("2");
    await start.getByLabel("Observaciones del pedido").fill("Invitados");
    await start.getByRole("button", { name: "Crear borrador" }).click();
    await expect(waiterPage).toHaveURL(/order=/);
    const orderId = new URL(waiterPage.url()).searchParams.get("order");
    expect(orderId).toBeTruthy();
    const search = waiterPage.getByRole("textbox", { name: "Buscar productos" });
    await search.fill("tc-01");
    await waiterPage.getByRole("button", { name: /Taco de la casa/ }).click();
    const editor = waiterPage.getByRole("dialog", { name: "Taco de la casa" });
    await editor.getByLabel("Variante").selectOption(variant.id);
    await editor.getByLabel(/Queso extra/).check();
    await editor.getByLabel("Cantidad").fill("2");
    await editor.getByLabel("Observaciones del producto").fill("Sin cebolla");
    await editor.getByRole("button", { name: /Agregar al pedido/ }).click();
    await expect(editor).toBeHidden();
    await search.fill("Limonada");
    await waiterPage.getByRole("button", { name: /Limonada/ }).click();
    const cart = waiterPage.getByRole("complementary", { name: "Carrito del pedido" });
    await expect(cart.getByText("Limonada", { exact: true })).toBeVisible();
    await waiterPage.reload();
    await expect(cart.getByText(/Grande · Queso extra · Sin cebolla/)).toBeVisible();
    await cart.getByRole("button", { name: "Guardar pedido" }).click();
    await expect(cart.getByText("Confirmado", { exact: true })).toBeVisible();
    await cart.getByRole("button", { name: "Enviar a cocina" }).click();
    const grill = kitchenPage.getByRole("article").filter({ hasText: "Taco de la casa" });
    await expect(grill.getByText("Sin cebolla", { exact: true })).toBeVisible();
    await expect(kitchenPage.getByText("1 × Limonada")).toHaveCount(0);
    await grill.getByRole("button", { name: "Iniciar preparación" }).click();
    await expect(cart.getByText("En preparación", { exact: true }).first()).toBeVisible();
    await grill.getByRole("button", { name: "Marcar todo listo" }).click();
    await expect(cart.getByText("Listo", { exact: true })).toBeVisible();
    await search.fill("Limonada");
    await waiterPage.getByRole("button", { name: /Limonada/ }).click();
    await expect(cart.getByText("Limonada", { exact: true })).toHaveCount(2);
    await cart.getByRole("button", { name: "Enviar a cocina" }).click();
    await cart.getByRole("button", { name: "Comandas", exact: true }).click();
    const tickets = waiterPage.getByRole("dialog", { name: "Comandas del pedido" });
    await expect(tickets.getByLabel("Comanda").locator("option")).toHaveCount(3);
    await expect(tickets.getByLabel("Comanda").locator("option").filter({ hasText: "Adicional" })).toHaveCount(1);
    await tickets.getByRole("button", { name: "Cerrar", exact: true }).click();
    await cart.getByRole("button", { name: "Actividad" }).click();
    const history = waiterPage.getByRole("dialog", { name: "Historial del pedido" });
    await expect(history.getByText("Comandas enviadas", { exact: true })).toHaveCount(2);
    await history.getByRole("button", { name: "Cerrar", exact: true }).click();
    await expect(cart.getByRole("button", { name: "Trasladar mesa" })).toHaveCount(0);

    await page.goto(`${route}/pos?order=${orderId}`);
    await page.getByRole("button", { name: "Trasladar mesa" }).click();
    const transfer = page.getByRole("dialog", { name: "Trasladar mesa" });
    await transfer.getByLabel("Mesa de destino").selectOption(second.id);
    await transfer.getByLabel("Motivo").fill("Cambio solicitado");
    await transfer.getByRole("button", { name: "Trasladar mesa" }).click();
    await expect(cart.getByText(/02 · 2 comensales/)).toBeVisible();
    await cashierPage.goto(`${route}/pos?order=${orderId}`);
    await cashierPage.getByRole("button", { name: /Pedido ·/ }).click();
    const mobileCart = cashierPage.getByRole("complementary", { name: "Carrito del pedido" });
    await mobileCart.getByRole("button", { name: "Dividir cuenta" }).click();
    const split = cashierPage.getByRole("dialog", { name: "Dividir cuenta" });
    await split.getByLabel(/Taco de la casa/).fill("1");
    await split.getByRole("button", { name: "Dividir cuenta" }).click();
    await expect(split).toBeHidden();
    await mobileCart.getByRole("button", { name: "Solicitar cuenta" }).click();
    await expect(mobileCart.getByText("Cuenta solicitada", { exact: true })).toBeVisible();
    await mobileCart.getByRole("button", { name: "Ver cuenta" }).click();
    const bill = cashierPage.getByRole("dialog", { name: "Cuenta preliminar" });
    await expect(bill).toBeVisible();
    await bill.getByRole("combobox", { name: "Cuenta", exact: true }).selectOption({ index: 2 });
    const receipt = bill.getByRole("article", { name: "Vista previa de 80 milímetros" });
    await expect(receipt.getByText("1 × Taco de la casa")).toBeVisible();
    await expect(receipt.getByText(/NO ES FACTURA FISCAL/)).toBeVisible();
    await bill.getByRole("button", { name: "Cerrar", exact: true }).click();
    await expect(mobileCart.getByRole("button", { name: "Cobrar pedido", exact: true })).toBeDisabled();
    await cashierPage.reload();
    await cashierPage.getByRole("button", { name: /Pedido ·/ }).click();
    await expect(mobileCart.getByText("Cuenta solicitada", { exact: true })).toBeVisible();
    await cashierPage.routeWebSocket("**/events", (socket) => socket.close());
    await cashierPage.reload();
    await expect(cashierPage.getByText("Actualización periódica", { exact: true })).toBeVisible();
    await cashierPage.getByRole("button", { name: /Pedido ·/ }).click();
    await cart.getByRole("button", { name: "Reabrir cuenta" }).click();
    await expect(mobileCart.getByText("Pendiente de cobro", { exact: true })).toBeVisible({ timeout: 12000 });
    await mobileCart.getByRole("button", { name: "Solicitar cuenta" }).click();
    await expect(mobileCart.getByText("Cuenta solicitada", { exact: true })).toBeVisible();

    await waiterPage.goto(`${route}/orders`);
    await waiterPage.getByRole("searchbox", { name: "Buscar pedido" }).fill("1");
    await expect(waiterPage.getByRole("link", { name: "Abrir #1", exact: true })).toBeVisible();
    await kitchenPage.getByRole("combobox", { name: "Estación" }).selectOption(kitchen.id);
    await expect(grill.getByText("Sin cebolla", { exact: true }).first()).toBeVisible();
  } finally {
    await Promise.all([waiter.close(), cook.close(), cashier.close()]);
  }
});
