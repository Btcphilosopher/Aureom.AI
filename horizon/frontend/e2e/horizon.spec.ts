import path from "node:path";
import { expect, test } from "@playwright/test";
import { completeStepUp, login, supplierBatchId, USERS } from "./helpers";

// Parcours dépendants de l'état : exécution séquentielle sur une base en « état maquette ».
test.describe.configure({ mode: "serial" });

const SECTIONS: [string, string][] = [
  ["Vue d’ensemble", "La maîtrise de votre trésorerie."],
  ["Comptes", "Comptes"],
  ["Paiements", "Paiements"],
  ["Trésorerie", "Trésorerie"],
  ["Financement", "Financement"],
  ["Change", "Change"],
  ["Commerce international", "Commerce international"],
  ["Documents", "Documents"],
  ["Administration", "Administration"],
];

test("connexion MFA et tableau de bord calculé (état maquette)", async ({ page }) => {
  await login(page, USERS.claire);
  await expect(page.getByTestId("env-pill")).toHaveText("ENVIRONNEMENT DE DÉMONSTRATION");
  await expect(page.getByTestId("user-name")).toHaveText("Claire Martin");
  await expect(page.getByTestId("kpi-liquidity-value")).toHaveText(/24,80\s?M€/);
  await expect(page.getByTestId("kpi-payments_to_approve")).toContainText("12");
  await expect(page.getByTestId("kpi-payments_to_approve")).toContainText(/1,24\s?M€/);
  await expect(page.getByTestId("kpi-expected_receipts_7d")).toContainText(/3,60\s?M€/);
  await expect(page.getByTestId("decision-center")).toContainText("Règlement fournisseurs – Déc.");
  await expect(page.getByTestId("decision-center")).toContainText("Bénéficiaire modifié");
  await expect(page.getByTestId("forecast-chart")).toBeVisible();
  await expect(page.getByTestId("band-method")).toContainText("enveloppe");
  await expect(page.getByTestId("group-accounts")).toContainText("Lecture seule");
  await expect(page.getByText("Concept indépendant · Données synthétiques · Aucun service bancaire réel")).toBeVisible();

  // Chaque indicateur ouvre ses données et son calcul.
  await page.getByTestId("kpi-available_liquidity").click();
  const drawer = page.getByTestId("drawer");
  await expect(drawer).toBeVisible();
  await expect(drawer.getByTestId("kpi-formula")).toContainText("solde comptabilisé − réservations actives");
  await expect(drawer).toContainText("Lumière France — Compte principal");
  await expect(drawer).toContainText("Exclus de l’indicateur");
  await page.keyboard.press("Escape");
  for (const key of ["payments_to_approve", "expected_receipts_7d", "alerts"]) {
    await page.getByTestId(`kpi-${key}`).click();
    await expect(page.getByTestId("drawer").getByTestId("kpi-formula")).toBeVisible();
    await page.keyboard.press("Escape");
  }
  // Bascule d'horizon du graphique
  await page.getByRole("button", { name: "7 jours" }).click();
  await expect(page.getByRole("button", { name: "7 jours" })).toHaveAttribute("aria-pressed", "true");
});

test("capture d'écran du tableau de bord (1672×941, ×2)", async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 1672, height: 941 }, deviceScaleFactor: 2, locale: "fr-FR" });
  const page = await ctx.newPage();
  await login(page, USERS.claire);
  await expect(page.getByTestId("forecast-chart")).toBeVisible();
  await expect(page.getByTestId("recent-payments")).toContainText("Règlement fournisseurs");
  await page.mouse.move(5, 900);
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.resolve(__dirname, "../../docs/screenshots/dashboard.png") });
  await ctx.close();
});

test("navigation dans les 9 sections sans erreur", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page, USERS.claire);
  for (const [label, heading] of SECTIONS) {
    await page.getByRole("navigation", { name: "Navigation principale" }).getByRole("link", { name: label }).click();
    await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
    if (label !== "Administration") await expect(page.locator(".alert")).toHaveCount(0);
  }
  expect(errors).toEqual([]);
});

test("l'administrateur technique ne peut pas approuver", async ({ page }) => {
  await login(page, USERS.julien);
  // Julien ne voit pas les paiements : l'accès au lot est refusé et l'approbation l'est aussi.
  const claireCtx = await page.context().browser()!.newContext();
  const cp = await claireCtx.newPage();
  await login(cp, USERS.claire);
  const batchId = await supplierBatchId(cp);
  await claireCtx.close();
  await page.goto(`/paiements/lots/${batchId}`);
  await expect(page.locator(".alert")).toContainText("Action non autorisée");
  await expect(page.locator(".alert")).toContainText("payment.read");
  const r = await page.request.post(`/api/v1/payment-batches/${batchId}/approvals`, {
    headers: { "X-Horizon-CSRF": "1" }, data: { decision: "APPROVE", version: 1 },
  });
  expect(r.status()).toBe(403);
  expect((await r.json()).error.code).toBe("FORBIDDEN");
});

test("la préparatrice ne peut pas approuver son propre lot", async ({ page }) => {
  await login(page, USERS.claire);
  await page.goto(`/paiements/lots/${await supplierBatchId(page)}`);
  await expect(page.getByTestId("batch-status")).toHaveText("En attente d'approbation");
  await expect(page.getByText("la séparation des tâches vous interdit de l’approuver")).toBeVisible();
  await page.getByTestId("approve").click();
  await expect(page.locator(".alert")).toContainText("Accès refusé");
});

test("double approbation : Sophie Bernard puis Marc Lefèvre, avec réauthentification", async ({ browser }) => {
  // Sophie : depuis le centre de décisions
  const s = await (await browser.newContext()).newPage();
  await login(s, USERS.sophie);
  await s.getByTestId("decision-center").getByTestId("decision-item").filter({ hasText: "Règlement fournisseurs – Déc." }).getByRole("link", { name: /Examiner/ }).click();
  await expect(s.getByRole("heading", { level: 1 })).toContainText("Règlement fournisseurs – Déc.");
  await expect(s.getByTestId("batch-total")).toHaveText(/480\s000,00\s€/);
  await expect(s.getByTestId("approval-count")).toHaveText("0/2");
  await s.getByTestId("approve").click();
  await completeStepUp(s);
  await expect(s.getByTestId("approval-count")).toHaveText("1/2");
  await expect(s.getByTestId("approvals")).toContainText("Sophie Bernard");
  // Une seconde approbation par la même personne est refusée
  await s.getByTestId("approve").click();
  await expect(s.locator(".alert")).toContainText("ALREADY_DECIDED");
  await s.screenshot({ path: path.resolve(__dirname, "../../docs/screenshots/lot-approbation.png"), fullPage: true });

  // Marc : quorum atteint → Approuvé (fonds réservés)
  const m = await (await browser.newContext()).newPage();
  await login(m, USERS.marc);
  await m.goto(`/paiements/lots/${await supplierBatchId(m)}`);
  await m.getByTestId("approve").click();
  await completeStepUp(m);
  await expect(m.getByTestId("batch-status")).toHaveText("Approuvé");

  // Exécution simulée via le panneau de démonstration
  await m.goto("/administration");
  await m.getByRole("tab", { name: "Démonstration" }).click();
  await m.getByTestId("run-jobs").click();
  await expect(m.getByText(/tâche\(s\) traitée\(s\)/)).toBeVisible();
  await m.goto(`/paiements/lots/${await supplierBatchId(m)}`);
  await expect(m.getByTestId("batch-status")).toHaveText("Traitement terminé");
  await expect(m.getByTestId("batch-payments")).toContainText("Exécuté selon confirmation");
  // Le détail d'un paiement distingue réception technique, acceptation et exécution
  await m.getByTestId("batch-payments").getByText("Exécuté selon confirmation").first().click();
  await expect(m.getByTestId("payment-steps")).toContainText("Réception technique");
  await expect(m.getByTestId("payment-timeline")).toContainText("Accepté par le système destinataire");
});

test("après exécution : liquidités mises à jour et audit consultable", async ({ page }) => {
  await login(page, USERS.claire);
  await expect(page.getByTestId("kpi-liquidity-value")).toHaveText(/24,32\s?M€/);
  await expect(page.getByTestId("recent-payments")).toContainText("Exécuté");
  await page.goto("/");
  const ines = await (await page.context().browser()!.newContext()).newPage();
  await login(ines, USERS.ines);
  await ines.goto("/administration");
  await ines.getByRole("tab", { name: "Audit et rapports" }).click();
  await expect(ines.getByTestId("audit-events")).toBeVisible();
  await ines.getByTestId("verify-chain").click();
  await expect(ines.getByText(/Chaîne intègre/)).toBeVisible();
  const dl = ines.waitForEvent("download");
  await ines.getByTestId("export-report").click();
  expect((await dl).suggestedFilename()).toMatch(/^horizon-rapport-.*\.zip$/);
});

test("délégation d'approbation plafonnée, avec réauthentification", async ({ page }) => {
  await login(page, USERS.sophie);
  await page.goto("/administration");
  await page.getByRole("tab", { name: "Politiques et délégations" }).click();
  const form = page.getByTestId("delegation-form");
  await form.locator('select[name="delegate_user_id"]').selectOption({ label: "Katrin Weber — Leiterin Finanzen Deutschland" });
  await form.locator('select[name="entity_id"]').selectOption({ label: "Lumière France" });
  // Plafond supérieur à celui de la déléguante (5 M€) : refusé
  await form.locator('input[name="max_amount"]').fill("6000000.00");
  await form.locator('input[name="reason"]').fill("Congés de fin d'année");
  await form.getByRole("button", { name: /Déléguer/ }).click();
  await completeStepUp(page);
  await expect(form.locator(".alert")).toContainText("DELEGATION_EXCEEDS_LIMIT");
  await form.locator('input[name="max_amount"]').fill("200000.00");
  await form.getByRole("button", { name: /Déléguer/ }).click();
  await expect(form).toContainText("Délégation enregistrée");
  await expect(page.locator("table").filter({ hasText: "Katrin Weber" })).toContainText("Active");
});
