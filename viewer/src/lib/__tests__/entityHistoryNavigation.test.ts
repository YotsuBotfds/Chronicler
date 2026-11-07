import {afterEach,expect,it,vi} from "vitest";
import {ENTITY_HISTORY_REQUEST,requestEntityHistory,peekEntityHistoryRequest,takeEntityHistoryRequest} from "../entityHistoryNavigation";
afterEach(()=>takeEntityHistoryRequest());
it("carries only a user-requested stable reference and snapshot, then consumes it once",()=>{
 const listener=vi.fn();window.addEventListener(ENTITY_HISTORY_REQUEST,listener);
 requestEntityHistory({kind:"project",id:3},28);
 expect(listener).toHaveBeenCalledTimes(1);expect(peekEntityHistoryRequest()).toEqual({entity:{kind:"project",id:3},turn:28});
 expect(takeEntityHistoryRequest()?.entity.id).toBe(3);expect(takeEntityHistoryRequest()).toBeNull();
 window.removeEventListener(ENTITY_HISTORY_REQUEST,listener);
});
