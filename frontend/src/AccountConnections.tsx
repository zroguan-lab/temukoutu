import {useEffect,useState} from 'react';
import {request} from './services/api';
import type {Connection} from './services/ai';

export default function AccountConnections({onChanged,disabled}:{onChanged:()=>Promise<void>;disabled:boolean}) {
  const [states,setStates]=useState<Record<string,Connection>>({}),[busy,setBusy]=useState(''),[error,setError]=useState('');
  async function read() {
    const entries=await Promise.all(['gpt','grok'].map(async id=>[id,await request<Connection>(`connections/${id}`,undefined,'GET')] as const));
    setStates(Object.fromEntries(entries));
  }
  useEffect(()=>{read().catch(()=>setError('无法读取登录状态'));},[]);
  const waiting=Object.values(states).some(s=>s.state==='waiting');
  useEffect(()=>{
    if(!waiting)return;
    const timer=window.setInterval(()=>{read().then(onChanged).catch(()=>setError('登录状态暂未确认，请稍后检查'));},2500);
    return()=>window.clearInterval(timer);
  },[waiting]);
  async function action(id:string,kind:'check'|'login') {
    setBusy(id);setError('');
    try {
      const state=await request<Connection>(`connections/${id}/${kind}`,{},'POST',35_000);
      setStates(previous=>({...previous,[id]:state}));await onChanged();
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy('');}
  }
  return <div className="account-connections">
    {['gpt','grok'].map(id=>{const state=states[id];const label=id==='gpt'?'GPT':'Grok';return <div className="connection" key={id}>
      <strong>{label} 账号</strong><p role="status">{state?.message||'正在读取…'}</p>
      {state&&!state.installed&&<p className="hint">请先安装官方 {id==='gpt'?'Codex':'Grok Build'} CLI，然后重新检查。</p>}
      <div className="row"><button disabled={disabled||!!busy||!state?.installed||state?.state==='waiting'} onClick={()=>action(id,'check')}>{busy===id?'处理中…':`检查 ${label} 登录`}</button>
      <button disabled={disabled||!!busy||!state?.installed||state?.state==='waiting'} onClick={()=>action(id,'login')}>{state?.authenticated?'重新登录':`连接 ${label}`}</button></div>
      {state?.state==='waiting'&&<p className="hint">官方登录页正在等待你操作。密码与授权由你在浏览器中完成，完成后这里会更新。</p>}
    </div>;})}
    <p className="hint">登录由官方 CLI 管理，项目不复制浏览器 cookie 或 token。生成图片会使用对应账号的权限和额度。</p>
    {error&&<p role="alert" className="error">{error}</p>}
  </div>;
}
