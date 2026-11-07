import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AdaptiveLivelihoods, WarConsequences } from "../PersonalExperience";
import { experienceSnapshot } from "../../../lib/__tests__/personalExperienceFixture";
import type { SystemPanelProps } from "../../../lib/systems";
afterEach(cleanup);
const props=()=>({bundle:{world_state:{regions:[{name:"A"},{name:"B"}],civilizations:[]},history:[experienceSnapshot()]},snapshot:experienceSnapshot(),currentTurn:4,onSeek:vi.fn(),onSelectRegion:vi.fn()}) as unknown as SystemPanelProps;
it("shows unknown title cost as unknown and offer distinct from job",()=>{render(<AdaptiveLivelihoods {...props()}/>);expect(screen.getByRole("table",{name:"Personal work experience"})).toHaveTextContent("1 / 0.3 / Unknown / Unknown");expect(screen.getByText(/refused offer is a choice/)).toBeInTheDocument();});
it("shows evacuation and prior separated pair without asserting safety",()=>{render(<WarConsequences {...props()}/>);expect(screen.getByRole("table",{name:"Individual war events"})).toHaveTextContent("evacuated");expect(screen.getByRole("table",{name:"Separated family pairs"})).toHaveTextContent("#7 / #8");expect(screen.getByText(/without establishing safety/)).toBeInTheDocument();});
it("shows the actual retained D3 rows in a rules3 personal record-only control",()=>{
 const p=props(),snapshot=experienceSnapshot() as unknown as {livelihoods:{adaptive_livelihoods:Record<string,unknown>}};
 const a=snapshot.livelihoods.adaptive_livelihoods,f=a.frame as Record<string,unknown>;
 Object.assign(a,{rules:"3",mode:"record_only",decision_channels:"all"});
 Object.assign(f,{decision_channels:"all",rows:[[7,1,.2]],rows_total:1,rows_installed:1,
  a6_rows:[],a6_rows_total:0,d3_rows:[[7,1,.2]],d3_rows_total:1,migration_rows_would:[[7,1,-.2]],
  migration_rows_would_total:1,information_gate_installed:false});
 render(<AdaptiveLivelihoods {...p} snapshot={snapshot as unknown as SystemPanelProps["snapshot"]}/>);
 expect(screen.getByText(/D3 war inputs remain independent/)).toBeInTheDocument();
 fireEvent.click(screen.getByText("Actual and component migration inputs"));
 expect(screen.getByRole("table",{name:"Actual installed migration scores"})).toHaveTextContent("#7B0.2");
 expect(screen.getByRole("table",{name:"Independent D3 war component"})).toHaveTextContent("#7B0.2");
 expect(screen.getByRole("table",{name:"Would-be personal experience scores"})).toHaveTextContent("#7B-0.2");
 expect(screen.getByText(/gate not installed; not an applied input/)).toBeInTheDocument();
});
