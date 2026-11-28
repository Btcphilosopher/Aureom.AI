import { expect, type Page } from "@playwright/test";

export const PASSWORD = "Horizon-Demo-2026!";
export const USERS = {
  claire: "claire.martin@lumiere.example",
  sophie: "sophie.bernard@lumiere.example",
  marc: "marc.lefevre@lumiere.example",
  julien: "julien.moreau@lumiere.example",
  ines: "ines.garnier@lumiere.example",
};

export async function currentTotp(page: Page, email: string): Promise<string> {
  const r = await page.request.get("/api/v1/auth/demo-users");
  expect(r.ok()).toBeTruthy();
  const users: { email: string; current_totp: string }[] = (await r.json()).users;
  return users.find((u) => u.email === email)!.current_totp;
}

/** Connexion complète : identifiants fictifs puis code TOTP (affiché uniquement en démonstration). */
export async function login(page: Page, email: string) {
  await page.goto("/login");
  await page.getByTestId("login-email").fill(email);
  await page.getByTestId("login-password").fill(PASSWORD);
  await page.getByTestId("login-submit").click();
  await expect(page.getByTestId("login-code")).toBeVisible();
  await page.getByTestId("login-code").fill(await currentTotp(page, email));
  await page.getByTestId("login-mfa-submit").click();
  await page.waitForURL((u) => u.pathname === "/");
  await expect(page.getByRole("heading", { name: "La maîtrise de votre trésorerie." })).toBeVisible();
}

/** Identifiant du lot fournisseurs de la démonstration (lu via l'API, session courante). */
export async function supplierBatchId(page: Page): Promise<string> {
  const r = await page.request.get("/api/v1/payment-batches?limit=200");
  expect(r.ok()).toBeTruthy();
  const b = (await r.json()).data.find((x: { label: string }) => x.label === "Règlement fournisseurs – Déc.");
  expect(b, "lot « Règlement fournisseurs – Déc. » (état maquette)").toBeTruthy();
  return b.id;
}

/** Saisie du code dans la fenêtre de réauthentification. */
export async function completeStepUp(page: Page) {
  await expect(page.getByRole("dialog", { name: "Réauthentification requise" })).toBeVisible();
  const code = await page.getByTestId("stepup-demo-code").textContent();
  await page.getByTestId("stepup-code").fill(code!.trim());
  await page.getByTestId("stepup-submit").click();
  await expect(page.getByRole("dialog", { name: "Réauthentification requise" })).toBeHidden();
}
