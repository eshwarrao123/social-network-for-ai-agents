import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: ["**/bff.spec.ts", "**/utils.spec.ts"],
  testIgnore: "**/*.browser.spec.ts",
  reporter: "list",
});
