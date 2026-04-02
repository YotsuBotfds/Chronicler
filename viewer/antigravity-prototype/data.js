// Chronicler 7.5 Prototype — Data Definitions
// All fake but internally consistent simulation data

const CIVS = [
  { name: "Thornwall Hegemony", short: "Thornwall", color: "#4a6a4a", fill: "rgba(74,106,74,0.35)", pop: "1.24M", growth: "+0.8%", treasury: "14,280g", income: "+340g", trade: "+120g" },
  { name: "Ashenmere Compact", short: "Ashenmere", color: "#4a5a7a", fill: "rgba(74,90,122,0.35)", pop: "890K", growth: "+1.2%", treasury: "18,450g", income: "+510g", trade: "+290g" },
  { name: "Veldrath Confederation", short: "Veldrath", color: "#7a6a3a", fill: "rgba(122,106,58,0.35)", pop: "1.05M", growth: "-0.3%", treasury: "8,120g", income: "+180g", trade: "-40g" },
  { name: "Pale Coast League", short: "Pale Coast", color: "#6a4a7a", fill: "rgba(106,74,122,0.35)", pop: "720K", growth: "+0.5%", treasury: "22,100g", income: "+620g", trade: "+380g" },
  { name: "Ironhold Principality", short: "Ironhold", color: "#7a5040", fill: "rgba(122,80,64,0.35)", pop: "480K", growth: "+0.1%", treasury: "11,600g", income: "+260g", trade: "+80g" }
];

const REGIONS = [
  { name:"Cold Waste", owner:2, poly:[[200,55],[300,38],[450,32],[600,40],[720,55],[760,80],[740,140],[600,148],[450,142],[300,138],[210,130],[160,100]], settlements:[{name:"Frostwatch",x:460,y:85,cap:false}] },
  { name:"Grey Highlands", owner:0, poly:[[120,110],[160,100],[210,130],[300,138],[290,200],[275,275],[200,290],[120,265],[85,210],[90,155]], settlements:[{name:"Greycrest",x:190,y:210,cap:false}] },
  { name:"Mistwood", owner:1, poly:[[300,138],[450,142],[600,148],[590,205],[570,280],[440,285],[290,280],[290,200]], settlements:[{name:"Hollowgrove",x:430,y:215,cap:false}] },
  { name:"Ashenmere Fen", owner:1, poly:[[600,148],[740,140],[800,160],[845,220],[850,290],[770,300],[640,292],[570,280],[590,205]], settlements:[{name:"Ashenmere",x:710,y:225,cap:true},{name:"Fenwatch",x:790,y:260,cap:false}] },
  { name:"Thornwall March", owner:0, poly:[[85,280],[120,265],[200,290],[275,275],[285,350],[270,435],[190,445],[100,420],[70,355]], settlements:[{name:"Thornwall",x:185,y:360,cap:true},{name:"Redstock",x:140,y:310,cap:false}] },
  { name:"Sunken Reach", owner:1, poly:[[275,275],[440,285],[570,280],[560,355],[540,430],[420,440],[290,435],[270,435],[285,350]], settlements:[{name:"Deepmire",x:410,y:360,cap:false}] },
  { name:"Veldrath Steppe", owner:2, poly:[[570,280],[640,292],[770,300],[850,290],[880,355],[870,435],[790,455],[670,445],[540,430],[560,355]], settlements:[{name:"Kharstead",x:720,y:370,cap:true},{name:"Dusthollow",x:810,y:400,cap:false}] },
  { name:"Ember Vale", owner:0, poly:[[70,420],[100,420],[190,445],[195,520],[170,575],[110,585],[60,545],[50,475]], settlements:[{name:"Emberhearth",x:125,y:500,cap:false}] },
  { name:"Ironhold Peaks", owner:4, poly:[[190,445],[270,435],[290,435],[315,505],[285,575],[215,595],[155,585],[170,575],[195,520]], settlements:[{name:"Ironhold",x:240,y:515,cap:true}] },
  { name:"Silverdeep Basin", owner:3, poly:[[290,435],[420,440],[540,430],[530,505],[495,575],[385,595],[300,585],[285,575],[315,505]], settlements:[{name:"Silverdeep",x:410,y:510,cap:false}] },
  { name:"Pale Coast", owner:3, poly:[[540,430],[670,445],[790,455],[810,515],[785,575],[700,605],[580,595],[495,575],[530,505]], settlements:[{name:"Harborlight",x:660,y:520,cap:true},{name:"Tidemark",x:750,y:540,cap:false}] },
  { name:"Draken Shoals", owner:3, poly:[[385,595],[495,575],[580,595],[640,625],[600,665],[480,675],[370,655],[325,620],[300,585]], settlements:[{name:"Drakespit",x:470,y:635,cap:false}] }
];

const TRADE_ROUTES = [
  { from:{x:185,y:360}, to:{x:410,y:360}, label:"Thornwall–Deepmire", profit:"+340g", margin:"18%", goods:"Grain, Iron", confidence:"0.82" },
  { from:{x:410,y:360}, to:{x:710,y:225}, label:"Deepmire–Ashenmere", profit:"+520g", margin:"24%", goods:"Timber, Dyes", confidence:"0.71" },
  { from:{x:710,y:225}, to:{x:660,y:520}, label:"Ashenmere–Harborlight", profit:"+680g", margin:"31%", goods:"Spices, Textiles", confidence:"0.88" },
  { from:{x:660,y:520}, to:{x:240,y:515}, label:"Harborlight–Ironhold", profit:"+290g", margin:"12%", goods:"Iron Ore, Tools", confidence:"0.65" },
  { from:{x:185,y:360}, to:{x:720,y:370}, label:"Thornwall–Kharstead", profit:"-80g", margin:"-4%", goods:"Weapons, Hides", confidence:"0.34" },
  { from:{x:410,y:510}, to:{x:470,y:635}, label:"Silverdeep–Drakespit", profit:"+180g", margin:"15%", goods:"Salt, Fish", confidence:"0.76" }
];

const CAMPAIGN_ARMIES = [
  { name:"Thornwall 1st Host", civ:0, strength:"4,200", morale:"78%",
    path:[[185,360],[230,340],[275,320],[320,340],[350,355]],
    target:"Sunken Reach", status:"Advancing" },
  { name:"Veldrath Raiders", civ:2, strength:"2,800", morale:"91%",
    path:[[720,370],[680,340],[640,310],[600,290]],
    target:"Ashenmere Fen", status:"Raiding" },
  { name:"Pale Coast Marines", civ:3, strength:"1,600", morale:"85%",
    path:[[660,520],[620,560],[580,590],[530,610]],
    target:"Draken Shoals", status:"Garrison" }
];

const BATTLE_SITES = [
  { x:350, y:355, name:"Battle of Deepmire Ford", turn:3808, result:"Thornwall victory" },
  { x:600, y:290, name:"Raid on Mistwood Border", turn:3811, result:"Veldrath pyrrhic" }
];

const CHRONICLE_ENTRIES = [
  { turn:3812, text:"The Thornwall garrison at Redstock reports growing unrest among displaced Veldrath migrants. Governor Aldric's grain reserves fall below the winter threshold.", type:"narrated" },
  { turn:3811, text:"Veldrath raiders cross the Mistwood border under cover of fog. Ashenmere scouts report three villages burned, trade caravans scattered.", type:"narrated" },
  { turn:3810, text:"Ashenmere merchants abandon the northern route as bandit losses exceed tolerable margins. The Compact reroutes through Silverdeep at higher cost.", type:"narrated" },
  { turn:3809, text:"Ironhold Principality signs a non-aggression accord with the Pale Coast League, securing southern borders for both parties.", type:"mechanical" },
  { turn:3808, text:"The Battle of Deepmire Ford. Thornwall's 1st Host defeats a Veldrath raiding force attempting to seize the river crossing. 340 casualties.", type:"narrated" },
  { turn:3806, text:"A new copper vein discovered in the Ironhold Peaks. Mining output projected to increase 12% within 40 turns.", type:"mechanical" },
  { turn:3804, text:"Pale Coast trade delegation arrives at Ashenmere. Negotiations on tariff reduction stall over dye import quotas.", type:"mechanical" },
  { turn:3801, text:"Famine conditions in Cold Waste drive Veldrath population southward. Migration pressure on Thornwall March borders intensifies.", type:"narrated" }
];

const EVENT_LOG = [
  { turn:3812, type:"war", typeLabel:"WAR", desc:"Veldrath raids Thornwall border settlements" },
  { turn:3811, type:"trade", typeLabel:"TRADE", desc:"Route Ashenmere→Pale Coast disrupted" },
  { turn:3810, type:"diplo", typeLabel:"DIPLO", desc:"Non-aggression pact: Ironhold–Pale Coast" },
  { turn:3809, type:"expand", typeLabel:"EXPAND", desc:"Thornwall claims Deepmire Ford outpost" },
  { turn:3808, type:"war", typeLabel:"WAR", desc:"Battle of Deepmire Ford resolved" },
  { turn:3807, type:"culture", typeLabel:"CULTURE", desc:"Ashenmere festival — scholarly tradition +2" },
  { turn:3806, type:"trade", typeLabel:"TRADE", desc:"Ironhold copper output +12% projected" },
  { turn:3805, type:"war", typeLabel:"WAR", desc:"Veldrath muster at Kharstead" },
  { turn:3804, type:"diplo", typeLabel:"DIPLO", desc:"Pale Coast–Ashenmere tariff talks stall" },
  { turn:3803, type:"trade", typeLabel:"TRADE", desc:"Silverdeep salt production peak" },
  { turn:3802, type:"culture", typeLabel:"CULTURE", desc:"Great Person promoted: Eadric of Thornwall" },
  { turn:3801, type:"expand", typeLabel:"EXPAND", desc:"Cold Waste famine — migration south" }
];

const CHARACTER = {
  name: "Eadric of Thornwall",
  stableId: "GP-00481",
  born: 2840,
  age: 972,
  occupation: "High Marshal",
  civ: 0,
  location: "Thornwall March",
  isMule: true,
  muleMemory: "Deepmire Ford massacre (T3808)",
  muleTurns: 14,
  needs: { safety:0.72, sustenance:0.85, social:0.48, status:0.91, spiritual:0.33, stimulation:0.65 },
  relationships: [
    { name:"Aldric the Elder", relation:"Liege Lord", strength:0.88 },
    { name:"Sera of Ashenmere", relation:"Rival", strength:-0.45 },
    { name:"Bram Ironfist", relation:"Lieutenant", strength:0.72 },
    { name:"Mira Thornchild", relation:"Heir", strength:0.65 },
    { name:"Vorath Dustwalker", relation:"Enemy", strength:-0.82 }
  ],
  memories: [
    { turn:3808, text:"Witnessed Deepmire Ford massacre", intensity:0.95, legacy:true },
    { turn:3790, text:"Appointed High Marshal", intensity:0.70, legacy:false },
    { turn:3775, text:"Marriage to house Ashenmere fails", intensity:0.60, legacy:false },
    { turn:3750, text:"First command at Greycrest garrison", intensity:0.45, legacy:false },
    { turn:3680, text:"Survived plague winter in Ember Vale", intensity:0.80, legacy:true },
    { turn:2840, text:"Born in Redstock", intensity:0.30, legacy:false }
  ],
  dynasty: ["Aldric the Elder (Father)", "Mira Thornchild (Daughter)", "Bram II (Son, deceased T3790)"],
  decisions: ["Reinforce Redstock or pursue Veldrath raiders", "Accept Ashenmere trade terms or maintain embargo", "Promote Bram Ironfist to regional command"]
};

const BATCH_RESULTS = [
  { rank:1, seed:"4ASF-9B1D-7C6E", score:0.73, wars:5, collapses:1, events:12, tech:"+3.2", anomalies:0 },
  { rank:2, seed:"7FE2-4A3B-CC91", score:0.71, wars:4, collapses:2, events:9, tech:"+2.8", anomalies:1 },
  { rank:3, seed:"B3D1-8F7A-22E4", score:0.68, wars:6, collapses:0, events:11, tech:"+4.1", anomalies:0 },
  { rank:4, seed:"9C44-1BE6-5D3F", score:0.64, wars:3, collapses:1, events:8, tech:"+2.1", anomalies:2 },
  { rank:5, seed:"E8A7-3C2D-FF10", score:0.61, wars:7, collapses:3, events:14, tech:"+1.9", anomalies:1 },
  { rank:6, seed:"2D5B-AA41-8873", score:0.58, wars:2, collapses:0, events:6, tech:"+3.5", anomalies:0 },
  { rank:7, seed:"F1C9-6E8D-4B25", score:0.55, wars:4, collapses:1, events:7, tech:"+2.4", anomalies:0 },
  { rank:8, seed:"6A30-D7F5-1198", score:0.52, wars:3, collapses:0, events:5, tech:"+1.7", anomalies:3 },
  { rank:9, seed:"84E2-5BC0-A6D7", score:0.49, wars:2, collapses:2, events:4, tech:"+0.8", anomalies:0 },
  { rank:10, seed:"C7F1-19A4-E352", score:0.45, wars:1, collapses:0, events:3, tech:"+2.9", anomalies:1 },
  { rank:11, seed:"3B98-EC27-7F4A", score:0.42, wars:3, collapses:1, events:5, tech:"+1.2", anomalies:0 },
  { rank:12, seed:"DA65-4810-B3CE", score:0.38, wars:1, collapses:0, events:2, tech:"+0.5", anomalies:0 }
];

const TIMELINE_EVENTS = [
  { pos:5, type:"major" }, { pos:12, type:"narrated" }, { pos:18, type:"normal" },
  { pos:25, type:"narrated" }, { pos:30, type:"major" }, { pos:35, type:"normal" },
  { pos:42, type:"narrated" }, { pos:48, type:"normal" }, { pos:52, type:"major" },
  { pos:55, type:"narrated" }, { pos:60, type:"normal" }, { pos:63, type:"narrated" },
  { pos:67, type:"major" }, { pos:70, type:"normal" }, { pos:73, type:"narrated" },
  { pos:76, type:"major" }, { pos:78, type:"normal" }, { pos:82, type:"narrated" },
  { pos:88, type:"normal" }, { pos:92, type:"normal" }
];

const NARRATED_SEGMENTS = [
  { start:3, end:8 }, { start:11, end:15 }, { start:23, end:28 },
  { start:38, end:45 }, { start:50, end:56 }, { start:62, end:68 },
  { start:72, end:78 }, { start:85, end:90 }
];
