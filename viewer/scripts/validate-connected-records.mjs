#!/usr/bin/env node
/** Bind production strict-reader results to the actual source bundle bytes.
 * PYTHONPATH=src node viewer/scripts/validate-connected-records.mjs --bundle FILE --python PY --out REPORT
 * No simulation, model, browser or held seed execution. Requires existing viewer development deps.
 */
import {createRequire} from "node:module";
import {fileURLToPath} from "node:url";
import {readFileSync,writeFileSync,mkdirSync} from "node:fs";
import {spawnSync} from "node:child_process";
import {createHash} from "node:crypto";
import path from "node:path";
const require=createRequire(import.meta.url),here=path.dirname(fileURLToPath(import.meta.url));
const options={bundle:null,out:null,python:"python"};
for(let i=2;i<process.argv.length;i+=2){const key=process.argv[i].replace(/^--/,"");if(!(key in options)||!process.argv[i+1])throw new Error(`Invalid option ${process.argv[i]}`);options[key]=process.argv[i+1];}
if(!options.bundle||!options.out)throw new Error("Required: --bundle FILE --out REPORT [--python PY]");
const decoded=spawnSync(options.python,["-c","import json,sys;from chronicler.bundle_codec import load_bundle;b=load_bundle(sys.argv[1]);print(json.dumps({'regions':len(b['world_state']['regions']),'civs':len(b['world_state']['civilizations']),'history':[{'turn':s['turn'],'livelihoods':s.get('livelihoods')} for s in b['history']]}))",options.bundle],{encoding:"utf8",maxBuffer:256*1024*1024});
if(decoded.status!==0)throw new Error(decoded.stderr||"Independent bundle decoding failed");
const data=JSON.parse(decoded.stdout);
const {buildSync}=require("esbuild");
const built=buildSync({entryPoints:[path.resolve(here,"../src/lib/validateConnectedRecords.ts")],bundle:true,platform:"node",format:"cjs",write:false});
const code=built.outputFiles[0].text,mod={exports:{}};
new Function("module","exports","require",code)(mod,mod.exports,require);
const report={schema_version:1,bundle:path.resolve(options.bundle),bundle_sha256:createHash("sha256").update(readFileSync(options.bundle)).digest("hex"),
 reader_bundle_sha256:createHash("sha256").update(code).digest("hex"),generated:new Date().toISOString(),validation:"actual production strict readers; only observed packages may supply story facts",snapshots:{}};
for(const snapshot of data.history){if(String(snapshot.turn) in report.snapshots)throw new Error(`Duplicate snapshot turn ${snapshot.turn}`);report.snapshots[snapshot.turn]=mod.exports.validateConnectedRecords(snapshot,data.regions,data.civs);}
mkdirSync(path.dirname(path.resolve(options.out)),{recursive:true});writeFileSync(options.out,JSON.stringify(report,null,2)+"\n");
console.log(`${data.history.length} snapshots validated; receipt ${options.out}`);
