import {useEffect,useRef,useState} from 'react';
import type {PointerEvent as ReactPointerEvent} from 'react';
import {request,imageUrl,loadImage} from './services/api';
import type {Task,ExportInfo} from './services/api';
import {imagePoint,rectangle} from './editor/geometry';
import type {Point} from './editor/geometry';
import CloudEditor from './CloudEditor';

type Tool='rect'|'polygon'|'perspective'|'add'|'erase'|'pan';
const names:Record<Tool,string>={rect:'矩形选区',polygon:'多边形',perspective:'四点透视',add:'添加画笔',erase:'擦除画笔',pan:'拖动画布'};
type Drag={type:'draw'|'move'|'corner'|'brush'|'pan';start:Point;previous:Point;initial:Point[];corner?:number;client?:Point;scroll?:Point};

export default function App() {
  const [task,setTask]=useState<Task|null>(null), [busy,setBusy]=useState(''),[error,setError]=useState('');
  const [tool,setTool]=useState<Tool>('rect'),[points,setPoints]=useState<Point[]>([]),[zoom,setZoom]=useState(0);
  const [brush,setBrush]=useState(24),[background,setBackground]=useState('checker'),[method,setMethod]=useState('grabcut');
  const [tolerance,setTolerance]=useState(28),[smooth,setSmooth]=useState(0),[feather,setFeather]=useState(0),[expand,setExpand]=useState(0),[padding,setPadding]=useState(12);
  const [exported,setExported]=useState<ExportInfo|null>(null),[maskOverlay,setMaskOverlay]=useState(true),[ready,setReady]=useState(false),[viewport,setViewport]=useState(560),[viewportHeight,setViewportHeight]=useState(610);
  const [originalZoom,setOriginalZoom]=useState(0),[previewZoom,setPreviewZoom]=useState(0),[filename,setFilename]=useState('');
  const [originalWidth,setOriginalWidth]=useState(0);
  const [cloudEnabled,setCloudEnabled]=useState(false);
  const [exportSize,setExportSize]=useState('1'),[longEdge,setLongEdge]=useState(1254);
  const canvas=useRef<HTMLCanvasElement>(null),result=useRef<HTMLCanvasElement>(null),mask=useRef(document.createElement('canvas'));
  const image=useRef<HTMLImageElement|null>(null),drag=useRef<Drag|null>(null),editor=useRef<HTMLDivElement>(null),input=useRef<HTMLInputElement>(null);
  const taskRef=useRef(task); taskRef.current=task;
  const scale=task?(zoom||Math.min(1,(viewport-32)/task.width,(viewportHeight-32)/task.height)):1;

  async function run(label:string,fn:()=>Promise<void>) {
    setError('');setBusy(label);
    try {await fn();} catch(e) {setError(e instanceof Error?e.message:String(e));} finally {setBusy('');}
  }
  function accept(next:Task) {setTask(next);setExported(next.export||null);localStorage.setItem('print-extractor-task',next.id);}
  async function mutate(action:string,body:unknown={}) {if(task)accept(await request<Task>(`tasks/${task.id}/${action}`,body));}
  function draw() {
    if(!image.current || !canvas.current || !result.current) return;
    const w=image.current.naturalWidth,h=image.current.naturalHeight;
    const ctx=canvas.current.getContext('2d')!,out=result.current.getContext('2d')!,mc=mask.current.getContext('2d')!;
    ctx.clearRect(0,0,w,h);ctx.drawImage(image.current,0,0);
    out.clearRect(0,0,w,h);out.drawImage(image.current,0,0);
    const rgb=out.getImageData(0,0,w,h),alpha=mc.getImageData(0,0,w,h);
    for(let i=0;i<rgb.data.length;i+=4) rgb.data[i+3]=Math.min(rgb.data[i+3],alpha.data[i]);
    out.putImageData(rgb,0,0);
    if(maskOverlay) {
      const overlay=ctx.getImageData(0,0,w,h);
      for(let i=0;i<overlay.data.length;i+=4) {const a=(1-alpha.data[i]/255)*.55; overlay.data[i]=overlay.data[i]*(1-a)+230*a;overlay.data[i+1]*=1-a;overlay.data[i+2]*=1-a;}
      ctx.putImageData(overlay,0,0);
    }
    if(points.length) {
      ctx.strokeStyle='#b9ff66';ctx.lineWidth=2/scale;ctx.fillStyle='rgba(185,255,102,.08)';ctx.beginPath();
      points.forEach((p,i)=>i?ctx.lineTo(...p):ctx.moveTo(...p));
      if(points.length>=3)ctx.closePath();ctx.fill();ctx.stroke();
      points.forEach((p,i)=>{ctx.fillStyle='#b9ff66';ctx.fillRect(p[0]-4/scale,p[1]-4/scale,8/scale,8/scale);if(tool==='perspective'){ctx.font=`${16/scale}px sans-serif`;ctx.fillText(String(i+1),p[0]+8/scale,p[1]);}});
    }
  }

  useEffect(()=>{const ro=new ResizeObserver(entries=>{setViewport(entries[0].contentRect.width);setViewportHeight(entries[0].contentRect.height);});if(editor.current)ro.observe(editor.current);return()=>ro.disconnect();},[]);
  useEffect(()=>{const id=localStorage.getItem('print-extractor-task');if(id)run('恢复上次任务',async()=>{accept(await request<Task>(`tasks/${id}`,undefined,'GET'));}).catch(()=>{});},[]);
  useEffect(()=>{
    if(!task)return;
    let active=true;setReady(false);
    Promise.all([loadImage(imageUrl(task,'work')),loadImage(imageUrl(task,'mask'))]).then(([im,ma])=>{
      if(!active)return;image.current=im;
      [canvas.current,result.current,mask.current].forEach(c=>{if(c){c.width=im.naturalWidth;c.height=im.naturalHeight;}});
      mask.current.getContext('2d')!.drawImage(ma,0,0);setReady(true);
    }).catch(e=>{if(active)setError(e.message);});
    return()=>{active=false;};
  },[task?.id,task?.rev]);
  useEffect(()=>{if(ready)draw();},[ready,points,scale,maskOverlay]);
  useEffect(()=>{
    const handler=(e:KeyboardEvent)=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'&&!(e.target instanceof HTMLInputElement)){e.preventDefault();const t=taskRef.current;if(t&&!busy)run('恢复操作',async()=>accept(await request<Task>(`tasks/${t.id}/history/${e.shiftKey?'redo':'undo'}`,{})));}if(e.key==='Escape')setPoints([]);};
    window.addEventListener('keydown',handler);return()=>window.removeEventListener('keydown',handler);
  },[busy]);

  async function upload(file?:File) {
    if(!file||busy)return;
    await run('上传与解码',async()=>{
      if(file.size>25*1024*1024)throw new Error('文件超过 25MB 限制');
      const form=new FormData();form.append('file',file);
      const next=await request<Task>('tasks',form);accept(next);setFilename(file.name);setPoints([]);setZoom(0);
      const proposal=await request<{box:number[]}>(`tasks/${next.id}/detect`,{});
      setPoints(rectangle([proposal.box[0],proposal.box[1]],[proposal.box[2],proposal.box[3]]));setTool('rect');
    });
  }
  function position(e:ReactPointerEvent<HTMLCanvasElement>):Point {return imagePoint(e.clientX,e.clientY,e.currentTarget.getBoundingClientRect(),e.currentTarget.width,e.currentTarget.height);}
  function stroke(a:Point,b:Point) {
    const ctx=mask.current.getContext('2d')!;ctx.strokeStyle=tool==='add'?'white':'black';ctx.fillStyle=ctx.strokeStyle;ctx.lineWidth=brush;ctx.lineCap='round';ctx.lineJoin='round';
    ctx.beginPath();ctx.moveTo(...a);ctx.lineTo(...b);ctx.stroke();ctx.beginPath();ctx.arc(b[0],b[1],brush/2,0,Math.PI*2);ctx.fill();draw();
  }
  function down(e:ReactPointerEvent<HTMLCanvasElement>) {
    if(!ready||busy)return;e.currentTarget.setPointerCapture(e.pointerId);
    const p=position(e);
    if(tool==='pan') {drag.current={type:'pan',start:p,previous:p,initial:[],client:[e.clientX,e.clientY],scroll:[editor.current!.scrollLeft,editor.current!.scrollTop]};return;}
    if(tool==='add'||tool==='erase') {drag.current={type:'brush',start:p,previous:p,initial:[]};stroke(p,p);return;}
    if(tool==='polygon'||tool==='perspective') {setPoints(prev=>tool==='perspective'&&prev.length>=4?[p]:[...prev,p]);return;}
    const corner=points.findIndex(q=>Math.hypot(q[0]-p[0],q[1]-p[1])<12/scale);
    if(points.length===4 && corner>=0)drag.current={type:'corner',start:p,previous:p,initial:points,corner};
    else if(points.length===4 && p[0]>points[0][0]&&p[0]<points[2][0]&&p[1]>points[0][1]&&p[1]<points[2][1])drag.current={type:'move',start:p,previous:p,initial:points};
    else {drag.current={type:'draw',start:p,previous:p,initial:[]};setPoints([p,p,p,p]);}
  }
  function move(e:ReactPointerEvent<HTMLCanvasElement>) {
    const d=drag.current;if(!d||busy)return;const p=position(e);
    if(d.type==='pan') {editor.current!.scrollLeft=d.scroll![0]+d.client![0]-e.clientX;editor.current!.scrollTop=d.scroll![1]+d.client![1]-e.clientY;}
    else if(d.type==='brush'){stroke(d.previous,p);d.previous=p;}
    else if(d.type==='draw')setPoints(rectangle(d.start,p));
    else if(d.type==='corner')setPoints(rectangle(d.initial[(d.corner!+2)%4],p));
    else if(d.type==='move') {
      const dx=Math.max(-d.initial[0][0],Math.min(task!.width-1-d.initial[2][0],p[0]-d.start[0]));
      const dy=Math.max(-d.initial[0][1],Math.min(task!.height-1-d.initial[2][1],p[1]-d.start[1]));
      setPoints(d.initial.map(q=>[q[0]+dx,q[1]+dy]));
    }
  }
  async function saveMask() {
    if(!task)return;
    const blob=await new Promise<Blob>((resolve,reject)=>mask.current.toBlob(b=>b?resolve(b):reject(new Error('蒙版编码失败')),'image/png'));
    const form=new FormData();form.append('file',blob,'mask.png');accept(await request<Task>(`tasks/${task.id}/mask`,form,'PUT'));
  }
  function up() {const d=drag.current;drag.current=null;if(d?.type==='brush')run('保存蒙版',saveMask);}
  async function fillSelection(keep:boolean) {
    if(points.length<3)throw new Error('请先设置至少三个选区顶点');
    const ctx=mask.current.getContext('2d')!;ctx.fillStyle=keep?'white':'black';ctx.beginPath();points.forEach((p,i)=>i?ctx.lineTo(...p):ctx.moveTo(...p));ctx.closePath();ctx.fill();draw();await saveMask();setPoints([]);
  }
  const disabled=!!busy||!task||!ready;
  const extracted=!!task&&!['unprocessed','cropped'].includes(task.method);
  const button=(label:string,fn:()=>Promise<void>,extra=false)=><button disabled={disabled||extra} onClick={()=>run(label,fn)}>{label}</button>;

  return <div className="app" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();upload(e.dataTransfer.files[0]);}}>
    <header><div className="brand"><span className="mark">P↗</span><div><h1>Print Extractor <span>AI</span></h1><small>印花提取工作台</small></div></div><div className="local"><i/> 默认在本机处理 <span>{cloudEnabled?'AI 已连接 · 使用前确认上传':'AI 提取可选'}</span></div></header>
    <div className="statusbar" role="status"><span>{busy?<><i className="processing"/>{busy}…</>:task?'● 图片已就绪 · 需要检查':'准备就绪 · 上传一张 T 恤商品图'}</span><small>01 上传　→　02 确认选区　→　03 分割与修正　→　04 导出</small></div>
    {error&&<div className="error" role="alert">{error}<button onClick={()=>setError('')}>关闭</button></div>}
    <main>
      <aside className="tools"><section><h2>01 <span>输入图片</span></h2><button className="dropzone" disabled={!!busy} onClick={()=>input.current?.click()}><strong>＋ 拖拽或选择图片</strong><small>JPG / PNG / WebP · ≤25MB · ≤1600万像素</small></button><input ref={input} data-testid="upload" type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={e=>{upload(e.target.files?.[0]);e.target.value='';}}/>{task&&<p className="fileinfo">{filename||'已恢复本地任务'}<br/>{task.width} × {task.height} px</p>}</section>
      <section><h2>02 <span>确认印花选区</span></h2>{button('自动候选定位',async()=>{const r=await request<{box:number[]}>(`tasks/${task!.id}/detect`,{});setTool('rect');setPoints(rectangle([r.box[0],r.box[1]],[r.box[2],r.box[3]]));})}
        <div className="toolgrid">{(['rect','polygon','perspective','pan'] as Tool[]).map(t=><button key={t} disabled={disabled} aria-pressed={tool===t} onClick={()=>{setTool(t);if(t!=='pan')setPoints([]);}}>{names[t]}</button>)}</div>
        <p className="hint">{tool==='perspective'?'依次点击：左上 → 右上 → 右下 → 左下。':tool==='polygon'?'逐点点击，多边形自动闭合。Esc 清空。':'拖动绘制矩形；拖动框内移动，拖动角点调大小。'}</p>
        {tool==='perspective'?button('应用四点透视',async()=>{await mutate('transform',{points});setPoints([]);setZoom(0);},points.length!==4):button('确认并裁切选区',async()=>{await mutate('crop',{points});setPoints([]);setZoom(0);},points.length<3)}
        <div className="row">{button('选区补充',()=>fillSelection(true),points.length<3)}{button('选区排除',()=>fillSelection(false),points.length<3)}</div>
        <button className="text" onClick={()=>setPoints([])}>清空选区</button>
      </section>
      <section><h2>03 <span>生成候选蒙版</span></h2><select aria-label="分割算法" value={method} disabled={disabled} onChange={e=>setMethod(e.target.value)}><option value="grabcut">GrabCut · 颜色与空间分割</option><option value="color">Lab 颜色差异 · 边缘估色</option><option value="manual">手动 · 保留选区全部像素</option></select><label>颜色差异 <b>{tolerance}</b><input aria-label="颜色差异" type="range" min="2" max="150" value={tolerance} onChange={e=>setTolerance(+e.target.value)}/></label>
        {button('生成分割候选',async()=>{await mutate('segment',{method,tolerance});setPoints([]);})}
        <div className="row">{task?.candidates.map(name=><button key={name} disabled={disabled} onClick={()=>run('切换候选',()=>mutate('candidate',{name}))}>{name==='color'?'颜色':name==='grabcut'?'GrabCut':'全保留'}</button>)}</div>
      </section>
      <section><h2>04 <span>手动修正</span></h2><div className="row">{(['add','erase'] as Tool[]).map(t=><button key={t} disabled={disabled} aria-pressed={tool===t} onClick={()=>{setTool(t);setPoints([]);}}>{names[t]}</button>)}</div>
        <label>笔刷直径 <b>{brush} px</b><input aria-label="笔刷直径" type="range" min="1" max="200" value={brush} onChange={e=>setBrush(+e.target.value)}/></label>
        {button('保存当前蒙版',saveMask)}
        {button('用当前蒙版引导 GrabCut',()=>mutate('segment',{method:'grabcut',tolerance,use_seed:true}))}<p className="hint">先添加/擦除修正。引导模式将蒙版纯白和纯黑像素作为确定种子。</p>
        <details><summary>边缘调整</summary><label>平滑 <b>{smooth}</b><input aria-label="平滑" type="range" min="0" max="10" value={smooth} onChange={e=>setSmooth(+e.target.value)}/></label><label>羽化 <b>{feather} px</b><input aria-label="羽化" type="range" min="0" max="20" value={feather} onChange={e=>setFeather(+e.target.value)}/></label><label>扩张 / 收缩 <b>{expand} px</b><input aria-label="扩张收缩" type="range" min="-20" max="20" value={expand} onChange={e=>setExpand(+e.target.value)}/></label>{button('应用边缘调整',()=>mutate('edges',{smooth,feather,expand}))}</details>
      </section>
      <section><div className="row">{button('恢复原图',async()=>{await mutate('reset');setPoints([]);setZoom(0);})}{button('删除当前任务',async()=>{await request(`tasks/${task!.id}`,undefined,'DELETE');setTask(null);setReady(false);setPoints([]);image.current=null;setExported(null);localStorage.removeItem('print-extractor-task');})}</div></section></aside>

      <article className="workspace"><div className="panelhead"><div><strong>编辑画布</strong><small>{names[tool]}{tool==='add'||tool==='erase'?` · ${brush}px`:''}</small></div><div className="row">{button('撤销',async()=>{await mutate('history/undo');setPoints([]);},!task?.can_undo)}{button('重做',async()=>{await mutate('history/redo');setPoints([]);},!task?.can_redo)}</div></div>
      <div className="canvasbar"><div className="row"><button aria-pressed={zoom===0} onClick={()=>setZoom(0)}>适应</button>{[1,2,4].map(z=><button key={z} aria-pressed={zoom===z} onClick={()=>setZoom(z)}>{z*100}%</button>)}</div><label className="check"><input type="checkbox" checked={maskOverlay} onChange={e=>setMaskOverlay(e.target.checked)}/> 显示排除区域</label></div>
      <div className={'editor '+(!task?'empty':'')} ref={editor}>
        {!task&&<div className="welcome"><div className="shirt">T</div><h2>从照片中取出印花</h2><p>上传商品图，确认胸前选区。<br/>生成蒙版后，用画笔保留每一处细节。</p><button className="primary" onClick={()=>input.current?.click()}>选择第一张图片</button><small>原图保留 · 真实 Alpha · 不上传云端</small></div>}
        <canvas ref={canvas} data-testid="editor" style={{display:task?'block':'none',width:task?task.width*scale:0,height:task?task.height*scale:0,cursor:tool==='pan'?'grab':'crosshair'}} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}/>
      </div>
      <div className="canvasfoot"><span>{task?`${Math.round(scale*100)}% · ${task.width} × ${task.height} px`:'等待图片'}</span><span>红色 = 蒙版排除 · Ctrl+Z 撤销</span></div>
      <section className="original"><div className="panelhead"><strong>原图对照</strong><select aria-label="原图缩放" value={originalZoom} onChange={e=>setOriginalZoom(+e.target.value)}><option value="0">适应</option><option value="2">200%</option><option value="4">400%</option></select></div><div className="originalscroll">{task?<img alt="原始商品图" src={task.provenance?`/api/tasks/${task.provenance.task_id}/preview?kind=original`:imageUrl(task,'original')} onLoad={e=>setOriginalWidth(e.currentTarget.naturalWidth)} style={originalZoom?{maxWidth:'none',maxHeight:'none',width:originalWidth*originalZoom}:{}}/>:<p>保留原始图像用于对照</p>}</div></section>
      </article>

      <aside className="output">{task?.provenance&&<section className="refine-context"><p>正在精修 AI 生成图。商品原图与生成文件均已保留。</p><button disabled={!!busy} onClick={()=>run('返回商品图',async()=>{const next=await request<Task>(`tasks/${task.provenance!.task_id}`,undefined,'GET');accept(next);setPoints([]);setZoom(0);setFilename('商品原图');})}>返回商品图与生成记录</button></section>}<CloudEditor onRefine={next=>{accept(next);setPoints([]);setZoom(0);setTool('erase');setFilename('AI 生成图 · 继续精修');}} key={task?.id||'empty'} task={task} onEnabled={setCloudEnabled} onBusy={setBusy} background={background}/><div className="panelhead"><strong>透明结果</strong><span className="badge">需要检查</span></div><div className="canvasbar"><div className="row">{[['checker','棋盘格'],['white','白底'],['black','黑底']].map(([v,label])=><button key={v} aria-pressed={background===v} onClick={()=>setBackground(v)}>{label}</button>)}</div><select aria-label="结果缩放" value={previewZoom} onChange={e=>setPreviewZoom(+e.target.value)}><option value="0">适应</option><option value="2">200%</option><option value="4">400%</option></select></div>
      <div className={'resultscroll '+background}><canvas ref={result} data-testid="result" style={{display:task?'block':'none',width:task?(previewZoom?task.width*previewZoom:'auto'):0,maxWidth:previewZoom?'none':'100%',maxHeight:previewZoom?'none':'100%',height:'auto'}}/>{!task&&<span>透明 PNG 预览</span>}</div>
      <section><h2>结果检查</h2><dl><dt>工作尺寸</dt><dd>{task?`${task.width} × ${task.height}`:'—'}</dd><dt>导出尺寸</dt><dd data-testid="export-size">{exported?`${exported.width} × ${exported.height}`:'导出后显示'}</dd><dt>透视校正</dt><dd>{task?.transformed?'已应用（重采样）':'未应用'}</dd><dt>AI 模型</dt><dd>{task?.provenance?({gpt:'GPT',grok:'Grok',qwen:'千问'}[task.provenance.provider]||task.provenance.provider):'未使用'}</dd><dt>Alpha 通道</dt><dd>{exported?`${exported.alpha_min}–${exported.alpha_max} · RGBA`:'导出时自动验证'}</dd></dl>
        <div className="warning">{task?.warnings.map((w,i)=><p key={i}>{w}</p>)||<p>同色印花和遮挡区域可能无法从单张照片分离。</p>}{exported?.possible_background_residue&&<p>检测到图案触及工作图边缘，可能有衣服残留或选区截断，请放大检查。</p>}</div>
        <p className="hint">请在黑/白底 200%–400% 检查文字、细线、彩色装饰和边缘。候选不是准确率保证。</p>
      </section><section className="export"><h2>05 <span>导出 PNG</span></h2>{!extracted&&<p className="warning">尚未提取印花。请先确认选区并点击“生成分割候选”，检查右侧衣服背景变为棋盘格后再导出。</p>}<label>导出大小<select aria-label="导出大小" value={exportSize} disabled={!!busy} onChange={e=>{setExportSize(e.target.value);setExported(null);}}><option value="1">原图尺寸 · 不放大</option><option value="2">2 倍 · 插值放大</option><option value="4">4 倍 · 插值放大</option><option value="custom">自定义长边</option></select></label>{exportSize==='custom'&&<label>目标长边（含边距）<input aria-label="目标长边" type="number" min="8" max="8192" value={longEdge} onChange={e=>{setLongEdge(+e.target.value);setExported(null);}}/></label>}<p className="warning">放大不增加原始细节，不是原生高清或 AI 重建。最大 8192px 长边 / 1600 万像素。边距随图案等比例放大。</p><label>透明安全边距 <b>{padding} px</b><input aria-label="透明安全边距" type="number" min="0" max="200" value={padding} onChange={e=>{setPadding(+e.target.value);setExported(null);}}/></label><button className="primary" disabled={disabled||!extracted} onClick={()=>run('验证并导出',async()=>{setExported(await request<ExportInfo>(`tasks/${task!.id}/export`,{padding,scale:exportSize==='custom'?1:+exportSize,target_long_edge:exportSize==='custom'?longEdge:null}));})}>验证并导出 RGBA PNG ↗</button>{exported?.detail_note&&<p className="hint">{exported.detail_note}；原尺寸 {exported.native_width} × {exported.native_height} → 输出 {exported.width} × {exported.height}</p>}{exported&&task&&extracted&&<a className="download" href={`/api/tasks/${task.id}/download`} download="print-extracted.png">下载透明 PNG ↓</a>}<small>自动裁切并加透明边距<br/>{task?.provenance?'在生成图上修正，不改变商品原图':'保留原图像素，透视操作除外'}</small></section>

</aside>
    </main><footer>PRINT EXTRACTOR AI <span>本地文件保存在 data/tasks · 最近 20 步可恢复 · 无自动清理，请按需删除任务</span></footer>
  </div>;
}

