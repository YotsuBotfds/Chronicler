import type { SystemPanelProps } from "../../lib/systems";
import { FoodAllocation } from "./FoodAllocation";
import { GrainConvoys } from "./GrainConvoys";
import { TimberStock } from "./TimberStock";
import { Workshops } from "./Workshops";

/**
 * Livelihoods sprint packages (default off): each section reads only its own
 * dated record and says so when it is absent; nothing is inferred across them.
 */
export function LivelihoodsPanel({ bundle, snapshot, currentTurn, onSelectRegion }: SystemPanelProps) {
  const row = snapshot as unknown as Record<string, unknown> | null;
  const record = (row?.livelihoods ?? null) as Record<string, unknown> | null;
  const props = { bundle, snapshot, currentTurn, onSelectRegion };
  return <div className="systems-body">
    {record?.workshops != null ? <Workshops {...props} /> : null}
    {record?.food_allocation != null ? <FoodAllocation {...props} /> : null}
    {record?.timber_stock != null ? <TimberStock {...props} /> : null}
    {record?.grain_convoys != null ? <GrainConvoys snapshot={snapshot} bundle={bundle} /> : null}
    {record == null ? <p className="systems-note">No livelihoods observation is recorded at snapshot {snapshot?.turn ?? currentTurn}.</p> : null}
  </div>;
}
