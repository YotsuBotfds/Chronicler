import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AdaptiveLivelihoods, WarConsequences } from "../PersonalExperience";
import { experienceSnapshot } from "../../../lib/__tests__/personalExperienceFixture";
import type { SystemPanelProps } from "../../../lib/systems";
afterEach(cleanup);
const props=()=>({bundle:{world_state:{regions:[{name:"A"},{name:"B"}],civilizations:[]},history:[experienceSnapshot()]},snapshot:experienceSnapshot(),currentTurn:4,onSeek:vi.fn(),onSelectRegion:vi.fn()}) as unknown as SystemPanelProps;
it("shows unknown title cost as unknown and offer distinct from job",()=>{render(<AdaptiveLivelihoods {...props()}/>);expect(screen.getByRole("table",{name:"Personal work experience"})).toHaveTextContent("1 / 0.3 / Unknown / Unknown");expect(screen.getByText(/refused offer is a choice/)).toBeInTheDocument();});
it("shows evacuation and prior separated pair without asserting safety",()=>{render(<WarConsequences {...props()}/>);expect(screen.getByRole("table",{name:"Individual war events"})).toHaveTextContent("evacuated");expect(screen.getByRole("table",{name:"Separated family pairs"})).toHaveTextContent("#7 / #8");expect(screen.getByText(/without establishing safety/)).toBeInTheDocument();});
