import { expect,it } from "vitest";
import sample from "../../__fixtures__/sample_bundle.json";
import { validateBundleStructure } from "../bundleValidation";
it("accepts canonical constructed metadata while preserving historical bundle compatibility",()=>{
 const b=structuredClone(sample) as unknown as Record<string,unknown>;
 expect(validateBundleStructure(b)).toBeNull();
 (b.metadata as Record<string,unknown>).constructed={from:"b".repeat(64),edits:["Explicitly constructed demo edit"]};
 expect(validateBundleStructure(b)).toBeNull();
 (b.metadata as Record<string,unknown>).constructed={from:"unverified",edits:[]};
 expect(validateBundleStructure(b)).toContain("metadata.constructed");
});
