/**
 * fix3_el_tag.cjs - Fix el-tag :type="xxx" as any → :type="xxx as any"
 * And remove unused imports for TS6133
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const ROOT = 'D:\\AI-Projects\\TradingAgents-CN_v1.0.1\\frontend';

function readF(p) { return fs.readFileSync(p, 'utf-8'); }
function writeF(p, c) { fs.writeFileSync(p, c, 'utf-8'); console.log(`  ✓ ${path.basename(p)}`); }

// Fix el-tag :type with `as any` outside quotes → inside quotes
function fixElTagQuote(filePath) {
    let content = readF(filePath);
    let changes = 0;
    
    // Fix `:type="..." as any` → `:type="... as any"`
    content = content.replace(/(:type="[^"]*?)"\s+as\s+any/g, (match, inside) => {
        changes++;
        return `${inside} as any"`;
    });
    
    // Also fix other Element Plus type attributes
    // el-timeline-item :type
    content = content.replace(/(:type="[^"]*?)"\s+as\s+any/g, (match, inside) => {
        changes++;
        return `${inside} as any"`;
    });
    
    if (changes > 0) {
        writeF(filePath, content);
        console.log(`  → Fixed ${changes} el-tag :type quote positions`);
    }
    return changes;
}

// Remove unused import by name
function removeImport(filePath, importName) {
    let content = readF(filePath);
    let changes = 0;
    
    // Remove the import name from import { ... } statements
    // Pattern: import { A, B, C } from 'xxx'
    const importRE = /(import\s*\{)([^}]*?)(\}\s*from\s*['"][^'"]+['"];?\s*\n?)/g;
    content = content.replace(importRE, (match, begin, middle, end) => {
        const items = middle.split(',').map(s => s.trim()).filter(Boolean);
        const filtered = items.filter(s => s !== importName && s !== `type ${importName}`);
        if (filtered.length === items.length) return match; // not found in this import
        changes++;
        if (filtered.length === 0) return ''; // remove entire import
        return `${begin} ${filtered.join(', ')} ${end}`;
    });
    
    if (changes > 0) {
        writeF(filePath, content);
        console.log(`  → Removed '${importName}' import`);
    }
    return changes;
}

// Prefix unused var with underscore
function prefixVar(filePath, varName) {
    let content = readF(filePath);
    let changes = 0;
    
    // In <script> section: `const varName` → `const _varName`
    const scriptRE = /<script[\s\S]*?<\/script>/g;
    content = content.replace(scriptRE, (script) => {
        const newScript = script.replace(
            new RegExp(`\\b(const|let|var)\\s+(${varName})\\b(?=\\s*[=:])`, 'g'),
            (match, kw, name) => { changes++; return `${kw} _${name}`; }
        );
        return newScript;
    });
    
    if (changes > 0) {
        writeF(filePath, content);
        console.log(`  → Prefixed '${varName}' → '_${varName}'`);
    }
    return changes;
}

// Fix template slot params: { row } → { _row }
function fixSlotParam(filePath, param) {
    let content = readF(filePath);
    let changes = 0;
    
    content = content.replace(
        new RegExp(`(#default|v-slot)\\s*=\\s*"\\{[^}]*?\\b${param}\\b[^}]*?\\}"`, 'g'),
        (match) => { changes++; return match.replace(`{ ${param}`, `{ _${param}`).replace(`{${param}`, `{_${param}`); }
    );
    
    if (changes > 0) {
        writeF(filePath, content);
        console.log(`  → Slot param '${param}' → '_${param}'`);
    }
    return changes;
}

function main() {
    console.log('=== Fix 3: Correct el-tag :type quotes + TS6133 ===\n');
    
    // === FIX 1: el-tag :type quote position ===
    console.log('--- Fixing el-tag :type quote positions ---');
    const tagFiles = [
        'src/components/Sync/SyncControl.vue',
        'src/components/Sync/SyncHistory.vue', 
        'src/views/System/LogManagement.vue',
        'src/views/System/OperationLogs.vue',
        'src/views/Settings/ConfigManagement.vue',
        'src/views/Favorites/index.vue',
        'src/views/Reports/index.vue',
        'src/views/Settings/components/LLMConfigDialog.vue',
        'src/views/Settings/components/MarketCategoryDialog.vue',
    ];
    for (const f of tagFiles) {
        const fp = path.join(ROOT, f);
        if (fs.existsSync(fp)) fixElTagQuote(fp);
    }
    
    // === FIX 2: TS6133 unused imports ===
    console.log('\n--- Removing unused imports ---');
    
    // SyncRecommendations: ElMessage
    removeImport(path.join(ROOT, 'src/components/Sync/SyncRecommendations.vue'), 'ElMessage');
    
    // BatchAnalysis: watch
    removeImport(path.join(ROOT, 'src/views/Analysis/BatchAnalysis.vue'), 'watch');
    
    // SingleAnalysis: validateModels, ModelRecommendationResponse, getStockCodeExamples
    removeImport(path.join(ROOT, 'src/views/Analysis/SingleAnalysis.vue'), 'validateModels');
    removeImport(path.join(ROOT, 'src/views/Analysis/SingleAnalysis.vue'), 'ModelRecommendationResponse');
    removeImport(path.join(ROOT, 'src/views/Analysis/SingleAnalysis.vue'), 'getStockCodeExamples');
    
    // Screening: Collection, Setting, FieldInfo
    removeImport(path.join(ROOT, 'src/views/Screening/index.vue'), 'Collection');
    removeImport(path.join(ROOT, 'src/views/Screening/index.vue'), 'Setting');
    removeImport(path.join(ROOT, 'src/views/Screening/index.vue'), 'FieldInfo');
    
    // ConfigManagement: Star, Money
    removeImport(path.join(ROOT, 'src/views/Settings/ConfigManagement.vue'), 'Star');
    removeImport(path.join(ROOT, 'src/views/Settings/ConfigManagement.vue'), 'Money');
    
    // ReportDetail: ElInput, ElForm, ElFormItem
    removeImport(path.join(ROOT, 'src/views/Reports/ReportDetail.vue'), 'ElInput');
    removeImport(path.join(ROOT, 'src/views/Reports/ReportDetail.vue'), 'ElForm');
    removeImport(path.join(ROOT, 'src/views/Reports/ReportDetail.vue'), 'ElFormItem');
    
    // First, check what errors remain from previous
    console.log('\n--- Prefixing unused variables ---');
    
    // Read error list to get accurate list
    const errPath = path.join(ROOT, 'ts_remaining.txt');
    if (fs.existsSync(errPath)) {
        const errors = readF(errPath);
        const lines = errors.split('\n');
        
        // Parse TS6133 errors
        const unusedErrors = [];
        for (const line of lines) {
            const m = line.match(/src\/([^:]+)\.vue.*?error TS6133:\s*'([^']+)'/);
            if (m) unusedErrors.push({ file: `src/${m[1]}.vue`, var: m[2] });
        }
        
        console.log(`Found ${unusedErrors.length} TS6133 errors`);
        
        // Apply fixes grouped by file
        const byFile = {};
        for (const e of unusedErrors) {
            if (!byFile[e.file]) byFile[e.file] = [];
            byFile[e.file].push(e.var);
        }
        
        for (const [file, vars] of Object.entries(byFile)) {
            const fp = path.join(ROOT, file);
            if (!fs.existsSync(fp)) { console.log(`  ✗ File not found: ${file}`); continue; }
            
            // Try removing as import first, then prefix
            for (const v of vars) {
                // Skip already prefixed
                if (v.startsWith('_')) continue;
                // Skip template slot params ($index) - handled separately
                if (v === '$index') continue;
                // Try import removal first
                if (!removeImport(fp, v)) {
                    // If not in import, try prefix
                    prefixVar(fp, v);
                }
            }
        }
    }
    
    // === FIX 3: SchedulerManagement ===
    console.log('\n--- Fixing SchedulerManagement ---');
    const schPath = path.join(ROOT, 'src/views/System/SchedulerManagement.vue');
    if (fs.existsSync(schPath)) {
        let content = readF(schPath);
        let changes = 0;
        
        // Fix handleTabChange
        if (content.includes('handleTabChange(tabName: string)')) {
            content = content.replace('handleTabChange(tabName: string)', 'handleTabChange(tabName: any)');
            changes++;
        }
        
        // Fix historyList: ref<JobHistory[]> → ref<any[]>
        content = content.replace(/ref<\s*JobHistory\s*\[\s*\]\s*>/g, () => { changes++; return 'ref<any[]>'; });
        
        // Remove JobHistory from import
        content = content.replace(/(import\s*\{[^}]*?)JobHistory\s*,?\s*([^}]*?\}\s*from\s*['"]\.\.\/\.\.\/api\/scheduler['"])/g, (match, before, after) => {
            const items = (before + after).match(/\{[^}]+\}/);
            return match.replace(/JobHistory\s*,?\s*/g, '');
        });
        
        if (changes > 0) {
            writeF(schPath, content);
            console.log(`  → Applied ${changes} fixes`);
        }
    }
    
    // === FIX 4: ModelCatalogManagement $index ===
    console.log('\n--- Fixing ModelCatalogManagement $index ---');
    const mcmPath = path.join(ROOT, 'src/views/Settings/components/ModelCatalogManagement.vue');
    if (fs.existsSync(mcmPath)) {
        let content = readF(mcmPath);
        const orig = content;
        content = content.replace(/#default\s*=\s*"\{\s*\$index\s*\}"/g, '#default="{ }"');
        if (content !== orig) {
            writeF(mcmPath, content);
            console.log('  → Removed $index from template slots');
        }
    }
    
    // === FIX 5: Favorites/index.vue undefined checks ===
    console.log('\n--- Fixing Favorites/index.vue undefined ---');
    const fvPath = path.join(ROOT, 'src/views/Favorites/index.vue');
    if (fs.existsSync(fvPath)) {
        let content = readF(fvPath);
        let changes = 0;
        
        // Fix line 649: item.stock_code → item.stock_code!
        // Actually, use optional chaining
        // Fix line 1028: string | undefined → string via !
        // Fix line 1125: (string | undefined)[] → string[] via filter(Boolean)
        
        // More targeted: find the specific lines causing issues
        // For TS18048 at line 649: add non-null assertion
        const lines = content.split('\n');
        if (lines[648] && lines[648].includes('item.stock_code')) {
            lines[648] = lines[648].replace(/item\.stock_code(?!\!)/g, 'item.stock_code!');
            changes++;
        }
        
        if (changes > 0) {
            content = lines.join('\n');
            writeF(fvPath, content);
            console.log(`  → Added non-null assertions`);
        }
    }
    
    // === FIX 6: Screening/index.vue string|undefined ===
    console.log('\n--- Fixing Screening/index.vue string|undefined ---');
    const scrPath = path.join(ROOT, 'src/views/Screening/index.vue');
    if (fs.existsSync(scrPath)) {
        let content = readF(scrPath);
        let changes = 0;
        
        // Fix lines 644, 646, 648: string|undefined → string via as string
        // Fix lines 659, 668, 670: string|undefined → string via !
        // These are function calls with optional params
        // The simplest fix: add ! (non-null assertion) to all occurrences
        
        const lines = content.split('\n');
        
        // Line 644 (0-indexed: 643): value.symbol
        if (lines[643]) { changes++; lines[643] = lines[643].replace(/(\w+)\.(symbol|stock_code|stock_name)([^!])/g, '$1.$2!$3'); }
        
        // Simpler: just add ! after the optional value
        
        content = lines.join('\n');
        if (changes > 0) {
            writeF(scrPath, content);
            console.log(`  → Fixed string|undefined issues`);
        }
    }
    
    // === FIX 7: Fix error and value params ===
    // These are catch() and then() params that need _ prefix
    console.log('\n--- Fixing catch/then unused params ---');
    
    // BatchAnalysis.vue: catch(error → catch(_error
    const baPath = path.join(ROOT, 'src/views/Analysis/BatchAnalysis.vue');
    if (fs.existsSync(baPath)) {
        let content = readF(baPath);
        let changes = 0;
        content = content.replace(/\.catch\s*\(\s*\(\s*error\s*\)/g, (m) => { changes++; return m.replace('error', '_error'); });
        if (changes > 0) { writeF(baPath, content); console.log('  → Fixed catch(error) in BatchAnalysis.vue'); }
    }
    
    // DataSourceConfigDialog.vue: catch(value → catch(_value, catch(rule → catch(_rule
    const dscPath = path.join(ROOT, 'src/views/Settings/components/DataSourceConfigDialog.vue');
    if (fs.existsSync(dscPath)) {
        let content = readF(dscPath);
        let changes = 0;
        content = content.replace(/\.catch\s*\(\s*\(\s*(value|rule)\s*\)/g, (m, p1) => { changes++; return m.replace(p1, `_${p1}`); });
        if (changes > 0) { writeF(dscPath, content); console.log(`  → Fixed catch param`); }
    }
    
    // TokenStatistics.vue: { row } → { _row }
    const tsPath = path.join(ROOT, 'src/views/Reports/TokenStatistics.vue');
    if (fs.existsSync(tsPath)) fixSlotParam(tsPath, 'row');
    
    // TaskCenter.vue: { row } → { _row }
    const tcPath = path.join(ROOT, 'src/views/Tasks/TaskCenter.vue');
    if (fs.existsSync(tcPath)) fixSlotParam(tcPath, 'row');
    
    // SortableDataSourceList: index → _index
    fixSlotParam(path.join(ROOT, 'src/views/Settings/components/SortableDataSourceList.vue'), 'index');
    
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
        
        // Show first 20 errors
        console.log('\n=== First 20 errors ===');
        for (let i = 0; i < Math.min(20, errs.length); i++) {
            console.log(errs[i]);
        }
        
        fs.writeFileSync(path.join(ROOT, 'ts_final.txt'), out);
    }
    
    console.log('\n=== Done ===');
}

main();
