import {afterEach,expect,it,vi} from "vitest";
import {cleanup,fireEvent,render,screen,within} from "@testing-library/react";
import natural from "../../../__fixtures__/watershed_records.json";
import type {Region,TurnSnapshot} from "../../../types";
import type {WatershedRecord} from "../../../watershedTypes";
import {WatershedBasin} from "../WatershedBasin";
afterEach(cleanup);
const snapshot = structuredClone(natural.snapshots[0]) as unknown as TurnSnapshot;
const record=(snapshot as unknown as {livelihoods:{watershed:WatershedRecord}}).livelihoods.watershed;
const regions=natural.regions.map((name,i)=>({name,x:i%5,y:Math.floor(i/5),controller:"Final controller"})) as unknown as Region[];
it("uses dated controllers for border links and supports keyboard region inspection",()=>{
 const [source,down]=record.graph.down.map((d,i)=>[i,d]).find(([,d])=>d>=0)!;
 const dated={...snapshot,region_control:{[regions[source].name]:"Past A",[regions[down].name]:"Past B"}};
 const onSelectRegion=vi.fn();
 render(<WatershedBasin regions={regions} snapshot={dated} record={record} onSelectRegion={onSelectRegion}/>);
 fireEvent.click(screen.getByText("Drainage map and cross-border flows"));
 const table=within(screen.getByRole("table",{name:`Basin links at snapshot ${snapshot.turn}`}));
 expect(table.getAllByText("Cross-border").length).toBeGreaterThan(0);
 expect(table.getAllByText("Unknown").length).toBeGreaterThan(0);
 const button=screen.getByRole("button",{name:`Inspect basin region ${regions[source].name}`});
 fireEvent.keyDown(button,{key:"Enter"});
 expect(onSelectRegion).toHaveBeenCalledWith(regions[source].name);
});
it("preserves the table when geographic coordinates were not recorded",()=>{
 render(<WatershedBasin regions={regions.map(({name})=>({name}) as Region)} snapshot={snapshot} record={record} onSelectRegion={vi.fn()}/>);
 expect(screen.getByText(/Map coordinates were not recorded/)).toBeInTheDocument();
 expect(screen.queryByRole("img")).toBeNull();
 expect(screen.getByRole("table")).toBeInTheDocument();
});
