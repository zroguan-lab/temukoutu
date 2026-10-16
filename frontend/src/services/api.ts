export type Task = {provenance?:{task_id:string;generation_id:string;provider:string;model:string;transparent:boolean};id:string;rev:string;width:number;height:number;method:string;status:string;transformed:boolean;ai_used:boolean;warnings:string[];can_undo:boolean;can_redo:boolean;candidates:string[];export?:ExportInfo};
export type ExportInfo = {width:number;height:number;alpha_min:number;alpha_max:number;possible_background_residue:boolean;warnings:string[];native_width?:number;native_height?:number;resampled?:boolean;detail_note?:string};
export async function request<T>(path:string, body?:unknown, method='POST', timeoutMs=100_000):Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(()=>controller.abort(),timeoutMs);
  try {
    const response = await fetch('/api/'+path, {method,signal:controller.signal,
      headers:body instanceof FormData || body === undefined ? {} : {'Content-Type':'application/json'},
      body:body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body)});
    if(!response.ok) { const error = await response.json().catch(()=>null); throw new Error(error?.error?.message || `请求失败 (${response.status})`); }
    return response.json();
  } catch(error) {
    if(error instanceof DOMException && error.name==='AbortError') throw new Error('请求超时，请检查服务状态后重试。');
    throw error;
  } finally {window.clearTimeout(timer);}
}
export function imageUrl(task:Task,kind:string) {return `/api/tasks/${task.id}/preview?kind=${kind}&v=${task.rev}`;}
export function loadImage(url:string):Promise<HTMLImageElement> { return new Promise((resolve,reject)=>{const img=new Image();img.onload=()=>resolve(img);img.onerror=()=>reject(new Error('图像预览加载失败'));img.src=url;}); }
