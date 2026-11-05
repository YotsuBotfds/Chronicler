import { describe, expect, it } from "vitest";
import type { TurnSnapshot } from "../../types";
import { apprenticeshipAt, apprenticeshipFunnel, apprenticeshipOutcomes, readApprenticeship } from "../apprenticeship";
import { apprentice, receipt, record, seat } from "./apprenticeshipFixture";

const snap = (apprenticeship: unknown, turn = 5) =>
  ({ turn, livelihoods: { schema_version: 1, apprenticeship } } as unknown as TurnSnapshot);
const reason = (x: unknown, regions = 3) => {
  const r = readApprenticeship(snap(x), regions);
  return r.status === "malformed" ? r.reason : r.status;
};

describe("apprenticeship reader", () => {
  it("reads dated, closing records and tells absent from malformed", () => {
    expect(apprenticeshipAt(snap(record), 3)?.qualifications[0].agent_id).toBe(7);
    expect(readApprenticeship(snap(record, 6), 3)).toEqual({ status: "malformed", reason: "misdated observation" });
    expect(readApprenticeship(({ turn: 5, livelihoods: { schema_version: 1 } } as unknown) as TurnSnapshot, 3))
      .toEqual({ status: "absent" });
    expect(readApprenticeship(null, 3)).toEqual({ status: "absent" });
    expect(reason(record, 2)).toBe("malformed site continuity");                  // region out of range
    expect(reason({ ...record, stage: "RS0" })).toBe("unknown apprenticeship schema");
  });

  it("refuses double work, foreign mentors and over-full seats", () => {
    const onCrew = { ...receipt, seats: [{ ...seat, agent_id: 8 }] };
    expect(reason({ ...record, receipts: [onCrew] })).toBe("an apprentice is also on the crew");
    const stranger = { ...receipt, seats: [{ ...seat, mentor: 9 }] };
    expect(reason({ ...record, receipts: [stranger] })).toBe("an apprentice was taught by someone who is not a mentor");
    const crowded = { ...receipt, seats: [21, 22, 24].map((a) => ({ ...seat, agent_id: a })) };
    expect(reason({ ...record, receipts: [crowded] })).toBe("more apprentices taught than mentors can teach");
    const twice = { ...receipt, seats: [seat, seat] };
    expect(reason({ ...record, receipts: [twice] })).toBe("a person holds two seats");
    const notCrew = { ...receipt, qualified_on_crew: [30], mentors: [30] };
    expect(reason({ ...record, receipts: [notCrew] })).toBe("a mentor is not a qualified crew member");
  });

  it("refuses wear and crew time that do not close", () => {
    expect(reason({ ...record, receipts: [{ ...receipt, upkeep_offset: 0.03, net_wear: -0.01 }] })).not.toBe("ok");
    expect(reason({ ...record, receipts: [{ ...receipt, net_wear: 0.02 }] })).toBe("wear does not close");
    expect(reason({ ...record, receipts: [{ ...receipt, craft_work: 0.5 }] })).toBe("crew time does not close");
    const idle = { ...receipt, operating: false };
    expect(reason({ ...record, receipts: [idle] })).toBe("a site that did not operate shows work");
    expect(reason({ ...record, receipts: [{ ...receipt, condition_after: 1.2 }] })).toBe("malformed site receipt");
    const overpaid = { ...receipt, seats: [{ ...seat, stipend_paid: 126 }] };
    expect(reason({ ...record, receipts: [overpaid] })).toBe("malformed site receipt");
  });

  it("refuses a qualified apprentice, an open record past completion and broken continuity", () => {
    expect(reason({ ...record, apprenticeships: [{ ...apprentice, agent_id: 7 }] }))
      .toBe("a qualified person is still an apprentice");
    expect(reason({ ...record, apprenticeships: [{ ...apprentice, attended: 10 }] })).toBe("malformed apprenticeships");
    expect(reason({ ...record, apprenticeships: [{ ...apprentice, gap: 5 }] })).toBe("malformed apprenticeships");
    expect(reason({ ...record, continuity: { ...record.continuity, qualified_elsewhere: 1 } }))
      .toBe("continuity does not close");
    const granted = { ...record, mode: "no_qualification",
      archive: [{ ...record.archive[0], ended_turn: 4 }] };
    expect(reason(granted)).toBe("a control completion was granted");
    expect(reason({ ...granted, archive: [{ ...record.archive[0], ended_turn: 4, granted: false }] })).toBe("ok");
  });

  it("keeps an unobserved turn unknown and orders the funnel and outcomes", () => {
    const unobserved = apprenticeshipAt(snap({ ...record, receipts: null, continuity: null }), 3);
    expect(unobserved?.receipts).toBeNull();
    expect(unobserved?.continuity).toBeNull();
    const parsed = apprenticeshipAt(snap(record), 3)!;
    const funnel = apprenticeshipFunnel(parsed);
    expect(funnel[0]).toEqual(["Site-turns observed", 8]);
    expect(funnel.at(-1)).toEqual(["Qualified by apprenticeship", 1]);
    expect(apprenticeshipFunnel({ ...parsed, counters: {} })[0]).toEqual(["Site-turns observed", 0]);
    expect(apprenticeshipOutcomes(parsed)).toEqual({ missed: [["away", 1]], ended: [["completed", 1], ["migrated", 1]] });
  });
});
