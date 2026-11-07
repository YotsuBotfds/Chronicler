# Linked entity histories

The Livelihoods viewer can compose completed-turn records into a linked history
of a named person, repair project, woodcutting expedition, titled shipment or
regional market. `entityHistory.ts` calls each package's strict reader; it never
reads a final-world object's history as evidence for an earlier snapshot.

Every displayed observation carries its snapshot, source turn, package, stable
entity identity, join, reading state and JSON pointer into the decoded bundle.
Related entity buttons move between a crew member and project or expedition,
and between a merchant and shipment. Snapshot buttons seek the recorded turn;
region buttons open the aggregate region inspector. The selector lists only
identities named at or before the currently selected snapshot.

The reading distinguishes off/unrecorded, unknown, rejected malformed records,
not in the bounded sample, truncated evidence, recorded none and recorded
observations. A frame's missing person names no activity in that frame, not a
claim that the person was inactive everywhere. No missing observation proves
death or migration. An inexact pool rebuild cannot establish continuity of a
person across the reset; this viewer does not invent an identity join for it.

Regional retail totals sit in rows explicitly labelled regional context, never
assigned to the person or project. Region context is attached only where an
accepted observation names the region at that snapshot, without carrying the
last known region forward through gaps. The PL1 home region and shipment origin
are context locations, not claims about a person's physical location. Existing
retail sample records ration/status but not who paid. Where an RS2 or PL1 record
names a crew and a total wage, the viewer preserves the crew total and says that
individual allocation is unrecorded. Stable participation links are not causal
links and no causal language is generated from them.

This is a saved-record composition, not a simulation switch or new authority.
No source, RNG, checkpoint or bundle schema changes are required. Packages not
represented by these adapters remain in their own panels until an explicit
strict adapter is added; the timeline does not silently infer their histories.

Focused tests use the retained natural seed-23 chain records and explicitly
constructed absent, malformed and capped variants. Browser journeys and broad
viewer checks are recorded separately with their actual build/source identity.

A4-3 and D4 add namespaced timber orders, food shipments, restitution claims
and string army ids. These identities are separate even if their numeric ids
match. Army allocation rows join the actual named army; the viewer never
infers that every person in a region was requisitioned. Claim rows show the
original cumulative obligation, actual paid amount, and unpaid difference.
The unpaid obligation is not household wealth. Timber cargo position is
labelled separately from its carrier's unrecorded residence. The strict
supply readers verify cargo/escrow identities and food-to-ration allocations
before contributing any linked fact; truncated samples never stand for the
whole liability ledger.

A6 history distinguishes exact personal cash, nullable forgone income/title
value, training progress, an offer decision, a native gate refusal, and a
migration score input. It never turns an input into a completed move. The
recorded destination-information mask preserves own past residence, living
bonds and dated packets as separate possible sources. Own closed cargo
experiences link only the named holder to that food shipment.

D3 records named wounds, releases, evacuation and return separately from the
prior X1 separation frame. A separation pair carries the actual T−1 source
turn, not the newer enclosing snapshot date. Evacuation does not establish
safety or a causal explanation for movement. The existing health care module
remains the injury authority. C4 guard rows name exact paid workers; regional
crowding, water service and patient supplies are attached only as explicitly
regional context, with their actual prior exposure date. Neither employment
nor regional exposure records diagnose an individual or attribute a death.
