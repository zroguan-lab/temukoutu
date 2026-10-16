import {test,expect} from '@playwright/test';
import path from 'node:path';
import fs from 'node:fs';

// Optional real-file replay: no new generation or account/API spend.
const manifest=process.env.PRINT_EXTRACTOR_GENERATED_FIXTURES;
for(const provider of ['gpt','grok'])test(`${provider} existing real output → preview → refine → brush → PNG → original record`,async({page})=>{
  test.skip(!manifest,'Set PRINT_EXTRACTOR_GENERATED_FIXTURES to seeded real-result task metadata.');
  const fixture=JSON.parse(fs.readFileSync(manifest!,'utf8'))[provider];
  let generationPosts=0;page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/generations'))generationPosts++;});
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/');await page.evaluate(id=>localStorage.setItem('print-extractor-task',id),fixture.task_id);await page.reload();
  const loaded=()=>expect(page.getByRole('button',{name:'生成分割候选',exact:true})).toBeEnabled();await loaded();
  await page.getByText('AI 提取',{exact:true}).click();
  const record=page.getByTestId('generation');await expect(record).toHaveCount(1);
  await expect(record.getByRole('img')).toBeVisible();
  await expect(record.getByRole('link')).toHaveText(provider==='gpt'?'下载透明候选（需检查）':'下载生成原图（JPG，非透明）');
  await page.screenshot({path:path.resolve(`../artifacts/ui-acceptance/${provider}-generation.png`),fullPage:true});
  const original=await (await page.request.get(`/api/tasks/${fixture.task_id}/generations/${fixture.generation_id}/image`)).body();
  await record.getByRole('button',{name:'继续精修',exact:true}).click();await loaded();
  const refined=await page.evaluate(()=>localStorage.getItem('print-extractor-task'));expect(refined).not.toBe(fixture.task_id);
  const metadata=await (await page.request.get(`/api/tasks/${refined}`)).json();expect(metadata.provenance.task_id).toBe(fixture.task_id);expect(metadata.ai_used).toBe(true);
  if(provider==='grok'){
    await expect(page.getByRole('button',{name:'验证并导出 RGBA PNG ↗',exact:true})).toBeDisabled();
    await page.getByLabel('分割算法').selectOption('color');await page.getByRole('button',{name:'生成分割候选',exact:true}).click();await loaded();
  }
  for(const bg of ['白底','黑底','棋盘格'])await page.getByRole('button',{name:bg,exact:true}).click();
  await page.getByRole('button',{name:'擦除画笔',exact:true}).click();
  const editor=page.getByTestId('editor');await editor.scrollIntoViewIfNeeded();const box=(await editor.boundingBox())!;
  await page.mouse.click(box.x+box.width*.5,box.y+box.height*.4);await loaded();
  await page.getByRole('button',{name:'撤销',exact:true}).click();await loaded();
  await page.getByRole('button',{name:'验证并导出 RGBA PNG ↗',exact:true}).click();
  const link=page.getByRole('link',{name:'下载透明 PNG ↓'});await expect(link).toBeVisible();
  const downloading=page.waitForEvent('download');await link.click();await (await downloading).saveAs(path.resolve(`../artifacts/ui-acceptance/${provider}-refined.png`));
  await page.screenshot({path:path.resolve(`../artifacts/ui-acceptance/${provider}-refined-workbench.png`),fullPage:true});
  await page.reload();await loaded();await expect(link).toBeVisible();
  await page.getByRole('button',{name:'返回商品图与生成记录',exact:true}).click();await loaded();
  expect(await page.evaluate(()=>localStorage.getItem('print-extractor-task'))).toBe(fixture.task_id);
  await page.getByText('AI 提取',{exact:true}).click();await expect(page.getByTestId('generation')).toHaveCount(1);
  const after=await (await page.request.get(`/api/tasks/${fixture.task_id}/generations/${fixture.generation_id}/image`)).body();expect(after.equals(original)).toBe(true);
  expect(generationPosts).toBe(0);expect(errors).toEqual([]);
});
