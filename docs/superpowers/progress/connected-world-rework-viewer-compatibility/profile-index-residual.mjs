#!/usr/bin/env node
/** Sample the already-compiled, identity-pinned production index in isolation. */
import { Session } from "node:inspector";
import { readFileSync,writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { pathToFileURL } from "node:url";
import { performance } from "node:perf_hooks";
const [runtime,bundleFile,out]=process.argv.slice(2);if(!runtime||!bundleFile||!out)throw new Error("RUNTIME BUNDLE OUTPUT_JSON");
const sha=x=>createHash("sha256").update(x).digest("hex"),raw=readFileSync(bundleFile),module=await import(pathToFileURL(runtime).href),bundle=module.decodeBundlePayload(JSON.parse(raw.toString("utf8")));
const session=new Session();session.connect();const post=(method,params={})=>new Promise((resolve,reject)=>session.post(method,params,(e,r)=>e?reject(e):resolve(r)));
await post("Profiler.enable");await post("Profiler.setSamplingInterval",{interval:1000});await post("Profiler.start");const t=performance.now(),index=module.indexEntityHistory(bundle),elapsed=performance.now()-t,{profile}=await post("Profiler.stop");session.disconnect();
writeFileSync(out+".cpuprofile",JSON.stringify(profile));const nodes=new Map(profile.nodes.map(n=>[n.id,n])),cost=new Map();for(let i=0;i<profile.samples.length;i++){const frame=nodes.get(profile.samples[i]).callFrame,key=JSON.stringify(frame);cost.set(key,(cost.get(key)??0)+(profile.timeDeltas?.[i]??1000));}
const self=[...cost].map(([frame,us])=>({frame:JSON.parse(frame),sampled_ms:us/1000})).sort((a,b)=>b.sampled_ms-a.sampled_ms);const digest=createHash("sha256");for(const s of index.snapshots)digest.update(JSON.stringify({turn:s.snapshot.turn,epoch:s.epoch,frames:s.frames}));digest.update(JSON.stringify(index.entities));
const report={generated:new Date().toISOString(),runtime,runtime_sha256:sha(readFileSync(runtime)),bundle:bundleFile,bundle_sha256:sha(raw),elapsed_ms:elapsed,index_sha256:digest.digest("hex"),self,profile_samples:profile.samples.length,note:"One diagnostic sampled CPU profile; excludes decoding and UI, no performance acceptance claim. Original pure formatter runtime and unchanged raw bundle."};writeFileSync(out,JSON.stringify(report,null,2)+"\n");console.log(JSON.stringify({elapsed_ms:elapsed,self:self.slice(0,10)}));
