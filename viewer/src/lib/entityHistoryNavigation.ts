import type {EntityRef} from "./entityHistory";
/** A user action, scoped to the currently loaded app; no durable invented identity. */
export interface EntityHistoryRequest {entity:EntityRef;turn:number}
export const ENTITY_HISTORY_REQUEST="chronicler:entity-history";
let pending:EntityHistoryRequest|null=null;
export function requestEntityHistory(entity:EntityRef,turn:number){pending={entity,turn};if(typeof window!=="undefined")window.dispatchEvent(new Event(ENTITY_HISTORY_REQUEST));}
export function peekEntityHistoryRequest(){return pending;}
export function takeEntityHistoryRequest(){const value=pending;pending=null;return value;}
