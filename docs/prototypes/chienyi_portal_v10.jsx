import React,{useState,useRef}from"react";

/* ============================================================
   ChienYi Portal v10 — Clean Rewrite
   
   DATA SOURCE MAP (prototype=mock, production=Odoo RPC/fields_get):
   - Selection fields (天氣/分類/階段/缺失類型) → model.fields_get()
   - Records (工程/日誌/檢查/缺失/照片/通報單) → model.search_read()
   - User info → res.users (uid)
   - Inspection templates → self.inspection.type.default_item_ids
   
   FRONTEND CONSTANTS (safe to hardcode):
   - S: color system
   - TABS: navigation structure
============================================================ */

const S={bg0:"#f5f6fa",bg2:"#ffffff",bg3:"#f0f1f5",bdr:"#e0e3eb",t1:"#1a1d26",t2:"#5a6070",t3:"#8b90a0",amber:"#e6a020",red:"#e8364f",green:"#22b357",blue:"#3b8de0",navH:76};
/* Light mode active. Production: use CSS variables for dark/light toggle:
   --portal-bg0, --portal-bg2, --portal-t1, etc.
   Toggle via body class or prefers-color-scheme media query */

// === MOCK DATA (all from backend API in production) ===
const INSPS=[{id:1,type:"模板工程自主檢查表",name:"INS-001",date:"2026/03/14",location:"B區基礎",state:"draft",checkedCount:0,totalCount:8,timing:"施工中"},{id:2,type:"鋼筋綁紮檢查表",name:"INS-002",date:"2026/03/12",location:"A區柱",state:"inspected",checkedCount:8,totalCount:8,timing:"施工後"}];
const DEFS=[{id:1,name:"DEF-001",type:"quality",desc:"混凝土蜂窩",location:"A區3F柱",deadline:"2026/03/20",state:"open",isOverdue:false,overdueDays:0,source:"daily_check"},{id:2,name:"DEF-002",type:"safety",desc:"安全網破損",location:"B區外牆",deadline:"2026/03/18",state:"open",isOverdue:false,overdueDays:0,source:"patrol"},{id:3,name:"DEF-003",type:"quality",desc:"鋼筋間距不足",location:"A區2F梁",deadline:"2026/03/13",state:"open",isOverdue:true,overdueDays:1,source:"daily_check"}];
const CLI=[{id:1,item:"模板尺寸",std:"±5mm",result:"",status:"",stage:"stage1"},{id:2,item:"支撐間距",std:"≤1.2m",result:"",status:"",stage:"stage1"},{id:3,item:"模板清潔",std:"無殘渣",result:"",status:"",stage:"stage1"},{id:4,item:"脫模劑塗佈",std:"均勻塗佈",result:"",status:"",stage:"stage2"},{id:5,item:"接縫密合度",std:"無漏漿",result:"",status:"",stage:"stage2"},{id:6,item:"預留孔位置",std:"圖說位置",result:"",status:"",stage:"stage2"},{id:7,item:"垂直度",std:"≤H/200",result:"",status:"",stage:"stage3"},{id:8,item:"表面平整度",std:"≤3mm/m",result:"",status:"",stage:"stage3"}];
const LD=[{date:"03/10",weekday:"一",status:"filled",weather:"晴/多雲",items:3},{date:"03/11",weekday:"二",status:"filled",weather:"多雲/雨",items:2},{date:"03/12",weekday:"三",status:"filled",weather:"晴/晴",items:4},{date:"03/13",weekday:"四",status:"empty"},{date:"03/14",weekday:"五",status:"empty"},{date:"03/15",weekday:"六",status:"today"},{date:"03/16",weekday:"日",status:"off"}];
const SLIPS=[{id:1,no:1,name:"第1次通報單",loc:"通河東街325巷口",state:"in_progress",pStart:"2026/03/01",pEnd:"2026/03/25",dur:25,items:3,amt:"1,200,000",iCnt:2,dCnt:1},{id:2,no:2,name:"第2次通報單",loc:"劍潭抽水站周邊",state:"not_started",pStart:"2026/03/20",pEnd:"2026/04/15",dur:27,items:5,amt:"850,000",iCnt:0,dCnt:0},{id:3,no:3,name:"第3次通報單",loc:"基河路排水箱涵",state:"draft",pStart:null,pEnd:null,dur:0,items:2,amt:"600,000",iCnt:0,dCnt:0}];
const PHOTOS_MOCK=[{id:1,name:"排水管線施工",date:"03/15",loc:"K0+150",cat:"PIP",src:"daily_log"},{id:2,name:"鋼筋綁紮完成",date:"03/15",loc:"A區2F",cat:"STL",src:"inspection"},{id:3,name:"模板組立",date:"03/14",loc:"B區基礎",cat:"FRM",src:"daily_log"},{id:4,name:"混凝土澆置",date:"03/14",loc:"A區3F",cat:"CON",src:"daily_log"},{id:5,name:"安全網檢查",date:"03/13",loc:"B區外牆",cat:"DEF",src:"defect"},{id:6,name:"回填作業",date:"03/12",loc:"K0+100",cat:"BKF",src:"other"}];
const WP={week:"2026/03/10 — 03/16",planned:3.2,actual:1.8,dailyTarget:"排水管線施工 + 回填作業"};
const WO=[{val:"sunny",label:"晴天",icon:"☀"},{val:"cloudy",label:"多雲",icon:"⛅"},{val:"overcast",label:"陰天",icon:"☁"},{val:"rainy",label:"雨天",icon:"🌧"},{val:"heavy_rain",label:"豪雨",icon:"⛈"},{val:"typhoon",label:"颱風",icon:"🌀"},{val:"foggy",label:"霧",icon:"🌫"}];
const CAT_OPTS=[{v:"STL",l:"鋼筋"},{v:"CON",l:"混凝土"},{v:"FRM",l:"模板"},{v:"PIP",l:"管線"},{v:"ELC",l:"電氣"},{v:"DEF",l:"缺失"},{v:"EXC",l:"開挖"},{v:"BKF",l:"回填"},{v:"PAV",l:"鋪面"},{v:"DRN",l:"排水"},{v:"OTH",l:"其他"}];
const PH_OPTS=[{v:"before",l:"施工前"},{v:"during",l:"施工中"},{v:"after",l:"施工後"},{v:"defect",l:"缺失"},{v:"acceptance",l:"驗收"}];
const PI={name:"士林區通河東街1段排水改善工程",code:"113070020302031",location:"通河東街1段325巷口至劍潭抽水站",contractAmount:"NT$ 28,500,000",contractStartDate:"2025/08/11",contractEndDate:"2026/06/30",contractDuration:324,actualDuration:247,totalApprovedDuration:324,authority:"臺北市政府工務局水利工程處",company:"千溢科技有限公司",contractors:["○○營造股份有限公司"],supervisionEngineer:"李○○",siteManager:"陳○○",projectType:"reservation",state:"construction"};
const PI_GEN={name:"大安區信義路排水改善工程",code:"113080030201015",location:"信義路四段至基隆路口",contractAmount:"NT$ 15,800,000",contractStartDate:"2025/09/01",contractEndDate:"2026/05/31",contractDuration:273,actualDuration:205,totalApprovedDuration:273,authority:"臺北市政府工務局水利工程處",company:"千溢科技有限公司",contractors:["△△營造股份有限公司"],supervisionEngineer:"林○○",siteManager:"吳○○",projectType:"general",state:"construction"};
const TABS=[{id:"info",nm:"工程資訊",ic:"🏗",bd:0},{id:"log",nm:"施工日誌",ic:"📋",bd:0},{id:"photo",nm:"照片中心",ic:"📷",bd:0},{id:"insp",nm:"自主檢查",ic:"🔍",bd:0},{id:"def",nm:"缺失改善",ic:"⚠",bd:0}];

// ============================================================
// APP COMPONENT
// ============================================================
function App(){
// --- State ---
const[currentProject,setCurrentProject]=useState(PI);
const projectType=currentProject.projectType;
const[activeTab,setActiveTab]=useState("home");
const[subPage,setSubPage]=useState(null);
const[showQuickAdd,setShowQuickAdd]=useState(false);
const[inspections,setInspections]=useState(INSPS);
const[defects,setDefects]=useState(DEFS);
const[logDays,setLogDays]=useState(LD);
const[slips]=useState(SLIPS);
const[manualTasks,setManualTasks]=useState({login:true,photo3:true,photo5:false});
const[dismissedEvts,setDismissedEvts]=useState({});
const[capturedFile,setCapturedFile]=useState(null);
const[navHistory,setNavHistory]=useState([]);
const isHome=activeTab==="home"&&!subPage;
const swipeRef=useRef({startX:0,startY:0,startTime:0});

// --- Computed: tasks (no defects/inspections - those are in event cards) ---
const tasks=[];
tasks.push({id:"login",name:"登入系統",score:5,done:manualTasks.login,icon:"🔓",type:"auto"});
tasks.push({id:"photo3",name:"上傳施工照片 ≥3張",score:15,done:manualTasks.photo3,icon:"📷",type:"daily"});
tasks.push({id:"photo5",name:"上傳照片達 5 張",score:10,done:manualTasks.photo5,icon:"📷",type:"daily"});
tasks.push({id:"log",name:"填寫今日施工日誌",score:30,done:logDays.some(d=>d.date==="03/15"&&d.status==="filled"),icon:"📋",type:"weekly",nav:"log"});

// --- Computed: events (from state, dismissable) ---
const evts=[];
defects.forEach(d=>{if(d.isOverdue&&d.state==="open"&&!dismissedEvts["def-"+d.id])evts.push({id:"def-"+d.id,tp:"urgent",tt:"缺失逾期",ds:d.name+" "+d.desc+" 逾期 "+d.overdueDays+" 天",act:"立即處理",nav:"def",item:d});});
inspections.forEach(i=>{if(i.state==="draft"&&!dismissedEvts["insp-"+i.id])evts.push({id:"insp-"+i.id,tp:"warn",tt:"自主檢查指派",ds:i.type+" 已指派給你",act:"前往檢查",nav:"insp",item:i});});

const openDefects=defects.filter(d=>!["verified","closed"].includes(d.state)).length;

// --- Navigation ---
const goBack=()=>{setShowQuickAdd(false);if(subPage){setSubPage(null);return;}setActiveTab("home");};
const doTask=(id)=>{const t=tasks.find(x=>x.id===id);if(!t||t.done)return;if(t.item){setActiveTab(t.nav||"def");setSubPage(t.nav==="def"?{type:"defForm",data:t.item}:{type:"inspForm",data:t.item});return;}if(t.nav){setActiveTab(t.nav);return;}setManualTasks(p=>({...p,[id]:true}));};

// --- Swipe ---
const handleTouchStart=(e)=>{swipeRef.current={startX:e.touches[0].clientX,startY:e.touches[0].clientY,startTime:Date.now()};};
const handleTouchEnd=(e)=>{const dx=e.changedTouches[0].clientX-swipeRef.current.startX;const dy=e.changedTouches[0].clientY-swipeRef.current.startY;const dt=Date.now()-swipeRef.current.startTime;if(dt<400&&Math.abs(dx)>80&&Math.abs(dx)>Math.abs(dy)*1.5){if(dx>0)goBack();}};

// --- Routing ---
const renderContent=()=>{
if(subPage?.type==="logForm")return <LogFormPage onBack={()=>setSubPage(null)} defects={defects} inspections={inspections} onSave={(date)=>{setLogDays(p=>p.map(d=>d.date===date?{...d,status:"filled",weather:"已填",items:1}:d));setSubPage(null);}}/>;
if(subPage?.type==="inspForm")return <InspectionFormPage insp={subPage.data} onBack={()=>setSubPage(null)} onSubmit={(insp,result)=>{if(insp.isNew){setInspections(p=>[{id:Date.now(),name:"INS-"+Date.now(),type:insp.type||"新增檢查",date:new Date().toLocaleDateString("zh-TW"),location:result.location||"",state:"inspected",checkedCount:result.checked,totalCount:result.total,timing:"施工中"},...p]);}else{setInspections(p=>p.map(x=>x.id===insp.id?{...x,state:"inspected",checkedCount:result.checked,totalCount:result.total}:x));}setSubPage(null);}}/>;
if(subPage?.type==="defForm")return <DefectFormPage defect={subPage.data} projectType={projectType} onBack={()=>setSubPage(null)} onSubmit={(defect,isNew)=>{if(isNew){setDefects(p=>[{id:Date.now(),name:"DEF-"+String(p.length+1).padStart(3,"0"),type:"quality",desc:defect.desc||"新提報缺失",location:defect.location||"",deadline:defect.deadline||"",state:"open",isOverdue:false,overdueDays:0,source:"daily_check"},...p]);}else{setDefects(p=>p.map(x=>x.id===defect.id?{...x,state:"action_taken"}:x));}setSubPage(null);}}/>;
if(subPage?.type==="fileManager")return <FileManagePage onBack={()=>setSubPage(null)} project={currentProject}/>;
if(subPage?.type==="newSlip")return <NewSlipPage onBack={()=>setSubPage(null)} project={currentProject}/>;
if(subPage?.type==="newProject")return <NewProjectPage onBack={()=>setSubPage(null)} onSave={(proj)=>{setCurrentProject(proj);setSubPage(null);}}/>;
if(subPage?.type==="projectSwitch")return <ProjectSwitchPage projects={[{id:1,data:PI,label:"通河東街排水改善(預約式)",type:"reservation"},{id:2,data:PI_GEN,label:"信義路排水改善(一般式)",type:"general"}]} current={currentProject} onSelect={(p)=>{if(p.data)setCurrentProject(p.data);setSubPage(null);}} onBack={()=>setSubPage(null)}/>;
if(subPage?.type==="slipDetail")return <SlipDetailPage slip={subPage.data} onBack={()=>setSubPage(null)} inspections={inspections} defects={defects} onOpenInsp={(i)=>setSubPage({type:"inspForm",data:i})} onOpenDef={(d)=>setSubPage({type:"defForm",data:d})}/>;
if(subPage?.type==="settings")return <SettingsPage onBack={()=>setSubPage(null)} projectType={projectType} currentProject={currentProject} setCurrentProject={setCurrentProject} setSubPage={setSubPage}/>;
if(subPage?.type==="photoUpload")return <PhotoUploadPage onBack={()=>{setCapturedFile(null);setSubPage(null);}} capturedFile={capturedFile}/>;
if(subPage?.type==="photoDetail")return <PhotoDetailPage photo={subPage.data} onBack={()=>setSubPage(null)}/>;
switch(activeTab){
case"info":return <InfoPage project={currentProject}/>;
case"log":return <LogListPage logDays={logDays} defects={defects} inspections={inspections} onEdit={(d)=>setSubPage({type:"logForm",data:d})}/>;
case"photo":return <PhotoListPage onUpload={()=>setSubPage({type:"photoUpload"})} onDetail={(p)=>setSubPage({type:"photoDetail",data:p})}/>;
case"insp":return <InspectionListPage projectType={projectType} inspections={inspections} onOpen={(i)=>setSubPage({type:"inspForm",data:i})}/>;
case"def":return <DefectListPage projectType={projectType} defects={defects} onOpen={(d)=>setSubPage({type:"defForm",data:d})}/>;
default:return renderHome();}};

// --- Home ---
const renderHome=()=>(<div style={{padding:"16px 14px",paddingBottom:S.navH+24}}>
{/* Event cards */}
{evts.map(ev=>(<div key={ev.id} style={{background:ev.tp==="urgent"?"rgba(232,54,79,0.06)":"rgba(230,160,32,0.06)",borderRadius:14,border:`1px solid ${ev.tp==="urgent"?"rgba(232,54,79,0.2)":"rgba(230,160,32,0.2)"}`,padding:16,marginBottom:10}}>
<div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start"}}>
<div style={{flex:1}}><div style={{fontSize:14,fontWeight:700,color:ev.tp==="urgent"?S.red:S.amber,marginBottom:4}}>{ev.tt}</div><div style={{fontSize:18,fontWeight:700,marginBottom:4}}>{ev.ds}</div></div>
<button onClick={()=>{setDismissedEvts(p=>({...p,[ev.id]:true}));if(ev.item){if(ev.nav==="def"){setActiveTab("def");setSubPage({type:"defForm",data:ev.item});}else if(ev.nav==="insp"){setActiveTab("insp");setSubPage({type:"inspForm",data:ev.item});}}else if(ev.nav)setActiveTab(ev.nav);}} style={{padding:"10px 16px",borderRadius:10,border:"none",background:ev.tp==="urgent"?S.red:S.amber,color:"#fff",fontSize:16,fontWeight:700,cursor:"pointer",minHeight:44,whiteSpace:"nowrap"}}>{ev.act} →</button>
</div></div>))}

{/* Weekly progress */}
<Sec title="本週進度"/>
<div onClick={()=>setSubPage({type:"logForm",data:"03/15"})} style={{background:S.bg2,borderRadius:14,border:`1px solid ${S.bdr}`,padding:16,marginBottom:12,cursor:"pointer"}}>
<div style={{fontSize:16,color:S.t2,marginBottom:8}}>{WP.week}</div>
<div style={{fontSize:17,color:S.t1,marginBottom:4}}>目標：{WP.dailyTarget}</div>
<div style={{display:"flex",gap:16,marginTop:12}}>{[{l:"預定進度",v:WP.planned,c:S.blue},{l:"實際進度",v:WP.actual,c:WP.actual>=WP.planned?S.green:S.amber},{l:"差異",v:(WP.actual-WP.planned).toFixed(1),c:S.red}].map((x,i)=>(<div key={i} style={{flex:1}}><div style={{fontSize:15,color:S.t3,marginBottom:4}}>{x.l}</div><div style={{fontSize:28,fontWeight:700,color:x.c}}>{x.v}%</div></div>))}</div>
<div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginTop:12,paddingTop:10,borderTop:`1px solid ${S.bdr}`}}><span style={{fontSize:15,color:S.t2}}>點擊填寫今日施工日誌</span><span style={{fontSize:16,fontWeight:700,color:S.amber}}>前往 →</span></div>
</div>

{/* Daily tasks */}
<Sec title="每日任務"/>
<div style={{background:S.bg2,borderRadius:16,border:`1px solid ${S.bdr}`,overflow:"hidden"}}>
<div style={{padding:16,background:"linear-gradient(135deg, rgba(230,160,32,0.05), transparent)",borderBottom:`1px solid ${S.bdr}`}}>
<div style={{padding:"10px 10px 4px",fontSize:15,fontWeight:700,color:S.t3}}>例行任務</div>
{tasks.filter(t=>t.type!=="notify").map(t=><TaskRow key={t.id} t={t} onDo={doTask}/>)}
</div></div>

{/* Notification slips (reservation only) */}
{projectType==="reservation"&&(<><Sec title="通報單"/>
{slips.map(sl=>{const stC={draft:S.t3,not_started:S.amber,in_progress:S.green,closed:S.t3};const stL={draft:"草稿",not_started:"未開始",in_progress:"施工中",closed:"已結案"};return(<div key={sl.id} onClick={()=>setSubPage({type:"slipDetail",data:sl})} style={{background:S.bg2,borderRadius:14,border:`1px solid ${S.bdr}`,padding:"18px 16px",marginBottom:12,cursor:"pointer",borderLeft:`4px solid ${stC[sl.state]}`}}>
<div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:6}}><div><div style={{fontSize:18,fontWeight:700}}>{sl.name}</div><div style={{fontSize:16,color:S.t2,marginTop:4}}>📍 {sl.loc}</div></div><span style={{fontSize:14,fontWeight:700,padding:"5px 12px",borderRadius:6,background:`${stC[sl.state]}22`,color:stC[sl.state]}}>{stL[sl.state]}</span></div>
<div style={{display:"flex",justifyContent:"space-between",fontSize:15,color:S.t2}}><span>{sl.pStart?`${sl.pStart} — ${sl.dur}天`:"未排定"}</span><span>{sl.items} 工項 · NT${sl.amt}</span></div>
<div style={{display:"flex",gap:12,marginTop:8,fontSize:15,color:S.t3}}><span>🔍 {sl.iCnt} 檢查</span><span>⚠ {sl.dCnt} 缺失</span><span style={{marginLeft:"auto",color:S.amber,fontWeight:700,fontSize:15}}>詳情 →</span></div>
</div>);})}
</>)}
</div>);

// --- Breadcrumbs ---
const renderBreadcrumbs=()=>{if(isHome)return null;
const crumbs=[{label:"首頁",action:()=>{setActiveTab("home");setSubPage(null);setShowQuickAdd(false);}}];
if(activeTab!=="home"){const tabLabel={info:"工程資訊",log:"施工日誌",photo:"照片中心",insp:"自主檢查",def:"缺失改善"}[activeTab]||"";crumbs.push({label:tabLabel,action:subPage?()=>setSubPage(null):null});}
if(subPage){const subLabel={logForm:"填寫日誌",inspForm:subPage.data?.isNew?"新增檢查":"檢查表單",defForm:subPage.data?.isNew?"提報缺失":"改善表單",settings:"設定",projectSwitch:"切換工程",newProject:"新增專案",newSlip:"新增通報單",fileManager:"檔案管理",photoUpload:"上傳照片",photoDetail:"照片詳情",slipDetail:"通報單詳情"}[subPage.type]||"";crumbs.push({label:subLabel,action:null});}
const show=crumbs.length<=3?crumbs:[crumbs[0],{label:"⋯",action:crumbs[crumbs.length-2].action},crumbs[crumbs.length-1]];
return(<div style={{display:"flex",alignItems:"stretch",marginBottom:10,background:"rgba(230,160,32,0.06)",border:"1px solid rgba(0,0,0,0.08)",borderRadius:12,overflow:"hidden",minHeight:48}}>
{show.map((cr,i)=>{const isLast=i===show.length-1;return(<React.Fragment key={i}>{i>0&&<div style={{width:1,background:"rgba(230,160,32,0.15)",alignSelf:"stretch"}}/>}<div onClick={cr.action||undefined} style={{flex:1,display:"flex",alignItems:"center",justifyContent:"center",padding:"12px 8px",cursor:cr.action?"pointer":"default",background:isLast?"rgba(230,160,32,0.08)":"transparent"}}><span style={{fontSize:17,fontWeight:isLast?700:600,color:isLast?S.amber:S.t3,textAlign:"center",overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{cr.label}</span></div></React.Fragment>);})}</div>);};

// --- Render ---
return(<div onTouchStart={handleTouchStart} onTouchEnd={handleTouchEnd} style={{maxWidth:430,margin:"0 auto",minHeight:"100vh",background:S.bg0,color:S.t1,fontFamily:'-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif',position:"relative",overflow:"hidden"}}>
{/* HUD */}
<div style={{background:"linear-gradient(180deg, rgba(255,255,255,0.97), rgba(248,249,252,0.92))",backdropFilter:"blur(10px)",padding:"14px 16px 12px",borderBottom:"1px solid rgba(0,0,0,0.08)",position:"fixed",top:0,left:"50%",transform:"translateX(-50%)",width:"100%",maxWidth:430,zIndex:100}}>
<div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:4}}>
<div style={{textAlign:"left"}}><div style={{fontSize:13,color:S.t3,letterSpacing:2,fontWeight:600}}>DAY</div><div style={{fontSize:30,fontWeight:900,color:S.amber,fontVariantNumeric:"tabular-nums"}}>{currentProject.actualDuration||0}</div></div>
<div style={{flex:1,textAlign:"center",padding:"0 12px",overflow:"hidden"}}><div style={{fontSize:15,color:S.t1,fontWeight:600,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{currentProject.name||""}</div></div>
<div onClick={()=>setSubPage({type:"settings"})} style={{width:44,height:44,borderRadius:22,background:"linear-gradient(135deg, #e6a020, #d4880a)",display:"flex",alignItems:"center",justifyContent:"center",fontSize:16,fontWeight:900,color:"#fff",cursor:"pointer",border:"2px solid rgba(230,160,32,0.25)",boxShadow:"0 2px 8px rgba(230,160,32,0.2)",flexShrink:0}}><span>阿</span></div>
</div>
{/* Breadcrumbs */}
{renderBreadcrumbs()}
{/* Resource bar (home only) */}
{isHome&&(<div style={{display:"flex",gap:6}}>
<div onClick={()=>setActiveTab("info")} style={{flex:1,textAlign:"center",padding:"10px 4px",background:S.bg2,borderRadius:10,border:`1px solid ${S.bdr}`,cursor:"pointer"}}><div style={{fontSize:24,fontWeight:700,color:"#1a9e94",fontVariantNumeric:"tabular-nums"}}>{currentProject.totalApprovedDuration?Math.round(currentProject.actualDuration/currentProject.totalApprovedDuration*100):0}%</div><div style={{fontSize:14,color:S.t2,marginTop:2,fontWeight:600}}>工程進度</div></div>
<div style={{flex:1,position:"relative"}}><div onClick={()=>setShowQuickAdd(!showQuickAdd)} style={{textAlign:"center",padding:"10px 4px",background:showQuickAdd?"rgba(230,160,32,0.12)":S.bg2,borderRadius:10,border:`1px solid ${showQuickAdd?S.amber:S.bdr}`,cursor:"pointer"}}><div style={{fontSize:24,fontWeight:700,color:"#d4940a"}}>＋</div><div style={{fontSize:14,color:S.t2,marginTop:2,fontWeight:600}}>快速新增</div></div>
{showQuickAdd&&(<div style={{position:"absolute",top:"100%",left:"50%",transform:"translateX(-50%)",marginTop:8,width:200,background:S.bg2,borderRadius:14,border:`1px solid ${S.bdr}`,padding:8,zIndex:300,boxShadow:"0 8px 32px rgba(0,0,0,0.12)"}}>
{[{label:"新增專案",icon:"➕",action:()=>{setSubPage({type:"newProject"});setShowQuickAdd(false);}},
...(projectType==="reservation"?[{label:"通報單",icon:"📄",action:()=>{setSubPage({type:"newSlip"});setShowQuickAdd(false);}}]:[]),
{label:"施工日誌",icon:"📋",action:()=>{setSubPage({type:"logForm",data:"03/15"});setShowQuickAdd(false);}},
{label:"自主檢查",icon:"🔍",action:()=>{setActiveTab("insp");setSubPage({type:"inspForm",data:{id:0,isNew:true}});setShowQuickAdd(false);}},
{label:"缺失改善",icon:"⚠",action:()=>{setActiveTab("def");setSubPage({type:"defForm",data:{id:0,isNew:true}});setShowQuickAdd(false);}},
{label:"檔案上傳",icon:"📂",action:()=>{setSubPage({type:"fileManager"});setShowQuickAdd(false);}},
].map((item,i)=>(<div key={i} onClick={item.action} style={{display:"flex",alignItems:"center",gap:10,padding:"12px 12px",borderRadius:10,cursor:"pointer",minHeight:44}}><span style={{fontSize:20}}>{item.icon}</span><span style={{fontSize:15,fontWeight:600,color:S.t1}}>{item.label}</span></div>))}</div>)}</div>
<div onClick={()=>setActiveTab("def")} style={{flex:1,textAlign:"center",padding:"10px 4px",background:S.bg2,borderRadius:10,border:`1px solid ${openDefects>0?"rgba(232,54,79,0.25)":S.bdr}`,cursor:"pointer"}}><div style={{fontSize:24,fontWeight:700,color:S.red,fontVariantNumeric:"tabular-nums"}}>{openDefects}件</div><div style={{fontSize:14,color:S.t2,marginTop:2,fontWeight:600}}>待改缺失</div></div>
</div>)}
</div>
{/* Content */}
<div style={{paddingTop:isHome?176:168,overflowY:"auto",WebkitOverflowScrolling:"touch"}}>{renderContent()}</div>
{/* Bottom Nav */}
<div style={{position:"fixed",bottom:0,left:"50%",transform:"translateX(-50%)",width:"100%",maxWidth:430,background:"rgba(255,255,255,0.97)",backdropFilter:"blur(10px)",borderTop:"1px solid rgba(0,0,0,0.08)",display:"flex",padding:"8px 4px",paddingBottom:"max(8px, env(safe-area-inset-bottom))",zIndex:100}}>
{TABS.map(tab=>{const active=activeTab===tab.id;const bd=tab.id==="insp"?inspections.filter(x=>x.state==="draft").length:tab.id==="def"?openDefects:tab.id==="log"?logDays.filter(d=>d.status==="empty"||d.status==="today").length:0;return(<div key={tab.id} onClick={()=>{setActiveTab(tab.id);setSubPage(null);setShowQuickAdd(false);}} style={{flex:1,textAlign:"center",padding:"6px 0",cursor:"pointer",position:"relative"}}>
<div style={{fontSize:24}}>{tab.ic}</div>
<div style={{fontSize:13,fontWeight:active?700:600,color:active?S.amber:S.t3,marginTop:2}}>{tab.nm}</div>
{bd>0&&<div style={{position:"absolute",top:-2,right:"50%",transform:"translateX(16px)",minWidth:20,height:20,background:S.red,color:"#fff",borderRadius:10,fontSize:11,fontWeight:900,display:"flex",alignItems:"center",justifyContent:"center",padding:"0 4px"}}>{bd}</div>}
</div>);})}
</div>
{/* FAB Camera */}
<label style={{position:"fixed",bottom:S.navH+16,right:16,zIndex:200,display:activeTab==="photo"?"none":"block"}}>
<input type="file" accept="image/*" capture="environment" style={{display:"none"}} onChange={(e)=>{if(e.target.files&&e.target.files[0]){setCapturedFile(e.target.files[0]);setActiveTab("photo");setSubPage({type:"photoUpload",data:{fromCamera:true}});}}}/>
<div style={{width:56,height:56,borderRadius:16,background:`linear-gradient(135deg, ${S.amber}, #cc8a10)`,display:"flex",alignItems:"center",justifyContent:"center",fontSize:24,boxShadow:"0 4px 20px rgba(230,160,32,0.2)",cursor:"pointer",color:"#000"}}>📷</div>
</label>
</div>);}

// ============================================================
// INSPECTION LIST PAGE
// ============================================================
function InspectionListPage({onOpen,projectType,inspections}){
const[slipFilter,setSlipFilter]=useState("all");
const inspData=inspections||INSPS;
const sC={draft:S.amber,inspected:S.blue,confirmed:S.green,closed:S.t3};
const sL={draft:"待檢查",inspected:"已檢查",confirmed:"已確認",closed:"已結案"};
return(<div style={{padding:"16px 14px",paddingBottom:S.navH+24}}>
<Sec title="自主檢查"/>
<button onClick={()=>onOpen({id:0,isNew:true})} style={{width:"100%",padding:"14px 20px",borderRadius:10,border:"none",background:`linear-gradient(135deg, ${S.amber}, #cc8a10)`,color:"#fff",fontSize:16,fontWeight:700,cursor:"pointer",minHeight:48,marginBottom:10}}>+ 新增檢查</button>
<div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:14}}><span style={{fontSize:16,fontWeight:700}}>共 {inspData.length} 筆</span></div>
{projectType==="reservation"&&(<div style={{display:"flex",flexWrap:"wrap",gap:6,marginBottom:14}}><button onClick={()=>setSlipFilter("all")} style={{padding:"8px 14px",borderRadius:8,border:"none",fontSize:15,fontWeight:600,cursor:"pointer",minHeight:44,background:slipFilter==="all"?S.amber:S.bg3,color:slipFilter==="all"?"#fff":S.t3}}>全部</button>{SLIPS.map(sl=>(<button key={sl.id} onClick={()=>setSlipFilter(sl.no)} style={{padding:"8px 14px",borderRadius:8,border:"none",fontSize:15,fontWeight:600,cursor:"pointer",minHeight:44,background:slipFilter===sl.no?S.amber:S.bg3,color:slipFilter===sl.no?"#fff":S.t3}}>第{sl.no}次</button>))}</div>)}
{inspData.map(insp=>(<div key={insp.id} onClick={()=>onOpen(insp)} style={{background:S.bg2,borderRadius:14,border:`1px solid ${S.bdr}`,padding:"18px 16px",marginBottom:12,cursor:"pointer",borderLeft:`4px solid ${sC[insp.state]}`}}>
<div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start"}}><div><div style={{fontSize:17,fontWeight:700}}>{insp.type}</div><div style={{fontSize:16,color:S.t2,marginTop:4}}>{insp.location} / {insp.date}</div></div><span style={{fontSize:14,fontWeight:700,padding:"5px 12px",borderRadius:6,background:`${sC[insp.state]}22`,color:sC[insp.state]}}>{sL[insp.state]}</span></div>
<div style={{display:"flex",gap:12,marginTop:8,fontSize:15,color:S.t3}}><span>✓ {insp.checkedCount}/{insp.totalCount} 項</span><span>{insp.timing}</span></div>
</div>))}
</div>);}

// ============================================================
// INSPECTION FORM PAGE
// ============================================================
function InspectionFormPage({insp,onBack,onSubmit}){
const isNew=insp?.isNew||false;
const[items,setItems]=useState(isNew?[]:CLI.map(x=>({...x})));
const toggleItem=(id,val)=>setItems(p=>p.map(x=>x.id===id?{...x,status:val}:x));
const checkedCount=items.filter(x=>x.status).length;
const stages=[...new Set(items.map(x=>x.stage))];
const stageLabels={stage1:"第一查驗階段",stage2:"第二查驗階段",stage3:"第三查驗階段"};
return(<div style={{padding:"16px 14px",paddingBottom:120}}>
<div style={{textAlign:"center",marginBottom:16}}>
<div style={{fontSize:26,fontWeight:900,color:S.amber}}>{isNew?"新增自主檢查":(insp?.type||"自主檢查表")}</div>
<div style={{fontSize:16,color:S.t2,marginTop:4}}>{isNew?"選擇檢查類型後自動載入項目":`${insp?.name} / ${insp?.date||""}`}</div>
</div>
<div style={{background:S.bg2,borderRadius:14,border:`1px solid ${S.bdr}`,padding:16,marginBottom:14}}>
{isNew&&(<div style={{marginBottom:14}}><div style={{fontSize:16,fontWeight:600,color:S.t2,marginBottom:8}}>檢查類型</div><div style={{display:"flex",flexWrap:"wrap",gap:8}}>{["模板工程","鋼筋綁紮","混凝土澆置","防水工程","管線埋設"].map(t=>(<button key={t} onClick={()=>setItems(CLI.map(x=>({...x})))} style={{padding:"10px 16px",borderRadius:10,border:"none",cursor:"pointer",minHeight:44,fontSize:15,fontWeight:600,background:S.bg3,color:S.t2}}>{t}</button>))}</div></div>)}
<FormField label="檢查位置" placeholder="例：B區基礎"/>
<FormField label="檢查時機" placeholder="施工中"/>
</div>
{stages.map(stage=>(<div key={stage} style={{marginBottom:14}}>
<div style={{fontSize:16,fontWeight:700,color:S.amber,marginBottom:8}}>{stageLabels[stage]||stage}</div>
{items.filter(x=>x.stage===stage).map(item=>(<div key={item.id} style={{background:S.bg2,borderRadius:12,border:`1px solid ${S.bdr}`,padding:14,marginBottom:8}}>
<div style={{fontSize:18,fontWeight:600,marginBottom:6}}>{item.item}</div>
<div style={{fontSize:15,color:S.t2,marginBottom:10}}>標準：{item.std}</div>
<div style={{display:"flex",gap:8}}>{[{v:"pass",l:"合格",c:S.green},{v:"defect",l:"有缺失",c:S.red},{v:"na",l:"無此項",c:S.t3}].map(opt=>(<button key={opt.v} onClick={()=>toggleItem(item.id,opt.v)} style={{flex:1,padding:"10px",borderRadius:10,border:"none",cursor:"pointer",minHeight:44,fontSize:15,fontWeight:700,background:item.status===opt.v?opt.c:S.bg3,color:item.status===opt.v?"#fff":S.t2}}>{opt.l}</button>))}</div>
</div>))}
</div>))}
<CollapseSection title="檢查照片" defaultOpen={false}><PhotoPickerInline label="拍攝檢查照片"/></CollapseSection>
<CollapseSection title="備註" defaultOpen={false}><textarea placeholder="備註說明..." style={{width:"100%",minHeight:80,padding:14,borderRadius:10,border:`1px solid ${S.bdr}`,background:S.bg0,color:S.t1,fontSize:17,fontFamily:"inherit",resize:"vertical"}}/></CollapseSection>
<button onClick={()=>{if(onSubmit)onSubmit(insp,{checked:checkedCount,total:items.length});else onBack();}} style={{width:"100%",padding:"20px",borderRadius:14,border:"none",background:`linear-gradient(135deg, ${S.amber}, #cc8a10)`,color:"#fff",fontSize:20,fontWeight:900,cursor:"pointer",marginTop:16,minHeight:64,boxShadow:"0 4px 20px rgba(230,160,32,0.2)"}}>{isNew?"建立檢查表":"提交檢查結果"} {items.length>0&&`(${checkedCount}/${items.length})`}</button>
</div>);}

// ============================================================
// DEFECT LIST PAGE
// ============================================================
function DefectListPage({onOpen,projectType,defects}){
const[slipFilter,setSlipFilter]=useState("all");
const defData=defects||DEFS;
const sC={open:S.red,investigating:S.amber,action_taken:S.blue,verified:S.green,closed:S.t3};
const sL={open:"待改善",investigating:"調查中",action_taken:"已採措施",verified:"已驗證",closed:"已結案"};
return(<div style={{padding:"16px 14px",paddingBottom:S.navH+24}}>
<Sec title="缺失改善"/>
<button onClick={()=>onOpen({id:0,isNew:true})} style={{width:"100%",padding:"14px 20px",borderRadius:10,border:"none",background:`linear-gradient(135deg, ${S.red}, #c0292b)`,color:"#fff",fontSize:16,fontWeight:700,cursor:"pointer",minHeight:48,marginBottom:10}}>+ 提報缺失</button>
<div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:14}}><span style={{fontSize:16,fontWeight:700}}>共 {defData.length} 筆</span></div>
{projectType==="reservation"&&(<div style={{display:"flex",flexWrap:"wrap",gap:6,marginBottom:14}}><button onClick={()=>setSlipFilter("all")} style={{padding:"8px 14px",borderRadius:8,border:"none",fontSize:15,fontWeight:600,cursor:"pointer",minHeight:44,background:slipFilter==="all"?S.amber:S.bg3,color:slipFilter==="all"?"#fff":S.t3}}>全部</button>{SLIPS.map(sl=>(<button key={sl.id} onClick={()=>setSlipFilter(sl.no)} style={{padding:"8px 14px",borderRadius:8,border:"none",fontSize:15,fontWeight:600,cursor:"pointer",minHeight:44,background:slipFilter===sl.no?S.amber:S.bg3,color:slipFilter===sl.no?"#fff":S.t3}}>第{sl.no}次</button>))}</div>)}
{defData.map(d=>(<div key={d.id} onClick={()=>onOpen(d)} style={{background:S.bg2,borderRadius:14,border:`1px solid ${S.bdr}`,padding:"18px 16px",marginBottom:12,cursor:"pointer",borderLeft:`4px solid ${sC[d.state]}`}}>
<div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start"}}><div><div style={{fontSize:17,fontWeight:700}}>{d.name}</div><div style={{fontSize:17,color:S.t1,marginBottom:3}}>{d.desc}</div><div style={{fontSize:16,color:S.t2,marginTop:4}}>📍 {d.location}</div></div><span style={{fontSize:14,fontWeight:700,padding:"5px 12px",borderRadius:6,background:`${sC[d.state]}22`,color:sC[d.state]}}>{sL[d.state]}</span></div>
{d.isOverdue&&<div style={{fontSize:15,color:S.red,fontWeight:700,marginTop:6}}>⚠ 逾期 {d.overdueDays} 天</div>}
</div>))}
</div>);}

// ============================================================
// DEFECT FORM PAGE
// ============================================================
function DefectFormPage({defect,onBack,projectType,onSubmit}){
const d=defect||DEFS[0];const isNew=d.isNew||false;
const[improvement,setImprovement]=useState("");const[corrective,setCorrective]=useState("");const[preventive,setPreventive]=useState("");
const sC={open:S.red,investigating:S.amber,action_taken:S.blue,verified:S.green,closed:S.t3};
const sL={open:"待改善",investigating:"調查中",action_taken:"已採措施",verified:"已驗證",closed:"已結案"};
return(<div style={{padding:"16px 14px",paddingBottom:120}}>
{isNew?(<div style={{textAlign:"center",marginBottom:16}}><div style={{fontSize:26,fontWeight:900,color:S.amber}}>提報新缺失</div><div style={{fontSize:16,color:S.t2,marginTop:4}}>填寫缺失資訊並上傳照片</div></div>):(<div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:16}}><div><div style={{fontSize:26,fontWeight:900,color:d.isOverdue?S.red:S.amber}}>{d.name}</div><div style={{fontSize:16,color:S.t2,marginTop:4}}>{d.desc}</div></div><div style={{padding:"6px 14px",borderRadius:8,background:`${sC[d.state]}22`,color:sC[d.state],fontSize:16,fontWeight:700}}>{sL[d.state]}</div></div>)}
{d.isOverdue&&!isNew&&(<div style={{background:"rgba(232,54,79,0.06)",borderRadius:14,padding:16,marginBottom:14,border:"1px solid rgba(232,54,79,0.2)"}}><div style={{fontSize:16,fontWeight:700,color:S.red}}>⚠ 已逾期 {d.overdueDays} 天</div><div style={{fontSize:15,color:S.t2,marginTop:4}}>改善期限：{d.deadline}</div></div>)}

{isNew?(<div style={{background:S.bg2,borderRadius:14,border:`1px solid ${S.bdr}`,padding:16,marginBottom:14}}>
<FormField label="缺失說明" placeholder="描述缺失具體情形..." multiline/>
<FormField label="發生位置" placeholder="例：B區基礎 K0+150"/>
<div style={{marginBottom:14}}><div style={{fontSize:16,fontWeight:600,color:S.t2,marginBottom:8}}>缺失類型</div><div style={{display:"flex",flexWrap:"wrap",gap:8}}>{[{v:"quality",l:"品質"},{v:"safety",l:"安全"},{v:"environmental",l:"環保"},{v:"schedule",l:"進度"},{v:"documentation",l:"文件"}].map(t=>(<button key={t.v} style={{padding:"10px 16px",borderRadius:10,border:"none",cursor:"pointer",minHeight:44,fontSize:15,fontWeight:600,background:S.bg3,color:S.t2}}>{t.l}</button>))}</div></div>
</div>):(<div style={{background:S.bg2,borderRadius:14,border:`1px solid ${S.bdr}`,padding:"4px 16px",marginBottom:14}}>
<InfoRow label="缺失類型" val={d.type==="quality"?"品質缺失":d.type==="safety"?"安全缺失":d.type}/>
<InfoRow label="發生位置" val={d.location}/><InfoRow label="缺失來源" val={d.source}/><InfoRow label="改善期限" val={d.deadline} accent={d.isOverdue?S.red:null}/>
</div>)}

<CollapseSection title={isNew?"缺失現場照片":"缺失照片（提報時上傳）"} defaultOpen={true}>
{isNew?<PhotoPickerInline label="拍攝缺失現場照片" color={S.red}/>:<div><div style={{display:"flex",gap:8,flexWrap:"wrap"}}>{[1,2].map(i=>(<div key={i} style={{width:100,height:100,background:S.bg3,borderRadius:10,display:"flex",alignItems:"center",justifyContent:"center",fontSize:32}}>🖼</div>))}</div><div style={{fontSize:16,color:S.t3,marginTop:8}}>提報者上傳的缺失照片</div></div>}
</CollapseSection>

{!isNew&&(<>
<CollapseSection title="改善說明（你來填）" defaultOpen={true}><textarea value={improvement} onChange={e=>setImprovement(e.target.value)} placeholder="描述你做了什麼改善..." style={{width:"100%",minHeight:100,padding:14,borderRadius:10,border:`1px solid ${S.bdr}`,background:S.bg0,color:S.t1,fontSize:17,fontFamily:"inherit",resize:"vertical"}}/></CollapseSection>
<CollapseSection title="矯正措施" defaultOpen={true}><textarea value={corrective} onChange={e=>setCorrective(e.target.value)} placeholder="針對缺失的改善行動..." style={{width:"100%",minHeight:90,padding:14,borderRadius:10,border:`1px solid ${S.bdr}`,background:S.bg0,color:S.t1,fontSize:17,fontFamily:"inherit",resize:"vertical"}}/></CollapseSection>
<CollapseSection title="預防措施" defaultOpen={false}><textarea value={preventive} onChange={e=>setPreventive(e.target.value)} placeholder="避免再次發生的措施..." style={{width:"100%",minHeight:90,padding:14,borderRadius:10,border:`1px solid ${S.bdr}`,background:S.bg0,color:S.t1,fontSize:17,fontFamily:"inherit",resize:"vertical"}}/></CollapseSection>
{projectType==="reservation"&&(<CollapseSection title="矯正中照片" defaultOpen={false}><PhotoPickerInline label="上傳矯正中照片" color={S.blue}/></CollapseSection>)}
<CollapseSection title="改善後照片（你來拍）" defaultOpen={true}><PhotoPickerInline label="上傳改善後照片" color={S.green}/></CollapseSection>
</>)}

<button onClick={()=>{if(onSubmit)onSubmit(d,isNew);else onBack();}} style={{width:"100%",padding:"20px",borderRadius:14,border:"none",background:`linear-gradient(135deg, ${S.green}, #1a9648)`,color:"#fff",fontSize:20,fontWeight:900,cursor:"pointer",marginTop:16,minHeight:64,boxShadow:"0 4px 20px rgba(34,179,87,0.2)"}}>{isNew?"提報缺失":"提交改善結果"}</button>
</div>);}

// ============================================================
// LOG LIST PAGE
// ============================================================
function LogListPage({onEdit,logDays,defects,inspections}){
const days=logDays||LD;
const stC={filled:S.green,empty:S.t3,today:S.amber,off:S.bg3};
return(<div style={{padding:"16px 14px",paddingBottom:S.navH+24}}>
<div style={{background:"rgba(59,141,224,0.06)",borderRadius:14,border:"1px solid rgba(59,141,224,0.15)",padding:16,marginBottom:14}}>
<div style={{fontSize:16,fontWeight:700,color:S.blue,marginBottom:6}}>📋 本週施工目標</div>
<div style={{fontSize:16,color:S.t1,lineHeight:1.6}}>{WP.dailyTarget}</div>
<div style={{display:"flex",gap:12,marginTop:10}}><div style={{fontSize:15,color:S.t2}}>預定 <span style={{fontWeight:700,color:S.blue}}>{WP.planned}%</span></div><div style={{fontSize:15,color:S.t2}}>目前 <span style={{fontWeight:700,color:WP.actual>=WP.planned?S.green:S.amber}}>{WP.actual}%</span></div></div></div>
{(defects||[]).filter(d=>d.state==="open").length>0&&(<div style={{background:"rgba(232,54,79,0.06)",borderRadius:14,border:"1px solid rgba(255,77,106,0.2)",padding:16,marginBottom:14}}><div style={{fontSize:16,fontWeight:700,color:S.red,marginBottom:8}}>⚠ 待處理缺失 {(defects||[]).filter(d=>d.state==="open").length} 件</div>{(defects||[]).filter(d=>d.state==="open").map(d=>(<div key={d.id} style={{fontSize:16,color:S.t1,padding:"8px 0",borderBottom:`1px solid ${S.bdr}`}}>{d.name} {d.desc} — {d.isOverdue?`逾期${d.overdueDays}天`:`期限${d.deadline}`}</div>))}</div>)}
{(inspections||[]).filter(i=>i.state==="draft").length>0&&(<div style={{background:"rgba(230,160,32,0.06)",borderRadius:14,border:"1px solid rgba(230,160,32,0.15)",padding:16,marginBottom:14}}><div style={{fontSize:16,fontWeight:700,color:S.amber,marginBottom:8}}>🔍 待完成檢查 {(inspections||[]).filter(i=>i.state==="draft").length} 件</div>{(inspections||[]).filter(i=>i.state==="draft").map(i=>(<div key={i.id} style={{fontSize:16,color:S.t1,padding:"8px 0"}}>{i.type} — {i.location}</div>))}</div>)}
<Sec title="本週施工日誌"/>
<div style={{fontSize:16,color:S.t2,marginBottom:14,textAlign:"center"}}>2026/03/10 — 03/16</div>
{days.map((day,i)=>(<div key={i} onClick={()=>day.status!=="off"&&onEdit(day.date)} style={{background:S.bg2,borderRadius:14,border:`1px solid ${day.status==="today"?S.amber:S.bdr}`,padding:"16px",marginBottom:8,cursor:day.status==="off"?"default":"pointer",opacity:day.status==="off"?0.4:1,borderLeft:`4px solid ${stC[day.status]}`}}>
<div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}><div style={{display:"flex",alignItems:"center",gap:12}}><div style={{fontSize:18,fontWeight:700}}>{day.date}</div><div style={{fontSize:16,color:S.t2}}>({day.weekday})</div></div>
{day.status==="filled"&&<span style={{fontSize:14,fontWeight:700,padding:"3px 10px",borderRadius:6,background:"rgba(34,179,87,0.1)",color:S.green}}>✓ 已填 · {day.weather}</span>}
{day.status==="empty"&&<span style={{fontSize:14,fontWeight:700,padding:"3px 10px",borderRadius:6,background:"rgba(230,160,32,0.12)",color:S.amber}}>待填寫</span>}
{day.status==="today"&&<span style={{fontSize:14,fontWeight:700,padding:"3px 10px",borderRadius:6,background:"rgba(230,160,32,0.12)",color:S.amber}}>今天</span>}
{day.status==="off"&&<span style={{fontSize:15,color:S.t3}}>休息日</span>}
</div></div>))}
</div>);}

// ============================================================
// LOG FORM PAGE
// ============================================================
function LogFormPage({onBack,onSave,defects,inspections}){
const[weatherAm,setWeatherAm]=useState("");const[weatherPm,setWeatherPm]=useState("");
const[workItems,setWorkItems]=useState([{selected:"",customMode:false,customName:""}]);
const[summary,setSummary]=useState("");
const addWorkItem=()=>setWorkItems(p=>[...p,{selected:"",customMode:false,customName:""}]);
return(<div style={{padding:"16px 14px",paddingBottom:120}}>
<div style={{textAlign:"center",marginBottom:14}}><div style={{fontSize:28,fontWeight:900,color:S.amber}}>03/15 (六)</div><div style={{fontSize:16,color:S.t2,marginTop:6}}>施工日誌</div></div>
<div style={{background:"rgba(59,141,224,0.06)",borderRadius:14,border:"1px solid rgba(59,141,224,0.15)",padding:16,marginBottom:14}}><div style={{fontSize:16,fontWeight:700,color:S.blue,marginBottom:6}}>📋 本週施工目標</div><div style={{fontSize:16,color:S.t1,lineHeight:1.6}}>{WP.dailyTarget}</div><div style={{display:"flex",gap:12,marginTop:10}}><div style={{fontSize:15,color:S.t2}}>預定進度 <span style={{fontWeight:700,color:S.blue}}>{WP.planned}%</span></div><div style={{fontSize:15,color:S.t2}}>目前 <span style={{fontWeight:700,color:WP.actual>=WP.planned?S.green:S.amber}}>{WP.actual}%</span></div></div></div>
{(defects||[]).filter(d=>d.state==="open").length>0&&(<div style={{background:"rgba(232,54,79,0.06)",borderRadius:14,border:"1px solid rgba(255,77,106,0.2)",padding:16,marginBottom:14}}><div style={{fontSize:16,fontWeight:700,color:S.red,marginBottom:8}}>⚠ 待處理缺失</div>{(defects||[]).filter(d=>d.state==="open").map(d=>(<div key={d.id} style={{fontSize:16,color:S.t1,padding:"8px 0",borderBottom:`1px solid ${S.bdr}`}}>{d.name} {d.desc} — {d.isOverdue?`逾期${d.overdueDays}天`:`期限${d.deadline}`}</div>))}</div>)}
{(inspections||[]).filter(i=>i.state==="draft").length>0&&(<div style={{background:"rgba(230,160,32,0.06)",borderRadius:14,border:"1px solid rgba(230,160,32,0.15)",padding:16,marginBottom:14}}><div style={{fontSize:16,fontWeight:700,color:S.amber,marginBottom:8}}>🔍 待完成檢查</div>{(inspections||[]).filter(i=>i.state==="draft").map(i=>(<div key={i.id} style={{fontSize:16,color:S.t1,padding:"8px 0"}}>{i.type} — {i.location}</div>))}</div>)}

<div style={{background:S.bg2,borderRadius:14,border:`1px solid ${S.bdr}`,padding:16,marginBottom:12}}>
<div style={{fontSize:20,fontWeight:700,marginBottom:14}}>天氣紀錄</div>
{["上午天氣","下午天氣"].map((label,idx)=>(<div key={idx} style={{marginBottom:idx===0?12:0}}><div style={{fontSize:16,fontWeight:600,color:S.t2,marginBottom:8}}>{label}</div>
<select value={idx===0?weatherAm:weatherPm} onChange={(e)=>idx===0?setWeatherAm(e.target.value):setWeatherPm(e.target.value)} style={{width:"100%",padding:14,borderRadius:10,border:`1px solid ${S.bdr}`,background:S.bg3,color:S.t1,fontSize:17,minHeight:52,appearance:"auto"}}><option value="">請選擇天氣</option>{WO.map(w=>(<option key={w.val} value={w.val}>{w.icon} {w.label}</option>))}</select></div>))}
</div>

<CollapseSection title="施工項目" defaultOpen={true} badge={`${workItems.length} 項`}>
{workItems.map((wi,i)=>(<div key={i} style={{background:S.bg3,borderRadius:12,padding:14,marginBottom:8}}>
<div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:10}}>
<span style={{fontSize:17,fontWeight:700,color:S.amber}}>項目 {i+1}</span>
{workItems.length>1&&<button onClick={()=>setWorkItems(p=>p.filter((_,j)=>j!==i))} style={{background:"none",border:"none",color:S.red,fontSize:15,fontWeight:700,cursor:"pointer",padding:"4px 8px"}}>刪除</button>}
</div>
<div style={{marginBottom:12}}>
<div style={{fontSize:17,fontWeight:600,color:S.t2,marginBottom:8}}>工項名稱</div>
{wi.customMode?(<div style={{display:"flex",gap:8}}>
<input value={wi.customName||""} onChange={e=>{const v=e.target.value;setWorkItems(p=>p.map((w,j)=>j===i?{...w,customName:v}:w));}} placeholder="輸入工項名稱" style={{flex:1,padding:14,borderRadius:10,border:`1px solid ${S.bdr}`,background:S.bg0,color:S.t1,fontSize:17,minHeight:52}}/>
<button onClick={()=>setWorkItems(p=>p.map((w,j)=>j===i?{...w,customMode:false,customName:""}:w))} style={{padding:"0 14px",borderRadius:10,border:`1px solid ${S.bdr}`,background:S.bg3,color:S.t2,fontSize:16,cursor:"pointer",minHeight:52}}>選單</button>
</div>):(<select value={wi.selected||""} onChange={e=>{const v=e.target.value;if(v==="custom"){setWorkItems(p=>p.map((w,j)=>j===i?{...w,customMode:true,selected:""}:w));}else{setWorkItems(p=>p.map((w,j)=>j===i?{...w,selected:v}:w));}}} style={{width:"100%",padding:14,borderRadius:10,border:`1px solid ${S.bdr}`,background:S.bg0,color:S.t1,fontSize:17,minHeight:52,appearance:"auto"}}>
<option value="" disabled>選擇或新增工項</option>
<option value="pipe">排水管線埋設</option>
<option value="manhole">人孔蓋安裝</option>
<option value="backfill">回填作業</option>
<option value="pavement">路面修復</option>
<option value="excavation">開挖工程</option>
<option value="rebar">鋼筋綁紮</option>
<option value="concrete">混凝土澆置</option>
<option value="formwork">模板工程</option>
<option value="custom">＋ 自行輸入工項</option>
</select>)}
</div>
<div style={{display:"flex",gap:8}}>
<div style={{flex:1}}><FormField label="今日數量" placeholder="0" type="number"/></div>
<div style={{flex:1}}><FormField label="單位" placeholder="M"/></div>
<div style={{flex:1}}><FormField label="施作位置" placeholder="K0+150"/></div>
</div>
<FormField label="施工說明" placeholder="簡述今日該工項施作內容" multiline/>
</div>))}
<button onClick={addWorkItem} style={{width:"100%",padding:"14px",borderRadius:12,border:`2px dashed ${S.bdr}`,background:"transparent",color:S.amber,fontSize:17,fontWeight:700,cursor:"pointer",minHeight:52}}>+ 新增施工項目</button>
</CollapseSection>

<CollapseSection title="工作摘要" defaultOpen={true}><textarea value={summary} onChange={e=>setSummary(e.target.value)} placeholder="今日施工重點摘要..." style={{width:"100%",minHeight:100,padding:14,borderRadius:10,border:`1px solid ${S.bdr}`,background:S.bg0,color:S.t1,fontSize:17,fontFamily:"inherit",resize:"vertical"}}/></CollapseSection>
<CollapseSection title="安全衛生檢查" defaultOpen={false}><YesNoField label="實施勤前教育"/><YesNoField label="確認新進勞工保險及訓練紀錄"/><YesNoField label="檢查勞工個人防護具"/><YesNoField label="施工項目是否需設置技術士"/><div style={{marginTop:12}}><div style={{fontSize:17,fontWeight:600,color:S.t2,marginBottom:8}}>安全衛生其他事項</div><textarea placeholder="其他安全衛生相關事項..." style={{width:"100%",minHeight:80,padding:14,borderRadius:10,border:`1px solid ${S.bdr}`,background:S.bg0,color:S.t1,fontSize:17,fontFamily:"inherit",resize:"vertical"}}/></div></CollapseSection>
<CollapseSection title="其他紀錄" defaultOpen={false}><FormField label="抽查試驗紀錄" placeholder="今日抽查項目..." multiline/><FormField label="分包商通知事項" placeholder="需要通知分包商的事項..." multiline/><FormField label="重要事項" placeholder="其他需要記錄的重要事項..." multiline/></CollapseSection>
<CollapseSection title="附件照片" defaultOpen={false}><PhotoPickerInline label="上傳施工照片"/></CollapseSection>

<button onClick={()=>{if(onSave)onSave("03/15");else onBack();}} style={{width:"100%",padding:"20px",borderRadius:14,border:"none",background:`linear-gradient(135deg, ${S.amber}, #cc8a10)`,color:"#fff",fontSize:20,fontWeight:900,cursor:"pointer",marginTop:16,minHeight:64,boxShadow:"0 4px 20px rgba(230,160,32,0.2)"}}>儲存日誌</button>
</div>);}

// ============================================================
// INFO PAGE
// ============================================================
function InfoPage({project}){const p=project||PI;const Row=({label,val,accent})=>(<div style={{display:"flex",justifyContent:"space-between",padding:"16px 0",borderBottom:`1px solid ${S.bdr}`,alignItems:"flex-start"}}><span style={{fontSize:16,color:S.t2,flexShrink:0,fontWeight:600}}>{label}</span><span style={{fontSize:16,fontWeight:accent?700:600,color:accent||S.t1,textAlign:"right",maxWidth:"55%",wordBreak:"break-all",lineHeight:1.4}}>{val}</span></div>);return(<div style={{padding:"16px 14px",paddingBottom:S.navH+24}}><div style={{display:"inline-block",padding:"6px 14px",borderRadius:8,background:"rgba(34,179,87,0.1)",color:S.green,fontSize:16,fontWeight:700,marginBottom:18}}>{({draft:"未開始",construction:"施工中",completion:"已竣工",acceptance:"驗收中",closed:"已結案",suspended:"停工",terminated:"終止"})[p.state]||p.state}</div><SectionLabel text="基本資訊"/><div style={{background:S.bg2,borderRadius:14,padding:"4px 16px",border:`1px solid ${S.bdr}`,marginBottom:18}}><Row label="工程名稱" val={p.name}/><Row label="工程編號" val={p.code}/><Row label="工程地點" val={p.location}/><Row label="工程類別" val={p.projectType==="general"?"一般式工程":"預約式工程"}/><Row label="契約金額" val={p.contractAmount} accent={S.amber}/></div><SectionLabel text="工期資訊"/><div style={{background:S.bg2,borderRadius:14,padding:"4px 16px",border:`1px solid ${S.bdr}`,marginBottom:18}}><Row label="契約開工日" val={p.contractStartDate}/><Row label="契約完工日" val={p.contractEndDate}/><Row label="契約工期" val={p.contractDuration+" 天"}/><Row label="已施工" val={p.actualDuration+" 天"} accent={S.blue}/><Row label="剩餘工期" val={(p.totalApprovedDuration-p.actualDuration)+" 天"} accent={(p.totalApprovedDuration-p.actualDuration)<90?S.amber:S.green}/></div><div style={{background:S.bg2,borderRadius:14,padding:16,border:`1px solid ${S.bdr}`,marginBottom:18}}><div style={{display:"flex",justifyContent:"space-between",marginBottom:10}}><span style={{fontSize:16,color:S.t2,fontWeight:500}}>工期進度</span><span style={{fontSize:20,fontWeight:700,color:S.amber}}>{p.totalApprovedDuration?Math.round(p.actualDuration/p.totalApprovedDuration*100):0}%</span></div><div style={{height:12,background:S.bg0,borderRadius:6,overflow:"hidden"}}><div style={{width:`${p.totalApprovedDuration?Math.round(p.actualDuration/p.totalApprovedDuration*100):0}%`,height:"100%",background:`linear-gradient(90deg, ${S.amber}, #f0b830)`,borderRadius:6}}/></div><div style={{display:"flex",justifyContent:"space-between",marginTop:8,fontSize:15,color:S.t3}}><span>{p.contractStartDate}</span><span>{p.contractEndDate}</span></div></div><SectionLabel text="相關單位"/><div style={{background:S.bg2,borderRadius:14,padding:"4px 16px",border:`1px solid ${S.bdr}`,marginBottom:18}}><Row label="業主機關" val={p.authority}/><Row label="監造單位" val={p.company}/><Row label="承包廠商" val={p.contractors?p.contractors.join("、"):""}/></div><SectionLabel text="工地人員"/><div style={{background:S.bg2,borderRadius:14,padding:"4px 16px",border:`1px solid ${S.bdr}`}}><Row label="監造工程師" val={p.supervisionEngineer}/><Row label="工地主任" val={p.siteManager}/></div></div>);}

// ============================================================
// PHOTO LIST PAGE
// ============================================================
function PhotoListPage({onUpload,onDetail}){
const[viewMode,setViewMode]=useState("photos");
const[showFilter,setShowFilter]=useState(false);
const[filterCat,setFilterCat]=useState("all");
const[filterSrc,setFilterSrc]=useState("all");
const[filterDate,setFilterDate]=useState("");
const[uploadGroups,setUploadGroups]=useState([]);
const[showUpload,setShowUpload]=useState(false);
const filtered=PHOTOS_MOCK.filter(p=>(filterCat==="all"||p.cat===filterCat)&&(filterSrc==="all"||p.src===filterSrc)&&(!filterDate||p.date===filterDate));
const grouped={};filtered.forEach(p=>{if(!grouped[p.date])grouped[p.date]=[];grouped[p.date].push(p);});
const sortedDates=Object.keys(grouped).sort((a,b)=>b.localeCompare(a));
const addGroup=()=>setUploadGroups(p=>[...p,{id:Date.now(),project:"",cat:"",phase:"",desc:"",files:[]}]);
const removeGroup=(gid)=>setUploadGroups(p=>p.filter(g=>g.id!==gid));
const updateGroup=(gid,field,val)=>setUploadGroups(p=>p.map(g=>g.id===gid?{...g,[field]:val}:g));
return(<div style={{padding:"16px 14px",paddingBottom:S.navH+80,position:"relative"}}>
<Sec title="照片中心"/>
{viewMode==="photos"?(<>
{sortedDates.map(date=>(<div key={date} style={{marginBottom:18}}>
<div style={{fontSize:16,fontWeight:700,color:S.t2,marginBottom:8}}>2026/{date} ({grouped[date].length}張)</div>
<div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:10}}>
{grouped[date].map(p=>{const catL={STL:"鋼筋",CON:"混凝土",FRM:"模板",PIP:"管線",ELC:"電氣",DEF:"缺失",EXC:"開挖",BKF:"回填",PAV:"鋪面",DRN:"排水",OTH:"其他"};return(
<div key={p.id} onClick={()=>onDetail(p)} style={{background:S.bg2,borderRadius:14,border:`1px solid ${S.bdr}`,overflow:"hidden",cursor:"pointer"}}>
<div style={{width:"100%",height:120,background:S.bg3,display:"flex",alignItems:"center",justifyContent:"center",fontSize:40}}>🖼</div>
<div style={{padding:"10px 12px"}}><div style={{fontSize:16,fontWeight:700,color:S.t1,marginBottom:4,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{p.name}</div><div style={{fontSize:15,color:S.t3}}>📍 {p.loc}</div></div>
</div>);})}
</div></div>))}
{sortedDates.length===0&&<div style={{textAlign:"center",padding:"40px 0",color:S.t3,fontSize:16}}>沒有符合條件的照片</div>}
</>):(
<div style={{background:S.bg2,borderRadius:14,border:`1px solid ${S.bdr}`,height:400,display:"flex",alignItems:"center",justifyContent:"center",flexDirection:"column",gap:12}}>
<div style={{fontSize:56}}>🗺</div><div style={{fontSize:18,fontWeight:700,color:S.t2}}>地圖檢視</div><div style={{fontSize:16,color:S.t3}}>接入 OpenStreetMap + Leaflet.js</div>
</div>)}

{/* Filter FAB - left */}
<div style={{position:"fixed",bottom:S.navH+14,left:16,zIndex:200}}>
<button onClick={()=>setShowFilter(!showFilter)} style={{width:64,height:64,borderRadius:16,background:showFilter||filterCat!=="all"||filterSrc!=="all"||filterDate?S.blue:"rgba(59,141,224,0.15)",border:`1px solid ${S.blue}`,display:"flex",alignItems:"center",justifyContent:"center",fontSize:28,cursor:"pointer",boxShadow:"0 4px 12px rgba(59,141,224,0.25)",color:showFilter||filterCat!=="all"||filterSrc!=="all"||filterDate?"#000":S.blue}}>🔍</button></div>

{/* Filter panel */}
{showFilter&&(<div style={{position:"fixed",bottom:S.navH+86,left:16,width:280,background:S.bg2,borderRadius:14,border:`1px solid ${S.bdr}`,padding:16,zIndex:200,boxShadow:"0 8px 32px rgba(0,0,0,0.1)"}}>
<div style={{fontSize:17,fontWeight:700,marginBottom:12}}>篩選條件</div>
<div style={{marginBottom:12}}><div style={{fontSize:16,color:S.t2,marginBottom:6}}>來源分類</div><select value={filterSrc} onChange={e=>setFilterSrc(e.target.value)} style={{width:"100%",padding:12,borderRadius:10,border:`1px solid ${S.bdr}`,background:S.bg3,color:S.t1,fontSize:16,minHeight:48,appearance:"auto"}}><option value="all">不篩選</option><option value="daily_log">施工日誌</option><option value="inspection">自主檢查</option><option value="defect">缺失改善</option><option value="other">每日照片</option></select></div>
<div style={{marginBottom:12}}><div style={{fontSize:16,color:S.t2,marginBottom:6}}>材料分類</div><select value={filterCat} onChange={e=>setFilterCat(e.target.value)} style={{width:"100%",padding:12,borderRadius:10,border:`1px solid ${S.bdr}`,background:S.bg3,color:S.t1,fontSize:16,minHeight:48,appearance:"auto"}}><option value="all">全部</option>{CAT_OPTS.map(c=>(<option key={c.v} value={c.v}>{c.l}</option>))}</select></div>
<div style={{marginBottom:14}}><div style={{fontSize:16,color:S.t2,marginBottom:6}}>拍攝日期</div><input type="date" value={filterDate} onChange={e=>setFilterDate(e.target.value)} style={{width:"100%",padding:12,borderRadius:10,border:`1px solid ${S.bdr}`,background:S.bg3,color:S.t1,fontSize:16,minHeight:48}}/></div>
<div style={{display:"flex",gap:8}}><button onClick={()=>{setFilterCat("all");setFilterSrc("all");setFilterDate("");}} style={{flex:1,padding:"12px",borderRadius:10,border:`1px solid ${S.bdr}`,background:"transparent",color:S.t2,fontSize:15,fontWeight:700,cursor:"pointer",minHeight:44}}>清除</button><button onClick={()=>setShowFilter(false)} style={{flex:1,padding:"12px",borderRadius:10,border:"none",background:S.amber,color:"#000",fontSize:15,fontWeight:700,cursor:"pointer",minHeight:44}}>套用</button></div>
</div>)}

{/* Floating segment control - center */}
<div style={{position:"fixed",bottom:S.navH+14,left:"50%",transform:"translateX(-50%)",zIndex:150,display:"flex",background:"rgba(255,255,255,0.95)",backdropFilter:"blur(12px)",borderRadius:12,border:`1px solid ${S.bdr}`,padding:3}}>
<button onClick={()=>setViewMode("photos")} style={{padding:"10px 18px",borderRadius:10,border:"none",fontSize:15,fontWeight:700,cursor:"pointer",minHeight:44,background:viewMode==="photos"?S.amber:"transparent",color:viewMode==="photos"?"#fff":S.t3}}>所有照片</button>
<button onClick={()=>setViewMode("map")} style={{padding:"10px 18px",borderRadius:10,border:"none",fontSize:15,fontWeight:700,cursor:"pointer",minHeight:44,background:viewMode==="map"?S.amber:"transparent",color:viewMode==="map"?"#fff":S.t3}}>地圖</button></div>

{/* Upload FAB - right */}
<div style={{position:"fixed",bottom:S.navH+14,right:16,zIndex:200}}>
<button onClick={()=>{if(!showUpload)addGroup();setShowUpload(!showUpload);}} style={{width:64,height:64,borderRadius:16,background:`linear-gradient(135deg, ${S.amber}, #cc8a10)`,border:"none",display:"flex",alignItems:"center",justifyContent:"center",fontSize:28,cursor:"pointer",boxShadow:"0 4px 24px rgba(230,160,32,0.25)",color:"#000"}}>{showUpload?"✕":"📷"}</button></div>

{/* Upload panel */}
{showUpload&&(<div style={{position:"fixed",bottom:S.navH+86,left:16,right:16,maxHeight:"60vh",overflowY:"auto",background:S.bg2,borderRadius:14,border:`1px solid ${S.bdr}`,padding:16,zIndex:200,boxShadow:"0 8px 32px rgba(0,0,0,0.1)"}}>
<div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:14}}><div style={{fontSize:18,fontWeight:700}}>批次上傳照片</div><button onClick={addGroup} style={{padding:"8px 14px",borderRadius:8,border:`1px solid ${S.amber}`,background:"transparent",color:S.amber,fontSize:15,fontWeight:600,cursor:"pointer",minHeight:44}}>+ 新增群組</button></div>
{uploadGroups.map((g,gi)=>(<div key={g.id} style={{background:S.bg3,borderRadius:12,padding:14,marginBottom:10,position:"relative"}}>
<div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:10}}><div style={{fontSize:16,fontWeight:700,color:S.amber}}>群組 {gi+1}</div>{uploadGroups.length>1&&<button onClick={()=>removeGroup(g.id)} style={{background:"none",border:"none",color:S.red,fontSize:14,fontWeight:700,cursor:"pointer"}}>刪除</button>}</div>
<div style={{marginBottom:10}}><div style={{fontSize:14,color:S.t2,marginBottom:4}}>所屬工程</div><select value={g.project||""} onChange={e=>updateGroup(g.id,"project",e.target.value)} style={{width:"100%",padding:8,borderRadius:8,border:`1px solid ${S.bdr}`,background:S.bg0,color:S.t1,fontSize:15,minHeight:44,appearance:"auto"}}><option value="">目前工程</option><option value="proj1">通河東街排水改善工程</option><option value="proj2">信義路排水改善工程</option></select></div>
<div style={{marginBottom:10}}><div style={{fontSize:14,color:S.t2,marginBottom:4}}>照片說明</div><input placeholder="描述這組照片..." value={g.desc} onChange={e=>updateGroup(g.id,"desc",e.target.value)} style={{width:"100%",padding:10,borderRadius:8,border:`1px solid ${S.bdr}`,background:S.bg0,color:S.t1,fontSize:15,minHeight:44}}/></div>
<div style={{display:"flex",gap:8,marginBottom:10}}><div style={{flex:1}}><div style={{fontSize:14,color:S.t2,marginBottom:4}}>分類</div><select value={g.cat} onChange={e=>updateGroup(g.id,"cat",e.target.value)} style={{width:"100%",padding:8,borderRadius:8,border:`1px solid ${S.bdr}`,background:S.bg0,color:S.t1,fontSize:15,minHeight:44,appearance:"auto"}}><option value="">選擇</option>{CAT_OPTS.map(c=>(<option key={c.v} value={c.v}>{c.l}</option>))}</select></div><div style={{flex:1}}><div style={{fontSize:14,color:S.t2,marginBottom:4}}>階段</div><select value={g.phase} onChange={e=>updateGroup(g.id,"phase",e.target.value)} style={{width:"100%",padding:8,borderRadius:8,border:`1px solid ${S.bdr}`,background:S.bg0,color:S.t1,fontSize:15,minHeight:44,appearance:"auto"}}><option value="">選擇</option>{PH_OPTS.map(p=>(<option key={p.v} value={p.v}>{p.l}</option>))}</select></div></div>
<PhotoPickerInline label="選擇照片"/>
</div>))}
<button onClick={()=>{alert(`已上傳 ${uploadGroups.length} 組照片`);setUploadGroups([]);setShowUpload(false);}} style={{width:"100%",padding:"16px",borderRadius:12,border:"none",background:`linear-gradient(135deg, ${S.amber}, #cc8a10)`,color:"#fff",fontSize:16,fontWeight:700,cursor:"pointer",minHeight:52,marginTop:6}}>上傳全部 ({uploadGroups.length} 組)</button>
</div>)}
</div>);}

// ============================================================
// PHOTO UPLOAD / DETAIL PAGES
// ============================================================
function PhotoUploadPage({onBack,capturedFile}){const[desc,setDesc]=useState("");const[cat,setCat]=useState("");const[phase,setPhase]=useState("");return(<div style={{padding:"16px 14px",paddingBottom:120}}><div style={{textAlign:"center",marginBottom:16}}><div style={{fontSize:26,fontWeight:900,color:S.amber}}>上傳照片</div></div><PhotoPickerArea/><FormField label="照片說明" placeholder="描述這張照片..." value={desc} onChange={setDesc}/><div style={{marginBottom:14}}><div style={{fontSize:16,fontWeight:600,color:S.t2,marginBottom:8}}>材料分類</div><select value={cat} onChange={e=>setCat(e.target.value)} style={{width:"100%",padding:14,borderRadius:10,border:`1px solid ${S.bdr}`,background:S.bg3,color:S.t1,fontSize:17,minHeight:52,appearance:"auto"}}><option value="">請選擇分類</option>{CAT_OPTS.map(c=>(<option key={c.v} value={c.v}>{c.l}</option>))}</select></div><div><div style={{fontSize:16,fontWeight:600,color:S.t2,marginBottom:8}}>施工階段</div><select value={phase} onChange={e=>setPhase(e.target.value)} style={{width:"100%",padding:14,borderRadius:10,border:`1px solid ${S.bdr}`,background:S.bg3,color:S.t1,fontSize:17,minHeight:52,appearance:"auto"}}><option value="">請選擇階段</option>{PH_OPTS.map(p=>(<option key={p.v} value={p.v}>{p.l}</option>))}</select></div><button onClick={()=>{alert("照片已上傳");onBack();}} style={{width:"100%",padding:"20px",borderRadius:14,border:"none",background:`linear-gradient(135deg, ${S.amber}, #cc8a10)`,color:"#fff",fontSize:20,fontWeight:900,cursor:"pointer",marginTop:20,minHeight:64}}>上傳照片</button></div>);}
function PhotoDetailPage({photo,onBack}){const p=photo||PHOTOS_MOCK[0];const catL={STL:"鋼筋",CON:"混凝土",FRM:"模板",PIP:"管線",ELC:"電氣",DEF:"缺失",EXC:"開挖",BKF:"回填",PAV:"鋪面",DRN:"排水",OTH:"其他"};return(<div style={{padding:"16px 14px",paddingBottom:120}}><div style={{width:"100%",height:260,background:S.bg3,borderRadius:14,display:"flex",alignItems:"center",justifyContent:"center",fontSize:56,marginBottom:16}}>🖼</div><div style={{fontSize:22,fontWeight:700,marginBottom:6}}>{p.name}</div><div style={{background:S.bg2,borderRadius:14,border:`1px solid ${S.bdr}`,padding:"4px 16px",marginBottom:14}}><InfoRow label="拍攝日期" val={`2026/${p.date}`}/><InfoRow label="位置" val={p.loc}/><InfoRow label="分類" val={catL[p.cat]||p.cat}/></div><div style={{display:"flex",gap:10}}><button style={{flex:1,padding:"14px",borderRadius:10,border:`1px solid ${S.bdr}`,background:S.bg2,color:S.t1,fontSize:16,fontWeight:700,cursor:"pointer",minHeight:48}}>下載</button><button style={{flex:1,padding:"14px",borderRadius:10,border:`1px solid rgba(232,54,79,0.2)`,background:"rgba(232,54,79,0.06)",color:S.red,fontSize:16,fontWeight:700,cursor:"pointer",minHeight:48}}>刪除</button></div></div>);}

// ============================================================
// SLIP DETAIL PAGE
// ============================================================
function SlipDetailPage({slip,onBack,inspections,defects,onOpenInsp,onOpenDef}){const sl=slip||SLIPS[0];const stL={draft:"草稿",not_started:"未開始",in_progress:"施工中",closed:"已結案"};const stC={draft:S.t3,not_started:S.amber,in_progress:S.green,closed:S.t3};return(<div style={{padding:"16px 14px",paddingBottom:120}}>
<div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:16}}><div><div style={{fontSize:26,fontWeight:900,color:S.amber}}>{sl.name}</div><div style={{fontSize:16,color:S.t2,marginTop:4}}>📍 {sl.loc}</div></div><div style={{padding:"6px 14px",borderRadius:8,background:`${stC[sl.state]}22`,color:stC[sl.state],fontSize:16,fontWeight:700}}>{stL[sl.state]}</div></div>
<SectionLabel text="基本資訊"/><div style={{background:S.bg2,borderRadius:14,padding:"4px 16px",border:`1px solid ${S.bdr}`,marginBottom:14}}><InfoRow label="通報單次" val={`第 ${sl.no} 次`}/><InfoRow label="工程地點" val={sl.loc}/><InfoRow label="預定開工" val={sl.pStart||"未排定"}/><InfoRow label="預定完工" val={sl.pEnd||"未排定"}/><InfoRow label="預定工期" val={sl.dur?`${sl.dur} 天`:"未排定"}/><InfoRow label="預估金額" val={`NT$ ${sl.amt}`} accent={S.amber}/></div>
<SectionLabel text="工項明細"/><div style={{background:S.bg2,borderRadius:14,border:`1px solid ${S.bdr}`,padding:16,marginBottom:14}}>{[{no:"一",desc:"排水管線埋設",unit:"M",planned_qty:120,actual_qty:45,unit_price:3500},{no:"二",desc:"人孔蓋安裝",unit:"座",planned_qty:8,actual_qty:3,unit_price:45000},{no:"三",desc:"路面修復",unit:"M²",planned_qty:200,actual_qty:0,unit_price:1200}].slice(0,sl.items).map((item,i)=>(<div key={i} style={{padding:"12px 0",borderBottom:i<sl.items-1?`1px solid ${S.bdr}`:"none"}}><div style={{display:"flex",justifyContent:"space-between",marginBottom:4}}><span style={{fontSize:16,fontWeight:600}}>{item.no}、{item.desc}</span><span style={{fontSize:15,color:S.t2}}>{item.unit}</span></div><div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}><div style={{flex:1,height:8,background:S.bg0,borderRadius:4,overflow:"hidden",marginRight:12}}><div style={{width:`${item.planned_qty?(item.actual_qty/item.planned_qty)*100:0}%`,height:"100%",background:item.actual_qty>0?S.green:S.bg3,borderRadius:4}}/></div><span style={{fontSize:15,color:S.t2,whiteSpace:"nowrap"}}>{item.actual_qty}/{item.planned_qty}</span></div></div>))}</div>
<SectionLabel text="自主檢查"/>{(inspections||[]).length>0?<div style={{background:S.bg2,borderRadius:14,border:`1px solid ${S.bdr}`,overflow:"hidden",marginBottom:14}}>{(inspections||[]).slice(0,2).map(i=>{const sC2={draft:S.amber,inspected:S.blue,confirmed:S.green};const sL2={draft:"待檢查",inspected:"已檢查",confirmed:"已確認"};return(<div key={i.id} onClick={()=>onOpenInsp&&onOpenInsp(i)} style={{padding:"16px",borderBottom:`1px solid ${S.bdr}`,cursor:"pointer"}}><div style={{display:"flex",justifyContent:"space-between"}}><span style={{fontSize:16,fontWeight:600}}>{i.type}</span><span style={{fontSize:14,color:sC2[i.state],fontWeight:700}}>{sL2[i.state]}</span></div><div style={{fontSize:16,color:S.t2,marginTop:4}}>{i.location} / {i.date}</div></div>);})}</div>:<div style={{fontSize:15,color:S.t3,marginBottom:14}}>尚無自主檢查紀錄</div>}
<SectionLabel text="缺失改善"/>{(defects||[]).filter(d=>d.state!=="verified"&&d.state!=="closed").length>0?<div style={{background:S.bg2,borderRadius:14,border:`1px solid ${S.bdr}`,overflow:"hidden",marginBottom:14}}>{(defects||[]).filter(d=>d.state!=="verified"&&d.state!=="closed").map(d=>{const sC3={open:S.red,investigating:S.amber,action_taken:S.blue};const sL3={open:"待改善",investigating:"調查中",action_taken:"已採措施"};return(<div key={d.id} onClick={()=>onOpenDef&&onOpenDef(d)} style={{padding:"16px",borderBottom:`1px solid ${S.bdr}`,cursor:"pointer"}}><div style={{display:"flex",justifyContent:"space-between"}}><span style={{fontSize:16,fontWeight:600}}>{d.name} {d.desc}</span><span style={{fontSize:14,color:sC3[d.state],fontWeight:700}}>{sL3[d.state]}</span></div><div style={{fontSize:15,color:d.isOverdue?S.red:S.t2,marginTop:3}}>{d.isOverdue?`逾期${d.overdueDays}天`:`期限${d.deadline}`}</div></div>);})}</div>:<div style={{fontSize:15,color:S.t3,marginBottom:14}}>尚無缺失紀錄</div>}
</div>);}

// ============================================================
// SETTINGS PAGE
// ============================================================
function SettingsPage({onBack,projectType,currentProject,setCurrentProject,setSubPage}){return(<div style={{padding:"16px 14px",paddingBottom:120}}><Sec title="設定"/>
<div style={{background:S.bg2,borderRadius:14,border:`1px solid ${S.bdr}`,overflow:"hidden",marginBottom:16}}>
<div style={{padding:"20px 16px",display:"flex",alignItems:"center",gap:14,borderBottom:`1px solid ${S.bdr}`}}><div style={{width:56,height:56,borderRadius:28,background:"linear-gradient(135deg, #e6a020, #d4880a)",display:"flex",alignItems:"center",justifyContent:"center",fontSize:24,fontWeight:900,color:"#000"}}>阿</div><div><div style={{fontSize:20,fontWeight:700}}>阿明</div><div style={{fontSize:15,color:S.t2}}>現場施工人員</div><div style={{fontSize:15,color:S.t3}}>jerryhuang6305@gmail.com</div></div></div>
<div onClick={()=>setSubPage({type:"projectSwitch"})}><SettingsRow icon="🏗" label="切換工程" val={currentProject.name?.substring(0,12)}/></div>
<SettingsRow icon="📋" label="工程類型" val={projectType==="general"?"一般式工程":"預約式工程"}/>
</div>
<SectionLabel text="專案管理"/><div style={{background:S.bg2,borderRadius:14,border:`1px solid ${S.bdr}`,overflow:"hidden",marginBottom:16}}>
<div onClick={()=>setSubPage({type:"newProject"})}><SettingsRow icon="➕" label="新增專案"/></div>
<div onClick={()=>setSubPage({type:"fileManager"})}><SettingsRow icon="📂" label="檔案管理"/></div>
</div>
<SectionLabel text="系統"/><div style={{background:S.bg2,borderRadius:14,border:`1px solid ${S.bdr}`,overflow:"hidden",marginBottom:16}}>
<SettingsRow icon="🔔" label="通知設定"/><SettingsRow icon="🌙" label="深色模式" val="開啟"/><SettingsRow icon="📱" label="系統版本" val="v10.0"/>
</div>
<SectionLabel text="其他"/><div style={{background:S.bg2,borderRadius:14,border:`1px solid ${S.bdr}`,overflow:"hidden",marginBottom:16}}>
<SettingsRow icon="📖" label="使用說明"/><SettingsRow icon="💬" label="意見回饋"/><SettingsRow icon="ℹ" label="關於"/>
</div>
<button style={{width:"100%",padding:"16px",borderRadius:14,border:`1px solid rgba(232,54,79,0.2)`,background:"rgba(232,54,79,0.06)",color:S.red,fontSize:16,fontWeight:700,cursor:"pointer",minHeight:52}}>登出</button>
</div>);}

// ============================================================
// NEW SLIP PAGE
// ============================================================
function NewSlipPage({onBack,project}){const[loc,setLoc]=useState("");const[locDetail,setLocDetail]=useState("");const[design,setDesign]=useState("");const[startDate,setStartDate]=useState("");const[duration,setDuration]=useState("");const[amount,setAmount]=useState("");const[items,setItems]=useState([{desc:"",unit:"",qty:"",price:""}]);return(<div style={{padding:"16px 14px",paddingBottom:120}}>
<div style={{textAlign:"center",marginBottom:16}}><div style={{fontSize:26,fontWeight:900,color:S.amber}}>新增通報單</div><div style={{fontSize:16,color:S.t2,marginTop:4}}>{project?.name||""}</div></div>
<CollapseSection title="基本資訊" defaultOpen={true}><FormField label="工程地點" placeholder="本次通報施工地點" value={loc} onChange={setLoc}/><button onClick={()=>{if(navigator.geolocation){navigator.geolocation.getCurrentPosition((pos)=>{setLoc(prev=>(prev?prev+" ":"")+`(${pos.coords.latitude.toFixed(6)}, ${pos.coords.longitude.toFixed(6)})`);},{});}}} style={{width:"100%",padding:"14px",borderRadius:10,border:`1px solid ${S.blue}`,background:"rgba(59,141,224,0.06)",color:S.blue,fontSize:16,fontWeight:700,cursor:"pointer",minHeight:48,marginBottom:14,marginTop:-8}}>📍 取得 GPS 位置</button><FormField label="詳細位置說明" placeholder="補充位置資訊" value={locDetail} onChange={setLocDetail} multiline/><FormField label="設計概述" placeholder="本次通報施工內容概述" value={design} onChange={setDesign} multiline/></CollapseSection>
<CollapseSection title="工期資訊" defaultOpen={true}><FormField label="預定開工日期" type="date" value={startDate} onChange={setStartDate}/><FormField label="預定工期(天)" placeholder="天數" type="number" value={duration} onChange={setDuration}/><FormField label="預估金額" placeholder="金額" type="number" value={amount} onChange={setAmount}/></CollapseSection>
<CollapseSection title="工項明細" defaultOpen={true} badge={`${items.length} 項`}>{items.map((_,i)=>(<div key={i} style={{background:S.bg3,borderRadius:12,padding:14,marginBottom:8}}><div style={{fontSize:16,fontWeight:700,color:S.amber,marginBottom:10}}>第 {i+1} 項</div><FormField label="項目說明" placeholder="工項描述"/><div style={{display:"flex",gap:8}}><div style={{flex:1}}><FormField label="單位" placeholder="M"/></div><div style={{flex:1}}><FormField label="數量" type="number"/></div><div style={{flex:1}}><FormField label="單價" type="number"/></div></div></div>))}<button onClick={()=>setItems(p=>[...p,{desc:"",unit:"",qty:"",price:""}])} style={{width:"100%",padding:"14px",borderRadius:12,border:`2px dashed ${S.bdr}`,background:"transparent",color:S.amber,fontSize:16,fontWeight:700,cursor:"pointer",minHeight:52}}>+ 新增工項</button></CollapseSection>
<button onClick={()=>{alert("通報單已建立");onBack();}} style={{width:"100%",padding:"20px",borderRadius:14,border:"none",background:`linear-gradient(135deg, ${S.amber}, #cc8a10)`,color:"#fff",fontSize:20,fontWeight:900,cursor:"pointer",marginTop:16,minHeight:64}}>建立通報單</button>
</div>);}

// ============================================================
// FILE MANAGE PAGE
// ============================================================
function FileManagePage({onBack,project}){const[docs]=useState([{id:1,name:"施工計畫書 v2",cat:"施工計畫",no:"DOC-001",state:"uploaded",date:"2026/03/01",size:"2.4 MB"},{id:2,name:"品質計畫書",cat:"品質管理",no:"DOC-002",state:"uploaded",date:"2026/02/15",size:"1.8 MB"},{id:3,name:"安衛計畫書",cat:"安全衛生",no:"DOC-003",state:"draft",date:"",size:""},{id:4,name:"竣工報告",cat:"竣工文件",no:"DOC-004",state:"draft",date:"",size:""}]);const[showUpload,setShowUpload]=useState(false);const[filterCat,setFilterCat]=useState("all");const cats=[...new Set(docs.map(d=>d.cat))];const filtered=filterCat==="all"?docs:docs.filter(d=>d.cat===filterCat);const stC={draft:S.amber,uploaded:S.green,archived:S.t3};const stL={draft:"待上傳",uploaded:"已上傳",archived:"已封存"};return(<div style={{padding:"16px 14px",paddingBottom:120}}>
<div style={{textAlign:"center",marginBottom:16}}><div style={{fontSize:26,fontWeight:900,color:S.amber}}>檔案管理</div><div style={{fontSize:16,color:S.t2,marginTop:4}}>{project?.name||""}</div></div>
<div style={{marginBottom:14}}><div style={{fontSize:16,color:S.t3,marginBottom:6}}>文件分類</div><select value={filterCat} onChange={e=>setFilterCat(e.target.value)} style={{width:"100%",padding:12,borderRadius:10,border:`1px solid ${S.bdr}`,background:S.bg3,color:S.t1,fontSize:16,minHeight:48,appearance:"auto"}}><option value="all">全部分類</option>{cats.map(c=>(<option key={c} value={c}>{c}</option>))}</select></div>
{filtered.map(d=>(<div key={d.id} style={{background:S.bg2,borderRadius:14,border:`1px solid ${S.bdr}`,padding:"16px",marginBottom:10,borderLeft:`4px solid ${stC[d.state]}`}}><div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:6}}><div><div style={{fontSize:17,fontWeight:700}}>{d.name}</div><div style={{fontSize:16,color:S.t2,marginTop:4}}>{d.no} / {d.cat}</div></div><span style={{fontSize:14,fontWeight:700,padding:"5px 12px",borderRadius:6,background:`${stC[d.state]}22`,color:stC[d.state]}}>{stL[d.state]}</span></div>{d.state==="uploaded"&&<div style={{fontSize:15,color:S.t3}}>{d.date} / {d.size}</div>}{d.state==="draft"&&<label style={{display:"flex",alignItems:"center",justifyContent:"center",gap:6,padding:"12px",borderRadius:10,border:`1px solid ${S.amber}`,background:"rgba(230,160,32,0.06)",color:S.amber,fontSize:15,fontWeight:700,cursor:"pointer",minHeight:44,marginTop:8}}><input type="file" style={{display:"none"}} onChange={()=>alert("檔案已上傳")}/>📎 上傳檔案</label>}</div>))}
<button onClick={()=>setShowUpload(!showUpload)} style={{width:"100%",padding:"16px",borderRadius:14,border:"none",background:`linear-gradient(135deg, ${S.amber}, #cc8a10)`,color:"#fff",fontSize:16,fontWeight:700,cursor:"pointer",marginTop:8,minHeight:56}}>+ 新增文件</button>
{showUpload&&(<div style={{background:S.bg2,borderRadius:14,border:`1px solid ${S.bdr}`,padding:16,marginTop:12}}><FormField label="文件名稱" placeholder="輸入文件名稱"/><div style={{marginBottom:14}}><div style={{fontSize:16,fontWeight:600,color:S.t2,marginBottom:8}}>文件分類</div><select style={{width:"100%",padding:12,borderRadius:10,border:`1px solid ${S.bdr}`,background:S.bg3,color:S.t1,fontSize:16,minHeight:48,appearance:"auto"}}><option value="">選擇分類</option>{cats.map(c=>(<option key={c} value={c}>{c}</option>))}</select></div><FormField label="應上傳日期" type="date"/><FormField label="備註" placeholder="備註說明" multiline/><label style={{display:"flex",alignItems:"center",justifyContent:"center",gap:8,width:"100%",padding:"16px",borderRadius:10,border:`2px dashed ${S.amber}`,background:"rgba(230,160,32,0.06)",color:S.amber,fontSize:16,fontWeight:700,cursor:"pointer",minHeight:52,marginBottom:12}}><input type="file" multiple style={{display:"none"}}/>📎 選擇檔案</label><button onClick={()=>{alert("文件已新增");setShowUpload(false);}} style={{width:"100%",padding:"14px",borderRadius:10,border:"none",background:S.amber,color:"#000",fontSize:16,fontWeight:700,cursor:"pointer",minHeight:48}}>確認新增</button></div>)}
</div>);}

// ============================================================
// NEW PROJECT PAGE
// ============================================================
function NewProjectPage({onBack,onSave}){const[name,setName]=useState("");const[loc,setLoc]=useState("");const[type,setType]=useState("general");const[owner,setOwner]=useState("");const[contractor,setContractor]=useState("");const[startDate,setStartDate]=useState("");const[endDate,setEndDate]=useState("");const[duration,setDuration]=useState("");const[amount,setAmount]=useState("");return(<div style={{padding:"16px 14px",paddingBottom:120}}>
<div style={{textAlign:"center",marginBottom:16}}><div style={{fontSize:26,fontWeight:900,color:S.amber}}>新增工程專案</div><div style={{fontSize:16,color:S.t2,marginTop:4}}>填寫工程基本資料</div></div>
<CollapseSection title="基本資訊" defaultOpen={true}><FormField label="工程名稱" placeholder="輸入工程名稱" value={name} onChange={setName}/><FormField label="工程地點" placeholder="輸入工程地點" value={loc} onChange={setLoc}/><button onClick={()=>{if(navigator.geolocation){navigator.geolocation.getCurrentPosition((pos)=>{setLoc(prev=>(prev?prev+" ":"")+`(${pos.coords.latitude.toFixed(6)}, ${pos.coords.longitude.toFixed(6)})`);alert("GPS 位置已取得");},{});}}} style={{width:"100%",padding:"14px",borderRadius:10,border:`1px solid ${S.blue}`,background:"rgba(59,141,224,0.06)",color:S.blue,fontSize:16,fontWeight:700,cursor:"pointer",minHeight:48,marginBottom:14,marginTop:-8}}>📍 取得目前 GPS 位置</button><div style={{marginBottom:14}}><div style={{fontSize:16,fontWeight:600,color:S.t2,marginBottom:8}}>工程類型</div><select value={type} onChange={e=>setType(e.target.value)} style={{width:"100%",padding:14,borderRadius:10,border:`1px solid ${S.bdr}`,background:S.bg3,color:S.t1,fontSize:17,minHeight:52,appearance:"auto"}}><option value="general">一般式工程</option><option value="reservation">預約式工程</option></select></div></CollapseSection>
<CollapseSection title="相關單位" defaultOpen={true}><FormField label="業主機關" placeholder="輸入業主機關名稱" value={owner} onChange={setOwner}/><FormField label="承包廠商" placeholder="輸入承包廠商名稱" value={contractor} onChange={setContractor}/></CollapseSection>
<CollapseSection title="工期資訊" defaultOpen={true}><FormField label="開工日期" type="date" value={startDate} onChange={setStartDate}/><FormField label="預定竣工" type="date" value={endDate} onChange={setEndDate}/><FormField label="契約工期(天)" type="number" value={duration} onChange={setDuration}/><FormField label="契約金額" type="number" value={amount} onChange={setAmount}/></CollapseSection>
<button onClick={()=>{if(!name){alert("請輸入工程名稱");return;}onSave({name,location:loc,projectType:type,contractAmount:`NT$ ${Number(amount||0).toLocaleString()}`,contractStartDate:startDate,contractEndDate:endDate,contractDuration:parseInt(duration)||0,actualDuration:0,totalApprovedDuration:parseInt(duration)||0,owner,contractor,company:"千溢科技有限公司",contractors:[contractor],supervisionEngineer:"",state:"draft"});}} style={{width:"100%",padding:"20px",borderRadius:14,border:"none",background:`linear-gradient(135deg, ${S.amber}, #cc8a10)`,color:"#fff",fontSize:20,fontWeight:900,cursor:"pointer",marginTop:16,minHeight:64}}>建立工程</button>
</div>);}

// ============================================================
// PROJECT SWITCH PAGE
// ============================================================
function ProjectSwitchPage({projects,current,onSelect,onBack}){return(<div style={{padding:"16px 14px",paddingBottom:120}}><Sec title="切換工程"/><div style={{fontSize:16,color:S.t2,marginBottom:14}}>選擇要查看的工程案件</div>{projects.map(p=>(<div key={p.id} onClick={()=>onSelect(p)} style={{background:S.bg2,borderRadius:14,border:`1px solid ${current===p.data?"rgba(245,183,64,0.5)":S.bdr}`,padding:"18px 16px",marginBottom:12,cursor:"pointer",borderLeft:`4px solid ${current===p.data?S.amber:S.bdr}`}}><div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}><div><div style={{fontSize:17,fontWeight:700,color:current===p.data?S.amber:S.t1}}>{p.label}</div><div style={{display:"flex",gap:8,marginTop:6}}><span style={{fontSize:14,fontWeight:700,padding:"5px 12px",borderRadius:6,background:p.type==="general"?"rgba(34,179,87,0.1)":"rgba(230,160,32,0.12)",color:p.type==="general"?S.green:S.amber}}>{p.type==="general"?"一般式":"預約式"}</span><span style={{fontSize:14,fontWeight:600,padding:"4px 10px",borderRadius:6,background:S.bg3,color:S.t2}}>{({draft:"未開始",construction:"施工中",completion:"已竣工",acceptance:"驗收中",closed:"已結案",suspended:"停工",terminated:"終止"})[p.data?.state]||""}</span></div></div>{current===p.data&&<div style={{fontSize:20,color:S.amber}}>✓</div>}</div></div>))}</div>);}

// ============================================================
// SHARED COMPONENTS
// ============================================================
function Sec({title}){return(<div style={{display:"flex",alignItems:"center",gap:10,margin:"18px 0 12px"}}><div style={{height:2,flex:1,background:`linear-gradient(90deg, ${S.amber}, transparent)`}}/><span style={{fontSize:16,fontWeight:700,color:S.t3,letterSpacing:2,whiteSpace:"nowrap"}}>{title}</span><div style={{height:2,flex:1,background:`linear-gradient(270deg, ${S.amber}, transparent)`}}/></div>);}
function SectionLabel({text}){return(<div style={{fontSize:16,fontWeight:700,color:S.t3,letterSpacing:2,marginBottom:8,marginTop:16}}>{text}</div>);}
function InfoRow({label,val,accent}){return(<div style={{display:"flex",justifyContent:"space-between",padding:"16px 0",borderBottom:`1px solid ${S.bdr}`,alignItems:"flex-start"}}><span style={{fontSize:16,color:S.t2,flexShrink:0,fontWeight:600}}>{label}</span><span style={{fontSize:16,fontWeight:accent?700:600,color:accent||S.t1,textAlign:"right",maxWidth:"55%",wordBreak:"break-all",lineHeight:1.4}}>{val}</span></div>);}
function CollapseSection({title,children,defaultOpen=true,badge}){const[open,setOpen]=useState(defaultOpen);return(<div style={{background:S.bg2,borderRadius:14,border:`1px solid ${S.bdr}`,marginBottom:12,overflow:"hidden"}}><div onClick={()=>setOpen(!open)} style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"14px 16px",cursor:"pointer",minHeight:52}}><div style={{display:"flex",alignItems:"center",gap:8}}><span style={{fontSize:19,fontWeight:700,color:S.t1}}>{title}</span>{badge&&<span style={{fontSize:14,padding:"3px 10px",borderRadius:6,background:S.bg3,color:S.t3}}>{badge}</span>}</div><span style={{fontSize:16,color:S.t3,transition:"transform 0.2s",transform:open?"rotate(180deg)":"rotate(0)"}}></span></div>{open&&<div style={{padding:"0 16px 16px"}}>{children}</div>}</div>);}
function FormField({label,placeholder,value,onChange,multiline,type}){return(<div style={{marginBottom:14}}><div style={{fontSize:16,fontWeight:600,color:S.t2,marginBottom:8}}>{label}</div>{multiline?<textarea value={value} onChange={onChange?e=>onChange(e.target.value):undefined} placeholder={placeholder} style={{width:"100%",minHeight:80,padding:14,borderRadius:10,border:`1px solid ${S.bdr}`,background:S.bg0,color:S.t1,fontSize:17,fontFamily:"inherit",resize:"vertical"}}/>:<input type={type||"text"} value={value} onChange={onChange?e=>onChange(e.target.value):undefined} placeholder={placeholder} style={{width:"100%",padding:14,borderRadius:10,border:`1px solid ${S.bdr}`,background:S.bg0,color:S.t1,fontSize:17,minHeight:52}}/>}</div>);}
function YesNoField({label}){const[val,setVal]=useState(null);return(<div style={{display:"flex",alignItems:"center",gap:12,padding:"10px 0",borderBottom:`1px solid ${S.bdr}`}}><span style={{fontSize:16,color:S.t1,flex:1}}>{label}</span><div style={{display:"flex",gap:6}}>{["有","無"].map(opt=>(<button key={opt} onClick={()=>setVal(opt)} style={{padding:"8px 16px",borderRadius:8,border:"none",cursor:"pointer",minHeight:44,fontSize:16,fontWeight:700,background:val===opt?(opt==="有"?S.green:S.red):S.bg3,color:val===opt?"#fff":S.t2}}>{opt}</button>))}</div></div>);}
function TaskRow({t,onDo}){return(<div style={{display:"flex",alignItems:"center",gap:12,padding:"14px 10px",borderBottom:`1px solid ${S.bdr}`,opacity:t.done?0.5:1}}><div style={{width:28,height:28,borderRadius:8,border:t.done?"none":`2px solid ${t.urgent?S.red:S.bdr}`,background:t.done?S.green:"transparent",display:"flex",alignItems:"center",justifyContent:"center",fontSize:14,color:"#fff",flexShrink:0}}>{t.done&&"✓"}</div><div style={{flex:1}}><div style={{fontSize:17,fontWeight:600,color:t.done?S.t3:t.urgent?S.red:S.t1,textDecoration:t.done?"line-through":"none"}}>{t.name}</div>{t.deadline&&<div style={{fontSize:15,color:S.red,marginTop:2}}>{t.deadline}</div>}</div>{!t.done&&<button onClick={()=>onDo(t.id)} style={{padding:"8px 14px",borderRadius:8,border:"none",background:t.urgent?"rgba(232,54,79,0.1)":"rgba(212,148,10,0.08)",color:t.urgent?S.red:S.amber,fontSize:16,fontWeight:700,cursor:"pointer",minHeight:44,whiteSpace:"nowrap"}}>前往 →</button>}</div>);}
function SettingsRow({icon,label,val}){return(<div style={{padding:"16px",display:"flex",alignItems:"center",justifyContent:"space-between",borderBottom:`1px solid ${S.bdr}`,cursor:"pointer",minHeight:56}}><div style={{display:"flex",alignItems:"center",gap:12}}><span style={{fontSize:20}}>{icon}</span><span style={{fontSize:16,fontWeight:600,color:S.t1}}>{label}</span></div><div style={{display:"flex",alignItems:"center",gap:6}}>{val&&<span style={{fontSize:15,color:S.t3}}>{val}</span>}<span style={{fontSize:16,color:S.t3}}>›</span></div></div>);}
function PhotoPickerInline({label,color}){const clr=color||S.amber;const[files,setFiles]=useState([]);const handleFiles=(e)=>{const f=Array.from(e.target.files||[]);const previews=f.map(file=>({name:file.name,url:URL.createObjectURL(file)}));setFiles(p=>[...p,...previews]);};return(<div>{files.length>0&&(<div style={{display:"flex",gap:8,flexWrap:"wrap",marginBottom:10}}>{files.map((f,i)=>(<div key={i} style={{width:72,height:72,borderRadius:10,overflow:"hidden",position:"relative"}}><img src={f.url} style={{width:"100%",height:"100%",objectFit:"cover"}}/><div onClick={(e)=>{e.preventDefault();setFiles(p=>p.filter((_,j)=>j!==i));}} style={{position:"absolute",top:2,right:2,width:22,height:22,borderRadius:11,background:"rgba(0,0,0,0.6)",color:"#fff",display:"flex",alignItems:"center",justifyContent:"center",fontSize:14,cursor:"pointer"}}>✕</div></div>))}</div>)}<label style={{display:"block",width:"100%",cursor:"pointer"}}><input type="file" accept="image/*" multiple style={{display:"none"}} onChange={handleFiles}/><div style={{width:"100%",padding:files.length>0?"12px":"18px",borderRadius:12,border:`2px dashed ${clr}`,background:`${clr}08`,color:clr,fontSize:files.length>0?15:16,fontWeight:700,textAlign:"center",minHeight:files.length>0?44:56,display:"flex",alignItems:"center",justifyContent:"center",gap:8}}>{files.length>0?`+ 繼續新增 (已選 ${files.length} 張)`:`📷 ${label||"上傳照片"}`}</div></label></div>);}
function PhotoPickerArea(){const[files,setFiles]=useState([]);const handleFiles=(e)=>{const f=Array.from(e.target.files||[]);const previews=f.map(file=>({name:file.name,url:URL.createObjectURL(file)}));setFiles(p=>[...p,...previews]);};return(<div style={{marginBottom:16}}>{files.length>0&&(<div style={{display:"flex",gap:8,flexWrap:"wrap",marginBottom:10}}>{files.map((f,i)=>(<div key={i} style={{width:80,height:80,borderRadius:10,overflow:"hidden",position:"relative"}}><img src={f.url} style={{width:"100%",height:"100%",objectFit:"cover"}}/><div onClick={()=>setFiles(p=>p.filter((_,j)=>j!==i))} style={{position:"absolute",top:2,right:2,width:22,height:22,borderRadius:11,background:"rgba(0,0,0,0.6)",color:"#fff",display:"flex",alignItems:"center",justifyContent:"center",fontSize:14,cursor:"pointer"}}>✕</div></div>))}</div>)}<label style={{display:"block",cursor:"pointer"}}><input type="file" accept="image/*" multiple style={{display:"none"}} onChange={handleFiles}/><div style={{width:"100%",background:S.bg2,borderRadius:14,border:`2px dashed ${S.amber}`,padding:files.length>0?"16px":"30px 16px",textAlign:"center"}}>{files.length>0?(<div style={{fontSize:16,fontWeight:700,color:S.amber}}>+ 繼續新增 (已選 {files.length} 張)</div>):(<><div style={{fontSize:56,marginBottom:10}}>📷</div><div style={{fontSize:20,fontWeight:700,color:S.amber,marginBottom:6}}>點擊上傳照片</div><div style={{fontSize:15,color:S.t3}}>可一次選取多張照片</div></>)}</div></label></div>);}
function PlaceholderPage({title,icon,desc}){return(<div style={{padding:"16px 14px",paddingBottom:S.navH+24,textAlign:"center"}}><div style={{fontSize:56,marginBottom:16}}>{icon||"🚧"}</div><div style={{fontSize:22,fontWeight:700,marginBottom:8}}>{title||"開發中"}</div><div style={{fontSize:16,color:S.t2}}>{desc||"此功能即將推出"}</div></div>);}

export default App;