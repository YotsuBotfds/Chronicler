import { expect, it } from "vitest";
import type { TurnSnapshot } from "../../types";
import { harvestCoverAt } from "../harvestCover";
const row = {region:0, slots:[1],standing:2,capacity:10,ratio:.2,cover_before:.9,supported_cover:.18,proposed_loss:.005,loss:.005,cover_after:.895};
const snapshot = (edits = {}) => ({turn:4,livelihoods:{harvest_cover:{schema_version:1,stage:"B4",source_turn:3,mode:"loss",rows:[structuredClone(row)],...edits}}}) as unknown as TurnSnapshot;
it("keeps absent, unsettled, measured zero and measured loss distinct",()=>{
 expect(harvestCoverAt({turn:4} as TurnSnapshot,2).status).toBe("absent");
 expect(harvestCoverAt(snapshot({rows:null}),2).status).toBe("unobserved");
 expect(harvestCoverAt(snapshot({rows:[]}),2).status).toBe("recorded");
 expect(harvestCoverAt(snapshot(),2).status).toBe("recorded");
 expect(harvestCoverAt(snapshot({mode:"record_only",rows:[{...row,loss:0,cover_after:.9}]}),2).status).toBe("recorded");
});
it.each([
 {source_turn:4}, {rows:[{...row,loss:.01}]}, {rows:[{...row,standing:1}]}, {rows:[{...row,slots:[1,1]}]},
 {rows:[{...row,slots:[]}]}, {rows:[{...row,cover_before:Infinity}]}, {mode:"record_only"}, {rows:[row,row]},
 {rows:[{...row,supported_cover:.95}]}, {stage:"B9"},
])("refuses malformed or misdated observations %j",edits=>expect(harvestCoverAt(snapshot(edits),2).status).toBe("malformed"));
