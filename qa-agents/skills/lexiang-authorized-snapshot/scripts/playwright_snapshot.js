#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const { chromium } = require("/Users/liushanshan/code/QA/bug-finder/node_modules/playwright");

async function main() {
  const [url, jsFile, profileDir, headedValue] = process.argv.slice(2);
  if (!url || !jsFile || !profileDir) throw new Error("url, jsFile and profileDir are required");
  const context = await chromium.launchPersistentContext(profileDir, {
    executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    headless: headedValue !== "true",
    viewport: { width: 1440, height: 1000 },
  });
  try {
    const page = context.pages()[0] || await context.newPage();
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 });
    await page.waitForTimeout(3000);
    const expression = fs.readFileSync(jsFile, "utf8");
    const value = await page.evaluate(expression => {
      // The expression is fixed Skill code, never page-provided content.
      return (0, eval)(expression);
    }, expression);
    process.stdout.write(typeof value === "string" ? value : JSON.stringify(value));
  } finally {
    await context.close();
  }
}

main().catch(error => {
  process.stderr.write(String(error.message || error));
  process.exit(1);
});
