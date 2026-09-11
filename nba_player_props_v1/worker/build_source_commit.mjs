import { execFileSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const dir=dirname(fileURLToPath(import.meta.url));
const commit=execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim();
if(!/^[0-9a-f]{40}$/.test(commit)) throw new Error('Unable to resolve 40-character deployment source commit');
writeFileSync(join(dir,'source_commit.generated.js'),`export const SOURCE_COMMIT=${JSON.stringify(commit)};\n`);
console.log(`NBA_BUILD_SOURCE_COMMIT=${commit}`);
