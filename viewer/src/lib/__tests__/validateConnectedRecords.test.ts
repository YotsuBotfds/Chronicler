import {expect,it} from "vitest";
import {validateConnectedRecords} from "../validateConnectedRecords";
import {timber,supplySnapshot} from "./supplyContractsFixture";
it("uses production book validation before marking a record eligible for narration",()=>{
 expect(validateConnectedRecords(supplySnapshot("timber_orders",timber),2,2).timber_orders).toBe("observed");
 const broken=structuredClone(timber);broken.orders[0].cash++;
 expect(validateConnectedRecords(supplySnapshot("timber_orders",broken),2,2).timber_orders).toBe("malformed");
 expect(validateConnectedRecords(supplySnapshot("timber_orders",{...timber,frame:null}),2,2).timber_orders).toBe("unobserved");
 expect(validateConnectedRecords(supplySnapshot("other",{}),2,2).timber_orders).toBe("absent");
});
