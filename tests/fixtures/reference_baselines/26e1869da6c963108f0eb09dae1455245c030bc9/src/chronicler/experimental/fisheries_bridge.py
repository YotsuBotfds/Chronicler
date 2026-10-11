"""Optional native catch patch; no changes to the default ecology schema."""
import pyarrow as pa


def build_fishery_yield_patch(world) -> pa.RecordBatch:
    from chronicler.models import ResourceType

    rows = [(rid, slot, region.resource_current_yields[slot])
            for rid, region in enumerate(world.regions)
            for slot, rtype in enumerate(region.resource_types)
            if rtype == ResourceType.FISH]
    return pa.record_batch({
        "region_id": pa.array([row[0] for row in rows], type=pa.uint16()),
        "slot": pa.array([row[1] for row in rows], type=pa.uint8()),
        "yield": pa.array([row[2] for row in rows], type=pa.float32()),
    })
