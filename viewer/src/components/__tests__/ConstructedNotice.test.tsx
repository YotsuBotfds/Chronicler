import { cleanup,render,screen } from "@testing-library/react";
import { afterEach,expect,it } from "vitest";
import { ConstructedNotice } from "../ConstructedNotice";
import { constructedExample,isConstructedExample } from "../../lib/constructedExample";
afterEach(cleanup);
const marker={from:"a".repeat(64),edits:["Removed one completed-turn receipt to demonstrate unknown evidence"]};
it("labels only an explicit valid demonstration with source and edits",()=>{render(<ConstructedNotice bundle={{metadata:{constructed:marker}}}/>);expect(screen.getByRole("note",{name:"Constructed demonstration"})).toHaveTextContent("not evidence of natural activation");expect(screen.getByText(marker.edits[0])).toBeInTheDocument();});
it("does not infer a demonstration from filename, seed or natural feature modes",()=>{for(const metadata of [{seed:23},{example_kind:"constructed"},{constructed:null},{constructed:{from:"missing",edits:[]}}]){expect(constructedExample({metadata})).toBeNull();}render(<ConstructedNotice bundle={{metadata:{seed:23,sim_model:"constructed_filename"}}}/>);expect(screen.queryByRole("note")).not.toBeInTheDocument();});
it("rejects empty edits and invalid source identity",()=>{expect(isConstructedExample(marker)).toBe(true);expect(isConstructedExample({...marker,edits:[]})).toBe(false);expect(isConstructedExample({...marker,from:"unverified"})).toBe(false);});
