#!/usr/bin/env python3
"""Capture a Lexiang category through a visible authenticated Chrome tab."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from datetime import datetime, timezone

from browser_snapshot import capture


JS = r"""JSON.stringify((()=>{
const category=new URL(location.href).searchParams.get('category_id');
if(!category)return {error:'category_id_missing',effective_url:location.href};
if(location.hostname!=='lexiangla.com')return {error:'authentication_required',effective_url:location.href};
const teams=[...(document.documentElement.innerHTML.matchAll(/k\d{6,}/g))].map(x=>x[0]);
const team=[...new Set(teams)][0];
if(!team)return {error:'team_id_not_discoverable',effective_url:location.href};
const unwrap=x=>{if(Array.isArray(x))return x;for(const k of ['data','list','items','targets','docs']){if(Array.isArray(x?.[k]))return x[k];if(x?.[k]&&typeof x[k]==='object'){const y=unwrap(x[k]);if(y.length)return y;}}return []};
const getJson=u=>{const x=new XMLHttpRequest();x.open('GET',u,false);x.withCredentials=true;x.send();if(x.status<200||x.status>=300)throw new Error(`http_${x.status}`);return JSON.parse(x.responseText)};
let rows=[];
for(let page=1;page<=100;page++){
 const u=`/api/v1/teams/${team}/docs?filter=node&parent_id=${category}&order=weight,-edited_at&limit=100&page=${page}`;
 let batch;try{batch=unwrap(getJson(u))}catch(e){return {error:`list_${String(e)}`,effective_url:location.href}};rows.push(...batch);if(batch.length<100)break;
}
const ids=[...new Set(rows.map(x=>x?.target?.id||x?.id||x?.doc_id).filter(Boolean))];
const pages=[];const failures=[];
for(const id of ids){
 try{const j=getJson(`/api/v1/teams/${team}/docs/${id}?lazy_load=1&increment=1`);const t=j?.target||j?.data?.target||j?.data||j;pages.push({id:String(id),title:t?.title||'',summary:t?.summary||'',content:t?.md_content||t?.content||'',edited_at:t?.edited_at||t?.updated_at||null});}catch(e){failures.push({id,error:String(e)})}
}
return {effective_url:location.href,category_id:category,team_id:team,index_count:ids.length,pages,failures};
})())"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    parsed = urlparse(args.url)
    if parsed.scheme != "https" or parsed.hostname != "lexiangla.com" or not parse_qs(parsed.query).get("category_id"):
        raise SystemExit("unapproved Lexiang category URL")
    value = capture(args.url, JS, wait_seconds=5)
    if value.get("error"):
        raise RuntimeError(str(value["error"]))
    pages = value.get("pages", [])
    failures = value.get("failures", [])
    if not pages or failures or len(pages) != value.get("index_count"):
        raise RuntimeError(f"partial Lexiang capture: pages={len(pages)} failures={len(failures)} index={value.get('index_count')}")
    for page in pages:
        content = str(page.get("content", ""))
        page["content_hash"] = "sha256:" + hashlib.sha256(content.encode()).hexdigest()
        page["source_url"] = f"https://lexiangla.com/docs/{page['id']}"
    snapshot = {
        "schema_version": "lexiang-category-snapshot/1.0",
        "source_url": args.url,
        "category_id": value["category_id"],
        "team_id": value["team_id"],
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "page_count": len(pages),
        "pages": pages,
    }
    canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    snapshot["manifest_hash"] = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"page_count": len(pages), "manifest_hash": snapshot["manifest_hash"]}))


if __name__ == "__main__":
    main()
