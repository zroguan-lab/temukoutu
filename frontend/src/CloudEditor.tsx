import {useEffect,useState} from 'react';
import {request} from './services/api';
import type {Task} from './services/api';
import type {Providers,Generation} from './services/ai';
import AISettings from './AISettings';

export default function CloudEditor({task,onEnabled,onBusy,onRefine,background}:{task:Task|null;onEnabled:(enabled:boolean)=>void;onBusy:(label:string)=>void;onRefine:(task:Task)=>void;background:string}) {
  const [config,setConfig]=useState<Providers|null>(null),[model,setModel]=useState('gpt-image');
  const [consent,setConsent]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [items,setItems]=useState<Generation[]>([]);
  async function refreshConfig() {
    const c=await request<Providers>('providers',undefined,'GET');setConfig(c);
    onEnabled(Object.values(c.connections).some(s=>s.authenticated));setConsent(false);
  }
  useEffect(()=>{refreshConfig().catch(()=>setError('无法读取 AI 配置；本地提取仍可使用。'));},[]);
  useEffect(()=>{
    setConsent(false);setItems([]);setError('');let active=true;
    if(task)request<Generation[]>(`tasks/${task.id}/generations`,undefined,'GET').then(r=>{if(active)setItems(r);}).catch(()=>{if(active)setError('无法读取生成记录');});
    return()=>{active=false;};
  },[task?.id,task?.rev]);
  const selected=config?.models.find(m=>m.id===model),provider=selected?.provider||'gpt';
  const enabled=provider==='qwen'?!!config?.cloud.enabled:!!config?.connections[provider]?.installed;
  async function refreshItems() {if(task)setItems(await request<Generation[]>(`tasks/${task.id}/generations`,undefined,'GET'));}
  async function generate() {
    if(!task||!consent||busy||!enabled)return;
    setBusy(true);onBusy('AI 正在提取');setError('');const source=task;
    try {
      await request<Generation>(`tasks/${source.id}/generations`,{model,request_id:crypto.randomUUID().replaceAll('-',''),source_revision:source.rev,
        allow_upload:true,allow_account_usage:provider!=='qwen',max_estimated_cost_cny:selected?.estimated_cost_cny||0},'POST',210_000);
    }catch(e){
      const message=e instanceof Error?e.message:String(e);
      setError(message.includes('请求超时')||message.includes('Failed to fetch')
        ?'结果暂未确认，可能仍在生成并已使用额度。请先刷新生成记录、核对账号用量，再决定是否重新生成。':message);
    }finally{
      try {setItems(await request<Generation[]>(`tasks/${source.id}/generations`,undefined,'GET'));}catch{/* Source may have been removed outside the page. */}
      setBusy(false);onBusy('');setConsent(false);
    }
  }
  async function refine(item:Generation) {
    if(!task||busy)return;
    setBusy(true);onBusy('准备精修');setError('');
    try {const next=await request<Task>(`tasks/${task.id}/generations/${item.id}/refine`,{});onRefine(next);}
    catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy(false);onBusy('');}
  }
  return <section className="cloud-editor"><details><summary>AI 提取</summary>
    <p>从当前工作图提取印花。生成结果可能改变文字和细节，请对照原图检查。</p>
    <AISettings onSaved={refreshConfig} disabled={busy}/>
    <label>选择 AI<select aria-label="AI 图像模型" value={model} disabled={busy} onChange={e=>{setModel(e.target.value);setConsent(false);}}>
      {config?.models.map(m=><option key={m.id} value={m.id}>{m.label}{m.estimated_cost_cny?` · 约 ¥${m.estimated_cost_cny.toFixed(2)}/张`:''}</option>)}
    </select></label>
    {provider!=='qwen'?<p className="hint">通过官方 {provider==='gpt'?'Codex':'Grok Build'} 使用本人登录。账号需具备图像权限和可用额度；登录成功不保证每次都能出图。</p>
      :<p className="hint">需要北京地域百炼 Key。当前适配尚未完成真实出图验证。</p>}
    {!enabled&&<p className="hint">展开“配置 AI”，先完成安装、登录或 Key 配置。</p>}
    <label className="cloud-consent"><input type="checkbox" aria-label="同意上传和使用额度" checked={consent} disabled={!task||!enabled||busy} onChange={e=>setConsent(e.target.checked)}/>
      {provider==='qwen'?`同意上传至阿里云北京地域，并接受本次预计 ¥${(selected?.estimated_cost_cny||0).toFixed(2)} 费用。`:`同意上传至 ${provider==='gpt'?'OpenAI':'xAI'} 官方服务，并使用本人账号额度。`}</label>
    <button className="primary" disabled={!task||!consent||!enabled||busy} onClick={generate}>{busy?'正在处理，请稍候…':'开始 AI 提取'}</button>
    <button className="text" disabled={!task||busy} onClick={()=>refreshItems().catch(()=>setError('无法刷新生成记录'))}>刷新生成记录</button>
    {error&&<p role="alert" className="error">{error}</p>}
    {items.map(item=><div className="generated" key={item.id} data-testid="generation"><p>{config?.models.find(m=>m.id===item.model)?.label||item.model} · {item.state==='completed'?(item.transparent?'透明候选，待检查':'已出图，需去背景'):item.state==='failed'?'未取得可用结果':'状态待确认，请先核对用量'}</p>
      {item.state==='completed'&&<><p>{item.width} × {item.height}{item.source_revision!==task?.rev?' · 来自先前工作图':''}</p>
        <div className={'generated-preview '+background}><img alt={item.transparent?'AI 透明候选，需核对细节':'AI 原始生成图，尚无透明背景'} src={`/api/tasks/${task!.id}/generations/${item.id}/image`}/></div>
        <button disabled={busy} onClick={()=>refine(item)}>继续精修</button>
        <a href={`/api/tasks/${task!.id}/generations/${item.id}/image`} download={`generated-original.${item.format||'png'}`}>{item.transparent?'下载透明候选（需检查）':`下载生成原图（${(item.format||'图片').toUpperCase()}，非透明）`}</a></>}
      {item.error&&<p className="warning">{item.error}</p>}<small>{item.warning}</small></div>)}
  </details></section>;
}
