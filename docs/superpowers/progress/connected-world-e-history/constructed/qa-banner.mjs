/** Evidence-only instrumentation of the frozen browser harness; no source is changed. */
import {readFileSync,writeFileSync,mkdirSync} from "node:fs";
import {createHash} from "node:crypto";
import {spawnSync} from "node:child_process";
import path from "node:path";
const args=process.argv.slice(2),index=args.indexOf("--source-script");
if(index<0)throw new Error("Required: --source-script FROZEN_QA_SCRIPT plus its normal arguments");
const source=path.resolve(args[index+1]);args.splice(index,2);
const out=path.resolve(args[args.indexOf("--out")+1]);mkdirSync(out,{recursive:true});
const original=readFileSync(source,"utf8");
const anchor='      const panel=options.journey === "public_health" ? "Epidemics" : "Livelihoods";';
if(original.split(anchor).length!==2)throw new Error("Frozen harness anchor changed; inspect before using");
const extra=`      const notice=page.getByRole("note",{name:"Constructed demonstration",exact:true});
      await notice.getByText("Recorded edits and source",{exact:true}).click();
      const marker=expected.constructed,noticeText=await notice.innerText();
      check(result,\`\${name}: constructed notice explicitly disclaims natural activation\`,noticeText.includes("not evidence of natural activation or qualification"));
      check(result,\`\${name}: expanded notice shows exact source hash and all recorded edits\`,noticeText.includes(marker.from)&&JSON.stringify(await notice.locator("li").allTextContents())===JSON.stringify(marker.edits));
      await notice.screenshot({path:path.join(options.out,\`\${name}-constructed-notice.png\`)});
`;
const instrumented=original.replace(anchor,extra+anchor),script=path.join(out,"instrumented-journey.mjs");
writeFileSync(script,instrumented);
const sha=s=>createHash("sha256").update(s).digest("hex");
writeFileSync(path.join(out,"harness.json"),JSON.stringify({source,source_sha256:sha(original),instrumented_sha256:sha(instrumented),
  modification:"Evidence-only extra notice expansion, source/edit assertions and notice screenshots; original production journey otherwise unchanged."},null,2)+"\n");
const run=spawnSync(process.execPath,[script,...args],{stdio:"inherit"});
if(sha(readFileSync(source))!==sha(original))throw new Error("Frozen harness was unexpectedly changed");
process.exitCode=run.status??1;
