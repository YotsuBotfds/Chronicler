/** Explicit demonstration metadata only; no inference from seed, filename or mode. */
export interface ConstructedExample { from: string; edits: string[] }
const object=(v:unknown):v is Record<string,unknown>=>v!==null&&typeof v==="object"&&!Array.isArray(v);
export function isConstructedExample(value:unknown):value is ConstructedExample {
 return object(value)&&typeof value.from==="string"&&/^[a-f0-9]{64}$/i.test(value.from)&&Array.isArray(value.edits)&&value.edits.length>0&&value.edits.length<=256&&value.edits.every((edit)=>typeof edit==="string"&&edit.trim().length>0&&edit.length<=2000);
}
export function constructedExample(bundle:unknown):ConstructedExample|null {
 if(!object(bundle)||!object(bundle.metadata)||!isConstructedExample(bundle.metadata.constructed))return null;
 return bundle.metadata.constructed;
}
