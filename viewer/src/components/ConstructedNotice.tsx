import { constructedExample } from "../lib/constructedExample";
/** Deliberately edited demonstrations stay visibly different from natural runs. */
export function ConstructedNotice({bundle}:{bundle:unknown}) {
 const marker=constructedExample(bundle);
 if(!marker)return null;
 return <aside role="note" aria-label="Constructed demonstration" style={{margin:"12px",padding:"12px 16px",border:"1px solid #be9b54",borderRadius:"8px",background:"#322b1c",color:"#f3e8c8",overflowWrap:"anywhere"}}>
  <strong>Constructed demonstration</strong>
  <p style={{margin:"4px 0"}}>This saved world was deliberately edited. It is an illustration, not evidence of natural activation or qualification.</p>
  <details><summary>Recorded edits and source</summary><p>Source bundle SHA-256: <code>{marker.from}</code></p><ul>{marker.edits.map((edit,i)=><li key={i}>{edit}</li>)}</ul></details>
 </aside>;
}
