import {test,expect} from '@playwright/test';
import path from 'node:path';

test('AI requires explicit upload consent and local extraction remains available',async({page})=>{
  await page.goto('/');await page.getByText('AI 提取',{exact:true}).click();
  await expect(page.getByRole('button',{name:'开始 AI 提取',exact:true})).toBeDisabled();
  await expect(page.getByLabel('同意上传和使用额度')).toBeDisabled();
  const config=await (await page.request.get('/api/providers')).json();
  expect(config.cloud.enabled).toBe(false);expect(config.cloud.verification).toBe('mock_contract_only');
  expect(config.cloud.experimental).toBe(true);
  await expect(page.getByLabel('AI 图像模型').locator('option')).toHaveText(['GPT · Codex 登录','Grok · Build 登录']);
  await page.getByText('配置 AI',{exact:true}).click();
  await expect(page.getByRole('button',{name:'检查 GPT 登录'})).toBeVisible();
  await expect(page.getByRole('button',{name:'检查 Grok 登录'})).toBeVisible();
});

test('Qwen key save/reload/clear keeps secrets out of responses and browser storage',async({page})=>{
  const fake='fake-browser-settings-value';let generationRequests=0;
  page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/generations'))generationRequests++;});
  async function open(){await page.getByText('AI 提取',{exact:true}).click();await page.getByText('配置 AI',{exact:true}).click();await page.getByText('千问实验配置（未验证可用）',{exact:true}).click();}
  await page.goto('/');await open();
  const key=page.getByLabel('百炼 API Key');await expect(key).toHaveAttribute('type','password');
  await key.fill(fake);await page.getByRole('button',{name:'保存实验配置',exact:true}).click();
  await expect(page.getByText('实验配置已保存。实验配置已启用（尚未验证可用）',{exact:true})).toBeVisible();
  expect(await (await page.request.get('/api/settings')).text()).not.toContain(fake);
  await page.reload();await open();await expect(key).toHaveValue('');
  await expect(page.getByText('实验配置已启用（尚未验证可用）',{exact:true})).toBeVisible();
  expect(await page.evaluate(()=>JSON.stringify(localStorage))).not.toContain(fake);
  await page.getByRole('button',{name:'清除本机 Key',exact:true}).click();
  await expect(page.getByText('尚未配置 Key，本地提取仍可用',{exact:true})).toBeVisible();expect(generationRequests).toBe(0);
});

test('AI failure shows no download, locks editing while pending and clears consent',async({page})=>{
  await page.route('**/api/providers',route=>route.fulfill({json:{cloud:{enabled:false,models:{},price_checked:'2026-10-15'},connections:{gpt:{installed:true,authenticated:true}},models:[{id:'gpt-image',provider:'gpt',label:'GPT · Codex 登录',account_usage:true}]}}));
  let records:object[]=[];let finish:()=>void=()=>{};const gate=new Promise<void>(resolve=>{finish=resolve;});let posted:Record<string,unknown>|null=null;
  await page.route('**/api/tasks/*/generations',async route=>{
    if(route.request().method()==='GET')return route.fulfill({json:records});
    const body=route.request().postDataJSON();posted=body;await gate;
    records=[{id:body.request_id,source_revision:body.source_revision,model:body.model,provider:'gpt',state:'failed',warning:'模拟失败，无模型请求',error:'登录已失效，请重新登录'}];
    await route.fulfill({status:422,json:{error:{message:'登录已失效，请重新登录'}}});
  });
  await page.goto('/');await page.getByTestId('upload').setInputFiles(path.resolve('../tests/fixtures/synthetic/black_white.png'));
  const local=page.getByRole('button',{name:'生成分割候选',exact:true});await expect(local).toBeEnabled();
  const id=await page.evaluate(()=>localStorage.getItem('print-extractor-task'));const before=await (await page.request.get(`/api/tasks/${id}`)).json();
  await page.getByText('AI 提取',{exact:true}).click();const generate=page.getByRole('button',{name:'开始 AI 提取',exact:true});await expect(generate).toBeDisabled();
  await page.getByLabel('同意上传和使用额度').check();await generate.click();await expect(local).toBeDisabled();
  await expect.poll(()=>posted).not.toBeNull();expect(posted).toMatchObject({model:'gpt-image',allow_upload:true,allow_account_usage:true,source_revision:before.rev});
  finish();await expect(page.getByText('未取得可用结果',{exact:false})).toBeVisible();await expect(local).toBeEnabled();
  await expect(page.getByLabel('同意上传和使用额度')).not.toBeChecked();await expect(page.getByRole('button',{name:'继续精修',exact:true})).toHaveCount(0);
  await expect(page.getByRole('link',{name:'下载透明 PNG ↓'})).toHaveCount(0);expect((await (await page.request.get(`/api/tasks/${id}`)).json()).rev).toBe(before.rev);
});

test('login starts promptly and requires the user on the official page',async({page})=>{
  let state={id:'gpt',installed:true,authenticated:false,state:'signed_out',message:'尚未登录或登录已失效'};
  await page.route('**/api/connections/gpt',route=>route.fulfill({json:state}));
  await page.route('**/api/connections/gpt/login',route=>{state={...state,state:'waiting',message:'请在官方浏览器页面完成登录和授权'};return route.fulfill({json:state});});
  await page.goto('/');await page.getByText('AI 提取',{exact:true}).click();await page.getByText('配置 AI',{exact:true}).click();await page.getByRole('button',{name:'连接 GPT',exact:true}).click();
  await expect(page.getByText('请在官方浏览器页面完成登录和授权',{exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'连接 GPT',exact:true})).toBeDisabled();
});
