/** Movement events (`agent_movements.py`); sect schisms and secessions use the shared types. */
export const MOVEMENT_EVENT_TYPES = [
  "movement_founded", "movement_spread", "movement_demand", "movement_reform", "movement_refused",
  "movement_crackdown", "movement_martyr", "movement_rising", "movement_concession", "movement_crushed",
  "movement_dispersed", "movement_end", "movement_leader", "reform_repealed", "reform_lapsed",
] as const;
