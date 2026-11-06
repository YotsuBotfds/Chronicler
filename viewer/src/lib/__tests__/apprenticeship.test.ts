import { describe, expect, it } from "vitest";
import type { TurnSnapshot } from "../../types";
import { apprenticeshipAt, apprenticeshipFunnel, apprenticeshipOutcomes, readApprenticeship, usefulWork } from "../apprenticeship";
import { apprentice, receipt, record, seat } from "./apprenticeshipFixture";
import { attachedSeat, crewSeat, v2Receipt, v2Record } from "./productiveRecoveryFixture";

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

describe("apprenticeship reader, RS1 rules version 2 (schema 2)", () => {
  const v2 = (patch: object = {}) => reason({ ...v2Record, ...patch });
  const site = (patch: object) => v2({ receipts: [{ ...v2Receipt, ...patch }, v2Record.receipts[1]] });

  it("reads schema 2 with attached and crew apprentices, graduates and detached records; still reads schema 1", () => {
    expect(v2()).toBe("ok");
    const parsed = apprenticeshipAt(snap(v2Record), 3)!;
    expect(parsed.schema_version).toBe(2);
    expect(parsed.receipts![0].seats.map((s) => s.aboard)).toEqual(["crew", "attached", undefined]);
    expect(parsed.graduates?.[0].agent_id).toBe(30);
    expect(parsed.detached?.[0].reason).toBe("absent");
    expect(reason(record)).toBe("ok");                                       // schema 1 unchanged
    expect(apprenticeshipOutcomes(parsed)).toEqual({ missed: [["absent", 3], ["no_room", 1]],
      ended: [["completed", 1], ["long_absence", 1]] });
    expect(usefulWork(parsed)?.find(([k]) => k.startsWith("Apprentice-turns attached"))?.[1]).toBe(3);
    expect(usefulWork(apprenticeshipAt(snap(record), 3)!)).toBeNull();
  });

  it("refuses mixed versions and version-1 endings in a version-2 record", () => {
    expect(v2({ rules_version: undefined })).toBe("unknown apprenticeship rules version");
    expect(reason({ ...record, graduates: [] })).toBe("unknown apprenticeship rules version");
    expect(reason({ ...record, schema_version: 3 })).toBe("unknown apprenticeship schema");
    expect(reason({ ...record, receipts: [{ ...receipt, covered: true }, record.receipts[1]] })).toBe("malformed site receipt");
    expect(reason({ ...record, apprenticeships: [{ ...apprentice, on_crew: 1 }] })).toBe("malformed apprenticeships");
    expect(v2({ archive: [{ ...v2Record.archive[1], ended_reason: "migrated" }] })).toBe("malformed archive");
    expect(site({ seats: [{ ...crewSeat, outcome: "missed", reason: "away", mentor: null }] })).toBe("malformed site receipt");
  });

  it("refuses crew apprentices off the crew, attached apprentices on it and unreserved attendance", () => {
    expect(site({ crew: [7, 8, 9] })).toBe("a crew apprentice is not on the crew");
    expect(site({ crew: [7, 8, 9, 21, 22] })).toBe("an apprentice is also on the crew");
    expect(site({ seats: [{ ...crewSeat, share: 0.5 }] })).toBe("a crew apprentice was reserved or paid beside the crew");
    expect(site({ seats: [{ ...attachedSeat, share: 0.25 }] })).toBe("an attached apprentice was not reserved");
    expect(site({ seats: [{ ...attachedSeat, aboard: undefined }] })).toBe("an attended apprentice was not aboard");
  });

  it("refuses useful-work records that do not close", () => {
    expect(site({ covered: false })).toBe("coverage disagrees with the qualified crew");
    expect(site({ full_offset: true })).toBe("the full-offset flag disagrees with the wear");
    expect(site({ offset_by_via: { apprenticeship: 0.01, service: 0.01 } })).toBe("the upkeep offset by route does not close");
    expect(site({ graduates_on_crew: [99] })).toBe("a graduate counted aboard is not on the crew");
    expect(site({ offset_by_graduates: undefined })).toBe("malformed useful-work record");
    expect(v2({ receipts: [v2Receipt, { ...v2Record.receipts[1], covered: false }] })).toBe("a site that did not operate shows useful work");
  });

  it("refuses records whose attendance, absence or entry age do not close", () => {
    const open = v2Record.apprenticeships;
    expect(v2({ apprenticeships: [{ ...open[0], on_crew: 1 }, ...open.slice(1)] })).toBe("malformed apprenticeships");
    expect(v2({ apprenticeships: [{ ...open[0], absent: 5 }, ...open.slice(1)] })).toBe("malformed apprenticeships");
    expect(v2({ apprenticeships: [{ ...open[0], entry_age: 55 }, ...open.slice(1)] })).toBe("malformed apprenticeships");
    expect(v2({ apprenticeships: [{ ...open[0], gap: 6 }, ...open.slice(1)] })).toBe("ok");   // misses pause, never end
  });

  it("refuses graduates and detached records that disagree, and keeps unobserved turns unknown", () => {
    const g = v2Record.graduates[0];
    expect(v2({ mode: "no_qualification", archive: [] })).toBe("malformed graduates");          // the control grants nothing
    expect(v2({ graduates: [{ ...g, crew_turns: 1 }] })).toBe("malformed graduates");
    expect(v2({ graduates: [{ ...g, agent_id: 21 }] })).toBe("a graduate is still an apprentice");
    expect(v2({ detached: [{ ...v2Record.detached[0], agent_id: 22 }] })).toBe("a detached apprentice also holds a seat");
    expect(v2({ detached: [{ ...v2Record.detached[0], reason: "no_mentor" }] })).toBe("malformed detached records");
    expect(v2({ detached: null })).toBe("detached records without the turn's receipts");
    expect(v2({ receipts: null, detached: null, continuity: null })).toBe("ok");
  });
});
