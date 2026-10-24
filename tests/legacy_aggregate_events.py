"""Pre-columnar ``AgentBridge._aggregate_events`` (verbatim), the test oracle."""
from collections import Counter

from chronicler.agent_bridge import OCCUPATION_NAMES, SUMMARY_TEMPLATES, logger
from chronicler.models import Event


def legacy_aggregate_events(self, world, named_agents=None):
    """Check thresholds and emit summary Events."""
    if named_agents is None:
        named_agents = {}
    summaries = []
    current = list(self._event_window)[-1] if self._event_window else []
    region_names = {i: r.name for i, r in enumerate(world.regions)}
    region_populations = {
        idx: int(getattr(region, "population", 0) or 0)
        for idx, region in enumerate(world.regions)
    }
    try:
        region_pops = self._sim.get_region_populations()
        region_ids = region_pops.column("region_id").to_pylist()
        alive_counts = region_pops.column("alive_count").to_pylist()
        region_populations.update({
            int(region_id): int(alive_count)
            for region_id, alive_count in zip(region_ids, alive_counts)
        })
    except (AttributeError, KeyError, TypeError, ValueError):
        logger.debug("Falling back to region.population values for event aggregation")

    # === Single-tick patterns ===

    # Group current events by type and region
    migrations_by_source = {}
    rebellions_by_region = {}
    switches_by_region = {}
    for e in current:
        if e.event_type == "migration":
            migrations_by_source.setdefault(e.region, []).append(e)
        elif e.event_type == "rebellion":
            rebellions_by_region.setdefault(e.region, []).append(e)
        elif e.event_type == "occupation_switch":
            switches_by_region.setdefault(e.region, []).append(e)

    # Mass migration: >=8 agents leave one region in one tick
    for region_id, events in migrations_by_source.items():
        if len(events) >= 8:
            occ_counts = Counter(e.occupation for e in events)
            occ_majority = OCCUPATION_NAMES[occ_counts.most_common(1)[0][0]]
            targets = Counter(e.target_region for e in events)
            target_id = targets.most_common(1)[0][0]
            summaries.append(Event(
                turn=world.turn, event_type="mass_migration",
                actors=legacy_named_actors_in_region(self, region_id, named_agents, current),
                description=SUMMARY_TEMPLATES["mass_migration"].format(
                    count=len(events), occ_majority=occ_majority,
                    source_region=region_names.get(region_id, f"region {region_id}"),
                    target_region=region_names.get(target_id, f"region {target_id}"),
                ),
                importance=5, source="agent",
            ))

    # Local rebellion: >=5 agents rebel in one region
    for region_id, events in rebellions_by_region.items():
        if len(events) >= 5:
            occ_counts = Counter(e.occupation for e in events)
            occ_majority = OCCUPATION_NAMES[occ_counts.most_common(1)[0][0]]
            summaries.append(Event(
                turn=world.turn, event_type="local_rebellion",
                actors=legacy_named_actors_in_region(self, region_id, named_agents, current),
                description=SUMMARY_TEMPLATES["local_rebellion"].format(
                    count=len(events), occ_majority=occ_majority,
                    region=region_names.get(region_id, f"region {region_id}"),
                ),
                importance=7, source="agent",
            ))

    # Occupation shift: >25% of region switches in one tick
    for region_id, events in switches_by_region.items():
        region_pop = region_populations.get(region_id, 0)
        if region_pop > 0 and len(events) / region_pop > 0.25:
            new_occ_counts = Counter(e.occupation for e in events)
            new_occ = OCCUPATION_NAMES[new_occ_counts.most_common(1)[0][0]]
            summaries.append(Event(
                turn=world.turn, event_type="occupation_shift",
                actors=legacy_named_actors_in_region(self, region_id, named_agents, current),
                description=SUMMARY_TEMPLATES["occupation_shift"].format(
                    count=len(events),
                    region=region_names.get(region_id, f"region {region_id}"),
                    new_occupation=new_occ,
                ),
                importance=5, source="agent",
            ))

    # === Multi-turn patterns ===

    # Loyalty cascade: >=10 agents flip in one region over 5 turns
    loyalty_flips_by_region = {}
    window_depth = min(len(self._event_window), 5)
    window_list = list(self._event_window)
    for turn_events in window_list[-window_depth:]:
        for e in turn_events:
            if e.event_type == "loyalty_flip":
                loyalty_flips_by_region[e.region] = loyalty_flips_by_region.get(e.region, 0) + 1
    for region_id, count in loyalty_flips_by_region.items():
        if count >= 10:
            recent_flips = [
                e for turn_events in window_list[-window_depth:]
                for e in turn_events
                if e.event_type == "loyalty_flip" and e.region == region_id
            ]
            target_civ_counts = Counter(e.civ_affinity for e in recent_flips)
            target_civ_id = target_civ_counts.most_common(1)[0][0]
            target_civ_name = (world.civilizations[target_civ_id].name
                              if target_civ_id < len(world.civilizations)
                              else f"civ {target_civ_id}")
            summaries.append(Event(
                turn=world.turn, event_type="loyalty_cascade",
                actors=legacy_named_actors_in_region(self, region_id, named_agents, recent_flips),
                description=SUMMARY_TEMPLATES["loyalty_cascade"].format(
                    count=count,
                    region=region_names.get(region_id, f"region {region_id}"),
                    target_civ=target_civ_name,
                ),
                importance=6, source="agent",
            ))

    # Demographic crisis: region loses >30% over window
    if len(self._event_window) >= 2:
        deaths_by_region = {}
        births_by_region = {}
        for turn_events in self._event_window:
            for e in turn_events:
                if e.event_type == "death":
                    deaths_by_region[e.region] = deaths_by_region.get(e.region, 0) + 1
                elif e.event_type == "birth":
                    births_by_region[e.region] = births_by_region.get(e.region, 0) + 1
        for region_id, deaths in deaths_by_region.items():
            births = births_by_region.get(region_id, 0)
            net_loss = deaths - births
            if region_id < len(world.regions):
                region = world.regions[region_id]
                if region.population > 0 and net_loss > 0:
                    loss_pct = net_loss / (region.population + net_loss) * 100
                    if loss_pct > 30:
                        summaries.append(Event(
                            turn=world.turn, event_type="demographic_crisis",
                            actors=legacy_named_actors_in_region(self, region_id, named_agents, current),
                            description=SUMMARY_TEMPLATES["demographic_crisis"].format(
                                region=region_names.get(region_id, f"region {region_id}"),
                                pct=int(loss_pct),
                                window=len(self._event_window),
                            ),
                            importance=7, source="agent",
                        ))

    # === M30 new event types ===

    # Economic boom: >=10 occupation switches TO merchant over 20-turn window
    # [CALIBRATE: post-M28, initial 10]
    merchant_switches_by_region = {}
    boom_window = min(len(self._event_window), 20)
    boom_events = [e for t in list(self._event_window)[-boom_window:] for e in t]
    for e in boom_events:
        if e.event_type == "occupation_switch" and e.occupation == 2:  # merchant
            merchant_switches_by_region[e.region] = \
                merchant_switches_by_region.get(e.region, 0) + 1
    for region_id, count in merchant_switches_by_region.items():
        if count >= 10:
            summaries.append(Event(
                turn=world.turn, event_type="economic_boom",
                actors=legacy_named_actors_in_region(self, region_id, named_agents, boom_events),
                description=SUMMARY_TEMPLATES["economic_boom"].format(
                    region=region_names.get(region_id, f"region {region_id}"),
                    count=count, window=boom_window,
                ),
                importance=5, source="agent",
            ))

    # Brain drain: >=5 scholars leave region over 10-turn window
    # [CALIBRATE: post-M28, initial 5]
    scholar_departures_by_region = {}
    drain_window = min(len(self._event_window), 10)
    drain_events = [e for t in list(self._event_window)[-drain_window:] for e in t]
    for e in drain_events:
        if e.event_type == "migration" and e.occupation == 3:  # scholar
            scholar_departures_by_region[e.region] = \
                scholar_departures_by_region.get(e.region, 0) + 1
    for region_id, count in scholar_departures_by_region.items():
        if count >= 5:
            summaries.append(Event(
                turn=world.turn, event_type="brain_drain",
                actors=legacy_named_actors_in_region(self, region_id, named_agents, drain_events),
                description=SUMMARY_TEMPLATES["brain_drain"].format(
                    count=count,
                    region=region_names.get(region_id, f"region {region_id}"),
                    window=drain_window,
                ),
                importance=5, source="agent",
            ))

    return summaries

def legacy_named_actors_in_region(self, region_id, named_agents, current_events):
    """Find named character names involved in events for a given region."""
    actors = []
    for e in current_events:
        if e.region == region_id and e.agent_id in named_agents:
            name = named_agents[e.agent_id]
            if name not in actors:
                actors.append(name)
    return actors
