#!/usr/bin/env node
"use strict";

const crypto = require("crypto");
const { chromium } = require("/Users/liushanshan/code/QA/bug-finder/node_modules/playwright");

const ENDPOINT = process.env.BI_KNOWLEDGE_CDP || "http://127.0.0.1:9222";
const CATEGORIES = [
  {id:"fcd477a0a8e811ecab26d2d68aa9b120",kind:"feature"},
  {id:"a107b4927f3911ecb3bbe2f4de7a462e",kind:"faq"},
];
const digest = value => `sha256:${crypto.createHash("sha256").update(value).digest("hex")}`;

function score(row, keyword) {
  const terms=keyword.toLowerCase().split(/\s+/).filter(Boolean);
  const title=String(row.title||"").toLowerCase(), summary=String(row.summary||"").toLowerCase();
  return terms.reduce((sum,term)=>sum+(title.includes(term)?10:0)+(summary.includes(term)?3:0),0);
}

async function pageFor(browser, host) {
  const pages=browser.contexts().flatMap(context=>context.pages());
  const page=pages.find(item=>{try{return new URL(item.url()).hostname===host}catch{return false}});
  if(!page)throw new Error(`reauthentication_required: open an authorized ${host} tab`);
  return page;
}

async function lexiangSearch(page, keyword) {
  const rows=await page.evaluate(async categories=>{
    const output=[];
    for(const category of categories)for(let number=1;number<=100;number++){
      const response=await fetch(`/api/v1/docs?filter=category&limit=100&page=${number}&category_id=${category.id}`,{credentials:"same-origin"});
      if(response.status===401||response.status===403)throw new Error("reauthentication_required");
      if(!response.ok)throw new Error(`lexiang_index_http_${response.status}`);
      const value=await response.json();const batch=Array.isArray(value.data)?value.data:[];
      output.push(...batch.map(row=>({id:String(row.id),document_id:String(row.target_id||row.target?.id||row.id),title:row.target?.title||row.name||"",summary:row.target?.summary||"",updated_at:row.edited_at||row.updated_at||null,category_id:category.id,category_kind:category.kind})));
      if(batch.length<100)break;
    }
    return output;
  },CATEGORIES);
  return rows.map(row=>({...row,score:score(row,keyword),source_url:`https://lexiangla.com/docs/${row.id}`})).filter(row=>row.score>0).sort((a,b)=>b.score-a.score||String(b.updated_at).localeCompare(String(a.updated_at))).slice(0,20);
}

async function main(){
  const [command,value]=process.argv.slice(2);if(!command||!value)throw new Error("command and query/document ID are required");
  const browser=await chromium.connectOverCDP(ENDPOINT);
  try{
    let result;
    if(command==="search"){
      const page=await pageFor(browser,"lexiangla.com");
      result={schema_version:"realtime-knowledge-search/1.0",source:"lexiang",query:value,retrieved_at:new Date().toISOString(),results:await lexiangSearch(page,value)};
    }else if(command==="detail"){
      const page=await pageFor(browser,"lexiangla.com");
      const item=await page.evaluate(async id=>{const response=await fetch(`/api/v1/docs/${encodeURIComponent(id)}?lazy_load=1&increment=1`,{credentials:"same-origin"});if(response.status===401||response.status===403)throw new Error("reauthentication_required");if(!response.ok)throw new Error(`lexiang_detail_http_${response.status}`);const result=await response.json();const x=result?.target||result?.data?.target||result?.data||result;return {id,title:x?.title||"",content:x?.md_content||x?.content||x?.summary||"",updated_at:x?.edited_at||x?.updated_at||null};},value);
      result={schema_version:"realtime-knowledge-detail/1.0",source:"lexiang",retrieved_at:new Date().toISOString(),source_url:`https://lexiangla.com/docs/${value}`,...item,content_hash:digest(String(item.content))};
    }else if(command==="kdocs-search"){
      const page=await pageFor(browser,"365.kdocs.cn");
      const item=await page.evaluate(async keyword=>{
        const workspace=document.querySelector(".thumbnail_workspace");
        const original=workspace?.scrollTop||0;const slides=new Map();
        const collect=()=>document.querySelectorAll(".thumbnail_slide").forEach(node=>{const text=(node.innerText||"").trim();const page=(node.querySelector(".page_index")?.textContent||text.split(/\n/)[0]||"").trim();if(text.length>page.length)slides.set(page,text);});
        if(workspace){for(let top=0;top<=workspace.scrollHeight;top+=Math.max(300,workspace.clientHeight)){workspace.scrollTop=top;await new Promise(resolve=>setTimeout(resolve,80));collect();}workspace.scrollTop=original;}else collect();
        const terms=keyword.toLowerCase().split(/\s+/).filter(Boolean);
        return {title:document.title,url:location.href,slides:[...slides].map(([page,text])=>({page,text})).filter(item=>terms.some(term=>item.text.toLowerCase().includes(term))).slice(0,30)};
      },value);
      result={schema_version:"realtime-knowledge-search/1.0",source:"kdocs",query:value,retrieved_at:new Date().toISOString(),title:item.title,source_url:item.url,results:item.slides.map(item=>({...item,snippet_hash:digest(item.text)}))};
    }else throw new Error(`unsupported command: ${command}`);
    process.stdout.write(`${JSON.stringify(result,null,2)}\n`);
  }finally{await browser.close()}
}
main().catch(error=>{process.stderr.write(`${String(error.message||error)}\n`);process.exit(1)});
