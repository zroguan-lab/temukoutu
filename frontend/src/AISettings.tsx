import {useEffect,useState} from 'react';
import {request} from './services/api';
import AccountConnections from './AccountConnections';

type Settings={enabled:boolean;key_configured:boolean;workspace_id:string;error?:string};

export default function AISettings({onSaved,disabled=false}:{onSaved:()=>Promise<void>;disabled?:boolean}) {
  const [settings,setSettings]=useState<Settings|null>(null),[key,setKey]=useState(''),[workspace,setWorkspace]=useState('');
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[saved,setSaved]=useState(false);
  useEffect(()=>{let active=true;request<Settings>('settings',undefined,'GET').then(s=>{if(active){setSettings(s);setWorkspace(s.workspace_id);setError(s.error||'');}}).catch(()=>{if(active)setError('无法读取 AI 配置状态');});return()=>{active=false;};},[]);
  async function save(enabled:boolean) {
    setBusy(true);setError('');setSaved(false);
    try {
      const next=await request<Settings>('settings',{enabled,api_key:key||null,workspace_id:workspace},'PUT');
      setSettings(next);setKey('');setSaved(true);await onSaved();
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy(false);}
  }
  async function clear() {
    setBusy(true);setError('');
    try {setSettings(await request<Settings>('settings',undefined,'DELETE'));setKey('');setWorkspace('');setSaved(false);await onSaved();}
    catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}
  }
  return <details className="ai-settings"><summary>配置 AI</summary>
    <AccountConnections onChanged={onSaved} disabled={disabled||busy}/><details><summary>千问实验配置（未验证可用）</summary><p>保留的北京百炼实验接口，未成功完成端到端出图，不列入工作台可用模型。保存 Key 不代表接口可用；实验请求会上传图片并可能产生费用。</p>
    <label>百炼 API Key<input aria-label="百炼 API Key" type="password" autoComplete="new-password" spellCheck={false} value={key}
      placeholder={settings?.key_configured?'已保存，留空保留':'在本机输入 API Key'} disabled={disabled||busy}
      onChange={e=>{setKey(e.target.value);setSaved(false);}}/></label>
    <details><summary>业务空间（可选）</summary><label>北京业务空间 ID<input aria-label="北京业务空间 ID" value={workspace} disabled={disabled||busy} onChange={e=>setWorkspace(e.target.value)}/></label></details>
    <button disabled={disabled||busy||(!key&&!settings?.key_configured)} onClick={()=>save(true)}>{busy?'正在保存…':'保存实验配置'}</button>
    {settings?.enabled&&<button disabled={disabled||busy} onClick={()=>save(false)}>关闭云端处理</button>}
    {settings?.key_configured&&<button disabled={disabled||busy} onClick={clear}>清除本机 Key</button>}
    <p role="status">{saved?'实验配置已保存。':''}{settings?.enabled?'实验配置已启用（尚未验证可用）':settings?.key_configured?'Key 已保存，云端已关闭':'尚未配置 Key，本地提取仍可用'}</p>
    {error&&<p role="alert" className="error">{error}</p>}
  </details></details>;
}
