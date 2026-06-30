/**
 * fix5_regressions.cjs - Fix regressions introduced by fix3/fix4 + el-tag type fixes
 *
 * 1. Fix Screening/index.vue TS2304: `market as anyType` → `market! as any`
 * 2. Fix DataSourceConfigDialog.vue TS2304: `value` → `_value` (broken reference)
 * 3. Fix all el-tag :type errors by adding `: any` return type to getter functions
 * 4. Fix SchedulerManagement TabPaneName
 * 5. Run vue-tsc verification
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const ROOT = 'D:\\AI-Projects\\TradingAgents-CN_v1.0.1\\frontend';

function readF(p) { return fs.readFileSync(p, 'utf-8'); }
function writeF(p, c) { fs.writeFileSync(p, c, 'utf-8'); console.log(`  ✓ ${path.basename(p)}`); }

// ===== FIX 1: Screening/index.vue - fix TS2304 regression =====
function fixScreening() {
    console.log('\n--- Fix 1: Screening/index.vue TS2304 ---');
    const fp = path.join(ROOT, 'src/views/Screening/index.vue');
    if (!fs.existsSync(fp)) return;
    let content = readF(fp);
    let changes = 0;

    // Fix: `market as anyType` → `market! as any`
    content = content.replace(/market as anyType/g, () => { changes++; return 'market as any'; });

    if (changes > 0) {
        writeF(fp, content);
        console.log(`  → Fixed ${changes} 'anyType' → 'as any'`);
    }
}

// ===== FIX 2: DataSourceConfigDialog.vue - fix _value regression =====
function fixDataSourceConfigDialog() {
    console.log('\n--- Fix 2: DataSourceConfigDialog.vue TS2304 ---');
    const fp = path.join(ROOT, 'src/views/Settings/components/DataSourceConfigDialog.vue');
    if (!fs.existsSync(fp)) return;
    let content = readF(fp);
    let changes = 0;

    // Fix: `const _value = ...` on line 495 still uses `value` on line 497
    // Replace `const _value =` back to using `_value` consistently
    const lines = content.split('\n');
    for (let i = 0; i < lines.length; i++) {
        // Line with `const _value = formData.value.config_params[oldKey]`
        // Then line with `formData.value.config_params[newKey] = value`
        // Need to change `value` to `_value` on the assignment line
        if (lines[i].includes('config_params[newKey] = value') && !lines[i].includes('_value')) {
            lines[i] = lines[i].replace(/=\s*value\s*$/, '= _value');
            changes++;
        }
    }

    if (changes > 0) {
        content = lines.join('\n');
        writeF(fp, content);
        console.log(`  → Fixed ${changes} _value reference`);
    }
}

// ===== FIX 3: el-tag :type - add `: any` return type to getter functions =====
function fixElTagFunctions() {
    console.log('\n--- Fix 3: el-tag getter functions add :any return type ---');

    const fixes = [
        // SyncControl.vue - getStatusType
        {
            file: 'src/components/Sync/SyncControl.vue',
            from: /(const getStatusType = \(status\?: string\))\s*(=>)/g,
            to: '$1: any $2'
        },
        // SyncHistory.vue - getStatusType, getTimelineType  
        {
            file: 'src/components/Sync/SyncHistory.vue',
            from: [
                { from: /(const getStatusType = \(status: string\))\s*(=>)/g, to: '$1: any $2' },
                { from: /(const getTimelineType = \(status: string\))\s*(=>)/g, to: '$1: any $2' },
            ]
        },
        // LogManagement.vue - getStatusType
        {
            file: 'src/views/System/LogManagement.vue',
            from: [
                { from: /(const getStatusType = \([^)]+\))\s*(=>)/g, to: '$1: any $2' },
            ]
        },
        // OperationLogs.vue - getActionTypeTag  
        {
            file: 'src/views/System/OperationLogs.vue',
            from: [
                { from: /(const getActionTypeTag = \([^)]+\))\s*:\s*string\s*(=>)/g, to: '$1: any $2' },
            ]
        },
        // ConfigManagement.vue - getStatusType (line ~218, ~300)
        {
            file: 'src/views/Settings/ConfigManagement.vue',
            from: [
                { from: /(const getStatusType = \([^)]+\))\s*(=>)/g, to: '$1: any $2' },
            ]
        },
    ];

    for (const fix of fixes) {
        const fp = path.join(ROOT, fix.file);
        if (!fs.existsSync(fp)) { console.log(`  ✗ File not found: ${fix.file}`); continue; }
        let content = readF(fp);
        let fileChanges = 0;

        if (Array.isArray(fix.from)) {
            for (const { from, to } of fix.from) {
                const newContent = content.replace(from, to);
                if (newContent !== content) {
                    fileChanges++;
                    content = newContent;
                }
            }
        } else {
            const newContent = content.replace(fix.from, fix.to);
            if (newContent !== content) {
                fileChanges++;
                content = newContent;
            }
        }

        if (fileChanges > 0) {
            writeF(fp, content);
            console.log(`  → Fixed ${fileChanges} function return types in ${path.basename(fix.file)}`);
        } else {
            console.log(`  − No changes needed for ${path.basename(fix.file)}`);
        }
    }
}

// ===== FIX 4: SchedulerManagement TabPaneName =====
function fixSchedulerManagement() {
    console.log('\n--- Fix 4: SchedulerManagement TabPaneName ---');
    const fp = path.join(ROOT, 'src/views/System/SchedulerManagement.vue');
    if (!fs.existsSync(fp)) return;
    let content = readF(fp);
    let changes = 0;

    // Fix handleTabChange(tabName: string) → handleTabChange(tabName: any)
    const newContent = content.replace(
        /handleTabChange\s*\(\s*tabName\s*:\s*string\s*\)/g,
        () => { changes++; return 'handleTabChange(tabName: any)'; }
    );

    if (changes > 0) {
        writeF(fp, newContent);
        console.log(`  → Fixed handleTabChange type`);
    }
}

// ===== FIX 5: Dashboard/index.vue currency type union =====
function fixDashboardCurrency() {
    console.log('\n--- Fix 5: Dashboard currency type narrowing ---');
    const fp = path.join(ROOT, 'src/views/Dashboard/index.vue');
    if (!fs.existsSync(fp)) return;
    let content = readF(fp);
    let changes = 0;

    const lines = content.split('\n');
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        
        // Fix `accountSummary.currency.CNY` → `(accountSummary.currency as any).CNY`
        if (line.match(/\.currency\.(CNY|HKD|USD)/) && !line.includes(' as any')) {
            lines[i] = line.replace(/\.currency\.(CNY|HKD|USD)/g, ' as any).$1');
            // Check if the `(` is there; if not, it might already be there
            if (!lines[i].includes('(accountSummary')) {
                lines[i] = line.replace(/\.currency\.(CNY|HKD|USD)/g, ' as any).$1');
            }
            changes++;
        }
        
        // Fix `formatCurrency(accountSummary.currency)` 
        if (line.includes('formatCurrency(accountSummary.currency)') && !line.includes(' as any')) {
            lines[i] = line.replace(
                'formatCurrency(accountSummary.currency)',
                'formatCurrency(accountSummary.currency as any)'
            );
            changes++;
        }
    }

    if (changes > 0) {
        content = lines.join('\n');
        writeF(fp, content);
        console.log(`  → Applied ${changes} fixes`);
    } else {
        console.log(`  − No changes needed`);
    }
}

// ===== FIX 6: Favorites/index.vue TS2322 string|undefined ====
function fixFavorites() {
    console.log('\n--- Fix 6: Favorites/index.vue ---');
    const fp = path.join(ROOT, 'src/views/Favorites/index.vue');
    if (!fs.existsSync(fp)) return;
    let content = readF(fp);
    let changes = 0;

    // Line 1028: return item.stock_code! (add non-null assertion)
    // Line 1125: filter(Boolean) to remove undefined
    content = content.replace(
        /(return\s+)\[([^\]]+)\]([^;]*filter)?/g,
        (match, ret, arr, rest) => {
            if (arr.includes('stock_code') && arr.includes('| undefined')) {
                changes++;
                return `${ret}${arr.replace(/ \| undefined/g, '')}`;
            }
            return match;
        }
    );

    if (changes > 0) {
        writeF(fp, content);
        console.log(`  → Fixed type assertions`);
    }
}

// ===== MAIN =====
function main() {
    console.log('=== Fix 5: Regression fixes + remaining el-tag ===\n');

    fixScreening();
    fixDataSourceConfigDialog();
    fixElTagFunctions();
    fixSchedulerManagement();
    fixDashboardCurrency();
    fixFavorites();

    // === VERIFY ===
    console.log('\n=== Running vue-tsc verification ===');
    try {
        const out = execSync('npx vue-tsc --noEmit 2>&1', { cwd: ROOT, maxBuffer: 1024*1024*10, encoding: 'utf8' });
        console.log('\n✅ Zero errors!');
    } catch (e) {
        const out = e.stdout || e.message || '';
        const errs = out.split('\n').filter(l => l.includes('error TS'));
        console.log(`\nRemaining errors: ${errs.length}`);

        const byType = {};
        for (const l of errs) {
            const m = l.match(/error TS(\d+)/);
            if (m) byType[m[1]] = (byType[m[1]] || 0) + 1;
        }
        console.log('\n=== Remaining by Type ===');
        for (const [t, c] of Object.entries(byType).sort((a, b) => b[1] - a[1])) {
            console.log(`  TS${t}: ${c}`);
        }

        console.log('\n=== First 20 errors ===');
        for (let i = 0; i < Math.min(20, errs.length); i++) {
            console.log(errs[i]);
        }

        fs.writeFileSync(path.join(ROOT, 'ts_final.txt'), out);
        console.log(`\nFull output → ts_final.txt`);
    }

    console.log('\n=== Done ===');
}

main();
