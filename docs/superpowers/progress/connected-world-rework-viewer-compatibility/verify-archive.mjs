#!/usr/bin/env node
/** Verify the complete production decoder/index/query products; no simulation. */
import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { performance } from "node:perf_hooks";
const options = { root:null, plain:null, archive:null, out:null };
for(let i=2;i<process.argv.length;i+=2){const key=process.argv[i].replace(/^--/,"");if(!(key in options)||!process.argv[i+1])throw new Error("Expected --root CHECKOUT --plain JSON --archive GZIP --out FILE");options[key]=path.resolve(process.argv[i+1]);}
if(Object.values(options).some(v=>!v))throw new Error("Missing option");
const sha=bytes=>createHash("sha256").update(bytes).digest("hex"),root=options.root;
const require=createRequire(path.join(root,"viewer/package.json")),{build}=require("esbuild");
const compiled=await build({stdin:{contents:`export {decodeBundleBytes,expandBundleBytes} from ${JSON.stringify(path.join(root,"viewer/src/lib/bundleFile.ts"))};export {indexEntityHistory,entityHistory} from ${JSON.stringify(path.join(root,"viewer/src/lib/entityHistory.ts"))};`,resolveDir:root,loader:"ts"},bundle:true,platform:"node",format:"esm",write:false,metafile:true});
mkdirSync(path.dirname(options.out),{recursive:true});const runtime=options.out+".runtime.mjs";writeFileSync(runtime,compiled.outputFiles[0].contents);
const source=Object.fromEntries(Object.keys(compiled.metafile.inputs).filter(file=>file!=="<stdin>").sort().map(file=>[file,sha(readFileSync(path.resolve(root,file)))]));
const {decodeBundleBytes,expandBundleBytes,indexEntityHistory,entityHistory}=await import(pathToFileURL(runtime).href);
const measure=async(name,filename)=>{const original=readFileSync(filename),raw=Uint8Array.from(original).buffer,t=performance.now();const result=await decodeBundleBytes(path.basename(filename),raw);const decodeMs=performance.now()-t;if(result.error||!result.bundle)throw new Error(result.error??"No decoded bundle");const bundle=result.bundle;
 const bundleSha=sha(JSON.stringify(bundle)),started=performance.now(),index=indexEntityHistory(bundle),indexMs=performance.now()-started,digest=createHash("sha256"),queries=createHash("sha256");
 for(const snapshot of index.snapshots)digest.update(JSON.stringify({turn:snapshot.snapshot.turn,epoch:snapshot.epoch,frames:snapshot.frames}));digest.update(JSON.stringify(index.entities));
 const through=Math.max(...bundle.history.map(s=>s.turn));for(const e of [{kind:"person",id:13},{kind:"person",id:999999},{kind:"household",id:13},{kind:"region",id:3},{kind:"project",id:0},{kind:"timber_order",id:0},{kind:"army",id:"army-2"}])for(const turn of [1,27,66,through])queries.update(JSON.stringify(entityHistory(index,e,turn)));
 return {name,file:filename,input_sha256:sha(original),input_bytes:original.length,identity:result.identity,expanded_sha256:sha(new Uint8Array(await expandBundleBytes(raw))),decoded_sha256:bundleSha,index_sha256:digest.digest("hex"),queries_sha256:queries.digest("hex"),snapshots:bundle.history.length,events:bundle.events_timeline.length,named_events:bundle.named_events.length,observations:index.snapshots.reduce((n,s)=>n+Object.values(s.frames).reduce((a,f)=>a+f.rows.length,0),0),entities:index.entities.length,timings_ms:{decode:decodeMs,index:indexMs}};
};
const plain=await measure("plain",options.plain),archive=await measure("archive",options.archive);
for(const key of ["expanded_sha256","decoded_sha256","index_sha256","queries_sha256","snapshots","events","named_events","observations","entities"])if(plain[key]!==archive[key])throw new Error(`Archive changed ${key}`);
if(plain.input_sha256!==archive.expanded_sha256||archive.identity.sha256!==archive.input_sha256||archive.identity.byteLength!==archive.input_bytes)throw new Error("Wrong artifact or expanded-byte identity");
const report={generated:new Date().toISOString(),source,compiled_sha256:sha(compiled.outputFiles[0].contents),plain,archive,equal:true,note:"Complete decoded/index serialization including every row's order/text/pointer/state plus 28 dated queries. Timings are one diagnostic, not a performance claim. Same unchanged simulation bytes; archive identities intentionally differ."};
writeFileSync(options.out,JSON.stringify(report,null,2)+"\n");console.log(JSON.stringify({equal:true,observations:plain.observations,index_sha256:plain.index_sha256}));
