"""Server-rendered admin console (no build step, ships in the wheel).

`render_admin_page()` returns a single self-contained HTML document, styled to
match the yohakuforce docs (paper/crimson theme), in Japanese, with per-field
guidance (なぜ必要 / 取得手順 / 設定方法). All data is loaded at runtime from the
JSON API using the API key the user enters (stored in the browser and sent as
``X-Api-Key``). Secrets are shown masked — full values never leave the server.

Tabs: 設定 (Settings) / ソース (Sources) / 状態 (Status).
"""

from __future__ import annotations

_PAGE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Context-Hub · 設定</title>
<style>
  :root{
    --ink:#0b0b0c; --ink-soft:#2a2a2e; --paper:#fbfaf8; --paper-2:#f2efea;
    --line:#e4ded5; --line-ink:#23232a; --crimson:#b51b2e; --crimson-d:#8c1322;
    --earth:#7c6a55; --muted:#6f6a62; --muted-2:#9a948b; --ok:#1f7a3d;
    --maxw:980px; --r:3px; --t:200ms cubic-bezier(.4,0,.2,1);
    --serif:"Hiragino Mincho ProN","Yu Mincho","Noto Serif JP",Georgia,serif;
    --sans:-apple-system,BlinkMacSystemFont,"Hiragino Sans","Noto Sans JP","Segoe UI",sans-serif;
    --mono:"SF Mono","JetBrains Mono","Roboto Mono","Noto Sans Mono",monospace;
  }
  *{box-sizing:border-box;}
  body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);
       font-size:15px;line-height:1.8;letter-spacing:.01em;-webkit-font-smoothing:antialiased;}
  a{color:var(--crimson-d);word-break:break-all;}
  code{font-family:var(--mono);font-size:.86em;background:var(--paper-2);padding:1px 6px;
       border-radius:var(--r);color:var(--crimson-d);}
  header{position:sticky;top:0;z-index:50;background:rgba(251,250,248,.9);
         backdrop-filter:saturate(140%) blur(12px);border-bottom:1px solid var(--line);}
  .bar{max-width:var(--maxw);margin:0 auto;display:flex;align-items:center;gap:18px;
       padding:0 24px;height:60px;flex-wrap:wrap;}
  .mark{font-family:var(--serif);font-size:20px;font-weight:600;letter-spacing:.04em;
        position:relative;padding-left:15px;}
  .mark::before{content:"";position:absolute;left:0;top:50%;transform:translateY(-50%);
        width:5px;height:21px;background:var(--crimson);}
  .mark .en{font-size:10px;letter-spacing:.24em;text-transform:uppercase;color:var(--muted-2);
        display:block;padding-left:0;line-height:1;margin-top:2px;}
  .sp{flex:1;}
  input,select{background:#fff;color:var(--ink);border:1px solid var(--line);border-radius:var(--r);
       padding:8px 11px;font:inherit;}
  input:focus,select:focus{outline:none;border-color:var(--ink);}
  input[readonly]{background:var(--paper-2);color:var(--muted);}
  .keybox{display:flex;gap:8px;align-items:center;}
  .keybox input{width:240px;}
  button{font-family:var(--sans);cursor:pointer;border-radius:var(--r);font-size:.85rem;
         padding:9px 16px;border:1px solid var(--line);background:#fff;color:var(--ink-soft);}
  button:hover{border-color:var(--ink);}
  button.primary{background:var(--ink);color:#fff;border-color:var(--ink);font-weight:600;letter-spacing:.03em;}
  button.primary:hover{background:var(--crimson-d);border-color:var(--crimson-d);}
  button.danger{color:var(--crimson-d);border-color:var(--line);}
  button.danger:hover{border-color:var(--crimson-d);}
  button:disabled{opacity:.45;cursor:not-allowed;}
  nav{max-width:var(--maxw);margin:0 auto;padding:14px 24px 0;display:flex;gap:2px;
      border-bottom:1px solid var(--line);}
  nav a{cursor:pointer;background:none;border:0;border-bottom:2px solid transparent;
        color:var(--muted);padding:9px 16px;margin-bottom:-1px;text-align:center;}
  nav a .jp{display:block;font-weight:600;font-size:13.5px;letter-spacing:.03em;}
  nav a .en{display:block;font-size:9px;letter-spacing:.18em;text-transform:uppercase;
        color:var(--muted-2);margin-top:1px;}
  nav a:hover{color:var(--ink);}
  nav a.active{color:var(--ink);border-bottom-color:var(--crimson);}
  main{max-width:var(--maxw);margin:0 auto;padding:24px;}
  h2{font-family:var(--serif);font-weight:600;font-size:18px;margin:0;letter-spacing:.02em;}
  .lead{color:var(--ink-soft);font-size:14px;margin:0 0 18px;}
  .muted{color:var(--muted);}
  .note{border:1px solid var(--line);border-left:3px solid var(--earth);background:#fff;
        padding:14px 18px;border-radius:var(--r);margin:0 0 18px;font-size:13.5px;color:var(--ink-soft);}
  .note.boundary{border-left-color:var(--crimson);}
  .note b{color:var(--ink);}
  .group{background:#fff;border:1px solid var(--line);border-radius:var(--r);margin:0 0 16px;overflow:hidden;}
  .group>h3{font-size:12px;letter-spacing:.1em;color:var(--muted);font-weight:700;margin:0;
        padding:12px 16px;border-bottom:1px solid var(--line);text-transform:uppercase;background:var(--paper);}
  .field{padding:14px 16px;border-bottom:1px solid var(--line);}
  .field:last-child{border-bottom:0;}
  .field .head{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;margin-bottom:7px;}
  .field .lab{font-weight:600;font-size:14px;}
  .field .env{font-family:var(--mono);font-size:10.5px;color:var(--muted-2);}
  .badge{font-size:10.5px;font-weight:700;letter-spacing:.03em;border:1px solid var(--line);
        border-radius:100px;padding:1px 9px;color:var(--muted);white-space:nowrap;}
  .badge.rr{color:var(--crimson-d);border-color:#e7c9cd;}
  .ctl{display:flex;gap:8px;align-items:center;flex-wrap:wrap;}
  .ctl input,.ctl select{flex:1;min-width:200px;}
  .help{font-size:12.5px;color:var(--muted);margin-top:6px;}
  .state{font-size:11px;}
  .state.set{color:var(--ok);} .state.unset{color:var(--muted-2);}
  details.guide{margin:9px 0 0;border:1px solid var(--line);border-radius:var(--r);background:var(--paper);}
  details.guide>summary{cursor:pointer;font-size:12.5px;color:var(--crimson-d);padding:8px 12px;list-style:none;}
  details.guide>summary::-webkit-details-marker{display:none;}
  details.guide>summary::before{content:"▸ ";}
  details.guide[open]>summary::before{content:"▾ ";}
  details.guide[open]>summary{border-bottom:1px solid var(--line);font-weight:700;}
  .gbody{padding:11px 14px;font-size:13px;color:var(--ink-soft);line-height:1.85;}
  .gbody b{color:var(--ink);} .gbody ol{margin:6px 0;padding-left:20px;} .gbody li{margin:4px 0;}
  .gbody .lbl{font-weight:700;color:var(--ink);}
  .row{display:flex;gap:10px;align-items:center;margin:0 0 16px;flex-wrap:wrap;}
  /* sources */
  .card{background:#fff;border:1px solid var(--line);border-radius:var(--r);margin:0 0 16px;overflow:hidden;}
  .card>h3{margin:0;padding:12px 16px;border-bottom:1px solid var(--line);display:flex;
        align-items:center;gap:10px;font-size:14px;font-family:var(--serif);font-weight:600;background:var(--paper);}
  .card>h3 .id{font-family:var(--mono);font-size:11px;color:var(--muted-2);}
  .src{display:grid;grid-template-columns:96px 64px 92px 1fr auto auto auto;gap:10px;
       align-items:center;padding:10px 16px;border-bottom:1px solid var(--line);}
  .src:last-child{border-bottom:0;}
  .src .t{font-weight:600;} .src input[type=number]{width:64px;min-width:0;}
  .src input[type=text]{min-width:0;}
  .kv{display:grid;grid-template-columns:220px 1fr;gap:10px;padding:11px 16px;border-bottom:1px solid var(--line);}
  .kv:last-child{border-bottom:0;} .kv .k{color:var(--muted);} .ok{color:var(--ok);} .bad{color:var(--crimson-d);}
  #toast{position:fixed;right:20px;bottom:20px;max-width:460px;background:#fff;border:1px solid var(--line);
        border-left:3px solid var(--crimson);border-radius:var(--r);padding:13px 16px;display:none;
        box-shadow:0 6px 24px rgba(0,0,0,.08);font-size:13.5px;}
  .hidden{display:none;}
  @media(max-width:720px){ .field .head{align-items:flex-start;} .kv{grid-template-columns:1fr;}
    .src{grid-template-columns:1fr 1fr;} }
</style>
</head>
<body>
<header>
  <div class="bar">
    <div class="mark">Context-Hub<span class="en">Admin Console</span></div>
    <span class="sp"></span>
    <div class="keybox">
      <input id="apikey" type="password" placeholder="ADMIN API キー" autocomplete="off">
      <button id="savekey">キーを使う</button>
    </div>
  </div>
</header>
<nav>
  <a data-tab="settings" class="active"><span class="jp">設定</span><span class="en">Settings</span></a>
  <a data-tab="sources"><span class="jp">ソース</span><span class="en">Sources</span></a>
  <a data-tab="status"><span class="jp">状態</span><span class="en">Status</span></a>
</nav>
<main>
  <p class="lead" id="intro">右上に <b>ADMIN API キー</b> を入力して「キーを使う」を押すと設定を読み込みます。
    外部連携の多くは任意です。やりたいことに応じて必要な項目だけ設定してください。各項目の
    「<b>なぜ必要？ 取得・設定の手順</b>」を開くと、取得元のURLと手順が出ます。
    シークレットは末尾4桁のみ表示され、<b>「変更」を押したときだけ</b>新しい値を入力できます。</p>

  <section id="tab-settings">
    <div id="form"></div>
    <div class="row">
      <button class="primary" id="save" disabled>変更を保存</button>
      <button id="reload" disabled>再読み込み</button>
    </div>
  </section>

  <section id="tab-sources" class="hidden">
    <div class="note">プロジェクトごとに、取り込むソース（Slack / Backlog / Redmine / Gmail）を
      有効化・設定します。<b>トークンやキーは「設定」タブ</b>で入れ、ここでは<b>どのソースを使うか・
      同期間隔・チャンネルID/プロジェクトキー</b>を決めます。各行の「テスト」で疎通確認できます。</div>
    <div class="row">
      <input id="newproj" placeholder="新しいプロジェクト名" style="flex:1;min-width:220px">
      <button class="primary" id="createproj">プロジェクト作成</button>
      <button id="reloadproj">再読み込み</button>
    </div>
    <div id="projects"></div>
  </section>

  <section id="tab-status" class="hidden">
    <div class="row"><button id="reloadstatus">状態を再取得</button></div>
    <div id="status"></div>
  </section>
</main>
<div id="toast"></div>
<script>
const $ = s => document.querySelector(s);
const KEYNAME = "ch_admin_key";
const apiKey = () => localStorage.getItem(KEYNAME) || "";
const setKey = k => localStorage.setItem(KEYNAME, k);
let CURRENT = [];
const SRC_TYPES = ["slack", "backlog", "redmine", "email"];
const SRC_LABEL = { slack:"Slack", backlog:"Backlog", redmine:"Redmine", email:"Gmail" };

function esc(s){ return (s==null?"":String(s)).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function linkify(s){ return esc(s).replace(/(https?:\/\/[^\s「」、。]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>'); }
function toast(msg, ok=true){
  const t=$("#toast"); t.innerHTML=msg; t.style.borderLeftColor = ok ? "var(--crimson)" : "var(--crimson-d)";
  t.style.display="block"; clearTimeout(t._h); t._h=setTimeout(()=>{t.style.display="none";},7000);
}
async function api(method, path, body){
  const res = await fetch(path, { method,
    headers:{ "X-Api-Key":apiKey(), "Content-Type":"application/json" },
    body: body ? JSON.stringify(body) : undefined });
  const data = await res.json().catch(()=>({}));
  if(!res.ok) throw new Error((data.error && data.error.message) || ("HTTP "+res.status));
  return data.data !== undefined ? data.data : data;
}

/* ---------- 設定 (Settings) ---------- */
function guideHtml(f){
  if(!f.why && !(f.steps&&f.steps.length) && !f.howToSet) return "";
  let body = "";
  if(f.why) body += `<p><span class="lbl">なぜ必要：</span>${linkify(f.why)}</p>`;
  if(f.steps && f.steps.length){
    body += `<p class="lbl">取得手順：</p><ol>` + f.steps.map(s=>`<li>${linkify(s)}</li>`).join("") + `</ol>`;
  }
  if(f.howToSet) body += `<p><span class="lbl">設定方法：</span>${linkify(f.howToSet)}</p>`;
  return `<details class="guide"><summary>なぜ必要？ 取得・設定の手順</summary><div class="gbody">${body}</div></details>`;
}
function ctlFor(f){
  if(f.kind==="select" || f.kind==="bool"){
    const opts = f.kind==="bool" ? ["true","false"] : f.options;
    const cur = (f.value||"").toLowerCase();
    return `<select data-env="${f.env}">` + opts.map(o =>
      `<option value="${esc(o)}"${(!f.secret && cur===o.toLowerCase())?" selected":""}>${esc(o)}</option>`).join("") + `</select>`;
  }
  if(f.secret){
    const ph = f.configured ? esc(f.value) : "未設定";
    return `<input data-env="${f.env}" data-secret="1" type="password" value="" placeholder="${ph}" readonly>
            <button type="button" data-edit="${f.env}">変更</button>`;
  }
  const type = f.kind==="int" ? "number" : "text";
  return `<input data-env="${f.env}" type="${type}" value="${esc(f.value)}">`;
}
function renderSettings(fields){
  CURRENT = fields; const groups={};
  for(const f of fields)(groups[f.group]=groups[f.group]||[]).push(f);
  const root=$("#form"); root.innerHTML="";
  for(const [group,list] of Object.entries(groups)){
    let inner = "";
    for(const f of list){
      const tag = f.tag ? `<span class="badge">${esc(f.tag)}</span>` : "";
      const rr = f.restartRequired ? `<span class="badge rr">要再起動</span>` : "";
      const st = f.configured ? `<span class="state set">● 設定済み</span>` : `<span class="state unset">○ 未設定</span>`;
      inner += `<div class="field">
        <div class="head"><span class="lab">${esc(f.label)}</span><span class="env">${esc(f.env)}</span>${tag}${rr}<span class="sp"></span>${st}</div>
        <div class="ctl">${ctlFor(f)}</div>
        ${f.help?`<div class="help">${esc(f.help)}</div>`:""}
        ${guideHtml(f)}
      </div>`;
    }
    const box=document.createElement("div"); box.className="group";
    box.innerHTML=`<h3>${esc(group)}</h3>${inner}`; root.appendChild(box);
  }
  root.querySelectorAll("[data-edit]").forEach(btn=>btn.onclick=()=>{
    const inp = root.querySelector(`input[data-env="${btn.dataset.edit}"]`);
    if(inp.hasAttribute("readonly")){ inp.removeAttribute("readonly"); inp.value=""; inp.placeholder="新しい値を入力（保存で更新）"; inp.focus(); btn.textContent="取消"; }
    else { inp.setAttribute("readonly","readonly"); inp.value=""; const f=CURRENT.find(x=>x.env===btn.dataset.edit); inp.placeholder=f&&f.configured?f.value:"未設定"; btn.textContent="変更"; }
  });
  $("#save").disabled=false; $("#reload").disabled=false;
}
function collectUpdates(){
  const byEnv=Object.fromEntries(CURRENT.map(f=>[f.env,f]));
  const updates={};
  for(const el of document.querySelectorAll("#form [data-env]")){
    const f=byEnv[el.dataset.env]; if(!f) continue;
    if(f.secret){ if(!el.hasAttribute("readonly") && el.value!=="") updates[f.env]=el.value; }
    else if(el.value !== (f.value||"")) updates[f.env]=el.value;
  }
  return updates;
}
async function loadSettings(){
  if(!apiKey()) return toast("先に API キーを入力してください", false);
  try{ renderSettings((await api("GET","/api/v1/config")).fields); }
  catch(e){ toast("読み込み失敗: "+e.message, false); }
}
async function saveSettings(){
  const updates=collectUpdates();
  if(!Object.keys(updates).length) return toast("変更はありません");
  try{
    const r=await api("PUT","/api/v1/config",{updates});
    let m=`保存しました（更新 ${r.changed.length} 件 / 削除 ${r.cleared.length} 件）。`;
    if(r.restartRequired.length) m+=` <b>要再起動</b>: ${r.restartRequired.join(", ")}`;
    if(r.rejected.length) m+=` 無効キー: ${r.rejected.join(", ")}`;
    toast(m, r.rejected.length===0); loadSettings();
  }catch(e){ toast("保存失敗: "+e.message, false); }
}

/* ---------- ソース (Sources) ---------- */
function extraField(type,c){
  if(type==="slack") return `<input type="text" data-k="channelIds" placeholder="チャンネルID（カンマ区切り）" value="${esc((c&&c.channelIds||[]).join(','))}">`;
  if(type==="backlog") return `<input type="text" data-k="backlogProjectKey" placeholder="プロジェクトキー" value="${esc(c&&c.backlogProjectKey||'')}">`;
  if(type==="redmine") return `<input type="text" data-k="redmineProjectIdentifier" placeholder="プロジェクト識別子" value="${esc(c&&c.redmineProjectIdentifier||'')}">`;
  return `<span class="muted">ラベル方式（Gmail）</span>`;
}
function renderProjects(projects){
  const root=$("#projects"); root.innerHTML="";
  if(!projects.length){ root.innerHTML='<p class="muted">プロジェクトがありません。上で作成してください。</p>'; return; }
  for(const p of projects){
    const byType=Object.fromEntries(p.sources.map(s=>[s.sourceType,s]));
    let rows="";
    for(const t of SRC_TYPES){
      const c=byType[t];
      rows+=`<div class="src" data-type="${t}">
        <span class="t">${SRC_LABEL[t]}</span>
        <label><input type="checkbox" data-k="isEnabled" ${c&&c.isEnabled?"checked":""}> 有効</label>
        <input type="number" data-k="syncIntervalMinutes" min="5" value="${c?c.syncIntervalMinutes:15}" title="同期間隔（分）">
        ${extraField(t,c)}
        <button data-act="savesrc">保存</button>
        <button data-act="testsrc">テスト</button>
        <button class="danger" data-act="delsrc" ${c?"":"disabled"}>削除</button>
      </div>`;
    }
    const card=document.createElement("div"); card.className="card"; card.dataset.pid=p.id;
    card.innerHTML=`<h3>${esc(p.name)} <span class="id">${esc(p.id.slice(0,8))}…</span><span class="sp" style="flex:1"></span>
      <button class="danger" data-act="delproj">プロジェクト削除</button></h3>${rows}`;
    root.appendChild(card);
  }
}
async function loadProjects(){
  if(!apiKey()) return toast("先に API キーを入力してください", false);
  try{ renderProjects(await api("GET","/api/v1/projects/detailed")); }
  catch(e){ toast("読み込み失敗: "+e.message, false); }
}
function readSrcRow(row){
  const body={ isEnabled: row.querySelector('[data-k=isEnabled]').checked,
    syncIntervalMinutes: parseInt(row.querySelector('[data-k=syncIntervalMinutes]').value||"15",10) };
  const ch=row.querySelector('[data-k=channelIds]'); if(ch) body.channelIds=ch.value.split(",").map(s=>s.trim()).filter(Boolean);
  const bk=row.querySelector('[data-k=backlogProjectKey]'); if(bk) body.backlogProjectKey=bk.value||null;
  const ri=row.querySelector('[data-k=redmineProjectIdentifier]'); if(ri) body.redmineProjectIdentifier=ri.value||null;
  return body;
}
async function onProjectsClick(e){
  const act=e.target.dataset.act; if(!act) return;
  const card=e.target.closest(".card"); const pid=card.dataset.pid;
  try{
    if(act==="delproj"){ if(!confirm("このプロジェクトを削除しますか？")) return;
      await api("DELETE",`/api/v1/projects/${pid}`); toast("プロジェクトを削除しました"); }
    else if(act==="savesrc"){ const row=e.target.closest(".src");
      await api("PUT",`/api/v1/projects/${pid}/sources/${row.dataset.type}`, readSrcRow(row));
      toast(`${SRC_LABEL[row.dataset.type]} を保存しました（自動同期へ反映するには serve 再起動）`); }
    else if(act==="delsrc"){ const row=e.target.closest(".src");
      await api("DELETE",`/api/v1/projects/${pid}/sources/${row.dataset.type}`); toast("ソースを削除しました"); }
    else if(act==="testsrc"){ const type=e.target.closest(".src").dataset.type;
      const probe=type==="email"?"gmail":type;
      const r=await api("POST",`/api/v1/config/test/${probe}`);
      toast((r.ok?"✅ OK":"❌ 失敗")+" · "+esc(r.detail)+(r.live?"（実接続）":""), r.ok); return; }
    loadProjects();
  }catch(err){ toast("失敗: "+err.message, false); }
}
async function createProject(){
  const name=$("#newproj").value.trim(); if(!name) return toast("名前を入力してください", false);
  try{ await api("POST","/api/v1/projects",{name}); $("#newproj").value=""; toast("プロジェクトを作成しました"); loadProjects(); }
  catch(e){ toast("作成失敗: "+e.message, false); }
}

/* ---------- 状態 (Status) ---------- */
function kv(k,v,cls){ return `<div class="kv"><span class="k">${esc(k)}</span><span class="${cls||''}">${v}</span></div>`; }
function renderStatus(s){
  const projects = s.projects.map(p =>
    `<div class="kv"><span class="k">${esc(p.name)}</span><span>${p.enabledSources.length?esc(p.enabledSources.join(", ")):'<span class="muted">有効ソースなし</span>'}</span></div>`).join("");
  $("#status").innerHTML =
    `<div class="card"><h3>システム</h3>
       ${kv("プロファイル", esc(s.profile))}
       ${kv("取り込みモード", esc(s.ingestMode))}
       ${kv("スケジューラ", esc(s.schedulerBackend))}
       ${kv("serve中の自動同期", s.sourceSyncEnabled?"ON":"OFF", s.sourceSyncEnabled?"ok":"bad")}
       ${kv("意味（ベクトル）検索", s.vectorSearchAvailable?"利用可":"FTS-onlyに縮退中", s.vectorSearchAvailable?"ok":"bad")}
       ${kv("Inbox フォルダ", s.inboxDir?esc(s.inboxDir):'<span class="muted">未設定</span>')}
     </div>
     <div class="card"><h3>プロジェクト（${s.projectCount}）</h3>
       ${projects || '<div class="kv"><span class="muted">プロジェクトなし</span></div>'}
     </div>`;
}
async function loadStatus(){
  if(!apiKey()) return toast("先に API キーを入力してください", false);
  try{ renderStatus(await api("GET","/api/v1/status")); }
  catch(e){ toast("状態取得失敗: "+e.message, false); }
}

/* ---------- タブ + 配線 ---------- */
function showTab(tab){
  for(const a of document.querySelectorAll("nav a")) a.classList.toggle("active", a.dataset.tab===tab);
  $("#tab-settings").classList.toggle("hidden", tab!=="settings");
  $("#tab-sources").classList.toggle("hidden", tab!=="sources");
  $("#tab-status").classList.toggle("hidden", tab!=="status");
  if(!apiKey()) return;
  if(tab==="settings") loadSettings(); else if(tab==="sources") loadProjects(); else loadStatus();
}
document.querySelectorAll("nav a").forEach(a => a.onclick = () => showTab(a.dataset.tab));
$("#savekey").onclick = () => { setKey($("#apikey").value.trim()); toast("キーを保存しました"); showTab("settings"); };
$("#save").onclick = saveSettings;
$("#reload").onclick = loadSettings;
$("#createproj").onclick = createProject;
$("#reloadproj").onclick = loadProjects;
$("#reloadstatus").onclick = loadStatus;
$("#projects").addEventListener("click", onProjectsClick);
window.addEventListener("DOMContentLoaded", () => { if(apiKey()){ $("#apikey").value=apiKey(); loadSettings(); } });
</script>
</body>
</html>
"""


def render_admin_page() -> str:
    """Return the complete admin console HTML document."""
    return _PAGE
