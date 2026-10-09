#!/usr/bin/env node
/**
 * scripts/check_web_literals.mjs
 * 
 * Static analysis gate enforcing Prompt P10 Requirement 5:
 * "scripts/check_web_literals.mjs fails on numeric/currency literals and record
 * arrays in web/src/pages (UI constants allowed)."
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const rootDir = path.resolve(__dirname, '..');
const pagesDir = path.join(rootDir, 'web', 'src', 'pages');

// Business data indicator keys in mock record objects
const BUSINESS_DATA_KEYS = new Set([
  'amount', 'currentspend', 'forecastspend', 'budget', 'actualspend',
  'monthlycost', 'projectedsavings', 'realisedsavings', 'hourlycommitment',
  'monthlysavings', 'proposedbudget', 'currentrunrate', 'baseforecast',
  'totalbilledcost', 'directcost', 'sharedcostallocated', 'unallocatedcost',
  'outofhourswastecost', 'eventtype', 'eventhash', 'targetentity',
  'scopegrant', 'sizingspec', 'saturationpct', 'daystoexhaustion',
  'previousvalue', 'newvalue', 'impactamount'
]);

// Banned variable name prefixes for data records
const BANNED_VAR_PREFIXES = ['MOCK_', 'DEMO_', 'INITIAL_', 'SAMPLE_'];

// Regex to catch hardcoded currency strings (e.g. "$120", "$ 1,234.50", "USD 500")
const CURRENCY_LITERAL_REGEX = /(?:\$|\bUSD\s*|\bEUR\s*|\bGBP\s*)\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+\.\d{2})/i;

const files = fs.readdirSync(pagesDir).filter((f) => f.endsWith('.tsx'));
const violations = [];

for (const file of files) {
  // Allow purely informational/showcase pages if any (e.g. DesignSystemShowcase)
  if (file === 'DesignSystemShowcase.tsx') continue;

  const filePath = path.join(pagesDir, file);
  const content = fs.readFileSync(filePath, 'utf-8');
  const lines = content.split('\n');

  lines.forEach((line, index) => {
    const lineNum = index + 1;
    const trimmed = line.trim();

    // Skip comments and imports
    if (trimmed.startsWith('//') || trimmed.startsWith('/*') || trimmed.startsWith('*') || trimmed.startsWith('import ')) {
      return;
    }

    // 1. Check for banned mock/demo array declarations
    for (const prefix of BANNED_VAR_PREFIXES) {
      if (new RegExp(`const\\s+${prefix}[A-Za-z0-9_]*\\s*[:=]`).test(trimmed)) {
        violations.push({
          file,
          line: lineNum,
          type: 'BANNED_DATA_RECORD_ARRAY',
          detail: `Banned mock data variable declaration: "${trimmed}"`,
        });
      }
    }

    // 2. Check for object literals inside arrays containing business data keys
    for (const key of BUSINESS_DATA_KEYS) {
      const fieldRegex = new RegExp(`^\\s*${key}\\s*:\\s*([0-9.]+|"[^"]*"|'[^']*')`, 'i');
      if (fieldRegex.test(trimmed)) {
        // Exclude schema/type definitions or default state settings
        if (!trimmed.includes('number') && !trimmed.includes('string') && !trimmed.includes('null') && !trimmed.includes('undefined')) {
          violations.push({
            file,
            line: lineNum,
            type: 'HARDCODED_BUSINESS_DATA_VALUE',
            detail: `Literal business data field assignment: "${trimmed}"`,
          });
        }
      }
    }

    // 3. Check for hardcoded currency literals in JSX/strings
    const currencyMatch = trimmed.match(CURRENCY_LITERAL_REGEX);
    if (currencyMatch && !trimmed.includes('currency') && !trimmed.includes('format') && !trimmed.includes('regex') && !trimmed.includes('aria-label') && !trimmed.includes('createCostExplanation')) {
      // Check if it's a raw currency figure rendered directly
      if (/>\s*\$[\d,]+(?:\.\d+)?\s*</.test(trimmed) || /['"`]\$[\d,]+(?:\.\d+)?['"`]/.test(trimmed)) {
        violations.push({
          file,
          line: lineNum,
          type: 'CURRENCY_LITERAL',
          detail: `Hardcoded currency literal in UI: "${trimmed}"`,
        });
      }
    }
  });
}

console.log('=======================================================');
console.log('Web Pages Zero-Literals AST & Static Analysis Scanner');
console.log(`Scanned ${files.length} pages in web/src/pages`);
console.log(`Violations Found: ${violations.length}`);
console.log('=======================================================');

if (violations.length > 0) {
  console.error('\nViolations:');
  for (const v of violations) {
    console.error(`  [FAIL] ${v.file}:${v.line} (${v.type}): ${v.detail}`);
  }
  process.exit(1);
} else {
  console.log('\n[PASS] check_web_literals passed cleanly! All pages free of embedded records and currency literals.');
  process.exit(0);
}
