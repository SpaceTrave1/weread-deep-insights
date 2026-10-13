/* Local-only interactions. Untrusted note/model text is never inserted as HTML. */
(() => {
  'use strict';
  const data = JSON.parse(document.getElementById('journal-data').textContent);
  const panels = [...document.querySelectorAll('.panel')];
  const moduleNames = {overview:'阅读总览',map:'阅读地图',notes:'笔记与表达',thinking:'我的思考',inspiration:'阅读启发',coverage:'数据与证据范围'};
  let currentRoute = '';
  function route(focus = false) {
    const hash = location.hash.slice(1);
    const target = document.getElementById(hash);
    const name = hash === 'main' ? currentRoute || 'overview' : Object.hasOwn(moduleNames, hash) ? hash : target?.closest('.panel')?.id || 'overview';
    panels.forEach(p => p.hidden = p.id !== name);
    document.querySelectorAll('.sidebar [data-route]').forEach(a => {
      if (a.dataset.route === name) a.setAttribute('aria-current', 'page');
      else a.removeAttribute('aria-current');
    });
    document.getElementById('current-module').textContent = moduleNames[name];
    if (name !== currentRoute) {
      if (focus) {document.getElementById('main').focus({preventScroll:true}); window.scrollTo({top:0,behavior:'instant'});}
      currentRoute = name;
    }
    if (target?.classList.contains('archive')) {setThinkingView('time');const extra=target.closest('.extra-archives');if(extra)extra.open=true;target.scrollIntoView({block:'start',behavior:'instant'});}
  }
  window.addEventListener('hashchange', () => route(true));
  document.querySelectorAll('[data-route]').forEach(a => a.addEventListener('click', event => {
    if (location.hash === '#' + a.dataset.route) {event.preventDefault();window.scrollTo({top:0,behavior:'instant'});}
  }));

  const tabs = [...document.querySelectorAll('[data-thinking-view]')];
  function setThinkingView(name, focus = false) {
    tabs.forEach(tab => {
      const selected = tab.dataset.thinkingView === name;
      tab.classList.toggle('active', selected);
      tab.setAttribute('aria-selected', String(selected));
      tab.tabIndex = selected ? 0 : -1;
      if (selected && focus) tab.focus();
    });
    document.getElementById('theme-view').hidden = name !== 'theme';
    document.getElementById('time-view').hidden = name !== 'time';
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => setThinkingView(tab.dataset.thinkingView));
    tab.addEventListener('keydown', event => {
      if (['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) {
        event.preventDefault();
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length-1 : (index+1)%tabs.length;
        setThinkingView(tabs[next].dataset.thinkingView, true);
      }
    });
  });
  document.querySelectorAll('[data-open-archive]').forEach(button => button.addEventListener('click', () => {
    relationType = 'all';
    document.getElementById('archive-search').value = '';
    document.querySelectorAll('[data-relation]').forEach(b => {const active = b.dataset.relation === 'all'; b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});
    filterArchives();
    setThinkingView('time');
    location.hash = button.dataset.openArchive;
    const archive = document.getElementById(button.dataset.openArchive);
    const extra=archive.closest('.extra-archives');if(extra)extra.open=true;
    archive.scrollIntoView({block:'start'});
  }));
  let relationType = 'all';
  const archives = [...document.querySelectorAll('.archive')];
  function filterArchives() {
    const word = document.getElementById('archive-search').value.trim().toLocaleLowerCase();
    let count = 0;
    archives.forEach(card => {
      const match = (relationType === 'all' || card.dataset.types.split(' ').includes(relationType)) && card.textContent.toLocaleLowerCase().includes(word);
      card.hidden = !match;
      if (match) count++;
      if(match && (word || relationType !== 'all')) {const extra=card.closest('.extra-archives');if(extra)extra.open=true;}
      card.querySelectorAll('.comparison').forEach(row => row.hidden = relationType !== 'all' && row.dataset.relation !== relationType);
    });
    document.getElementById('archive-count').textContent = `${count} / ${archives.length} 个问题档案`;
    document.getElementById('archive-empty').hidden = count !== 0;
  }
  document.querySelectorAll('[data-relation]').forEach(button => button.addEventListener('click', () => {
    relationType = button.dataset.relation;
    document.querySelectorAll('[data-relation]').forEach(b => {const active=b===button;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});
    filterArchives();
  }));
  document.getElementById('archive-search').addEventListener('input', filterArchives);
  document.querySelectorAll('[data-chart]').forEach(button => button.addEventListener('click', () => {
    const mode = button.dataset.chart;
    document.querySelectorAll('[data-chart]').forEach(b => {const active=b===button;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});
    const bars = [...document.querySelectorAll('.annual-bar')];
    const max = Math.max(...bars.map(b => Number(b.dataset[mode])), 1);
    bars.forEach(bar => {bar.style.height = `${Number(bar.dataset[mode])/max*100}%`;bar.closest('.annual-col').querySelector('.annual-value').textContent = bar.dataset[mode];});
    document.getElementById('chart-caption').textContent = `单位：${mode==='hours'?'小时':'有效阅读天数'}。最新年份截至快照日期，不与完整年度直接等量比较。`;
  }));

  let noteKind = 'all', page = 0;
  const pageSize = 8;
  const sortedNotes = [...data.notes].sort((a,b) => (a.date==='日期未知'?'':a.date)<(b.date==='日期未知'?'':b.date)?1:-1);
  const search = document.getElementById('note-search'), year = document.getElementById('note-year');
  function node(tag, className, text) {const n=document.createElement(tag);if(className)n.className=className;if(text!==undefined)n.textContent=text;return n;}
  function showNotes(reset = false) {
    if(reset) page=0;
    const word=search.value.trim().toLocaleLowerCase();
    const filtered=sortedNotes.filter(n => (noteKind==='all'||n.kind===noteKind) && (year.value==='all'||(year.value==='unknown'?n.date==='日期未知':n.date.startsWith(year.value))) && `${n.title} ${n.author} ${n.chapter} ${n.text}`.toLocaleLowerCase().includes(word));
    const totalPages=Math.max(1,Math.ceil(filtered.length/pageSize));page=Math.min(page,totalPages-1);
    const list=document.getElementById('note-list');list.replaceChildren();
    filtered.slice(page*pageSize,(page+1)*pageSize).forEach(n => {
      const card=node('article','note-card'),header=node('header');
      header.append(node('span','',n.kind==='personal_review'?'个人点评':'原文划线'),node('span','',n.date));
      card.append(header,node('h3','',n.title),node('p','small',[n.author,n.chapter].filter(Boolean).join(' · ')),node('p','note-excerpt',n.text.slice(0,145)+(n.text.length>145?'…':'')));
      const details=node('details'),summary=node('summary','', '完整原文与时间来源');
      details.append(summary,node('p','full-note',n.text),node('p','source-id',`${n.time_basis}；${n.visibility==='observed'?'本次取得':'本次未取得，不推断删除'}。来源版本 ${n.version}`));card.append(details);list.append(card);
    });
    if(!filtered.length)list.append(node('p','empty','没有匹配的笔记。请调整搜索、类型或年份。'));
    document.getElementById('note-count').textContent=`匹配 ${filtered.length.toLocaleString()} / ${data.notes.length.toLocaleString()} 条正文 · 每页 ${pageSize} 条`;
    document.getElementById('note-page').textContent=`${filtered.length?page+1:0} / ${filtered.length?totalPages:0}`;
    document.getElementById('note-prev').disabled=page===0;document.getElementById('note-next').disabled=page>=totalPages-1;
  }
  document.querySelectorAll('[data-note-kind]').forEach(button => button.addEventListener('click', () => {
    noteKind=button.dataset.noteKind;
    document.querySelectorAll('[data-note-kind]').forEach(b => {const active=b===button;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});showNotes(true);
  }));
  search.addEventListener('input',()=>showNotes(true));year.addEventListener('change',()=>showNotes(true));
  document.getElementById('note-prev').addEventListener('click',()=>{page--;showNotes();search.focus({preventScroll:true});});
  document.getElementById('note-next').addEventListener('click',()=>{page++;showNotes();search.focus({preventScroll:true});});
  document.querySelectorAll('.export-feedback').forEach(button => button.addEventListener('click', () => {
    const form=button.closest('.feedback'),status=form.querySelector('select').value, explanation=form.querySelector('textarea').value.trim();
    const message=form.querySelector('.feedback-message');
    if(!status||!explanation){message.textContent='请选择看法并填写补充说明。';return;}
    const payload={...data.feedback[form.dataset.trajectory],status,explanation};
    const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json;charset=utf-8'}));
    const a=document.createElement('a');a.href=url;a.download=`reading-feedback-${form.dataset.trajectory}.json`;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
    message.textContent='反馈文件已生成；导入前尚未保存到长期档案。';
  }));
  showNotes();filterArchives();setThinkingView('theme');route();document.documentElement.classList.add('js-ready');
})();
