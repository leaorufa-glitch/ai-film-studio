'use client';
import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { ArrowRight, Clapperboard, Plus, Search, Film, Sparkles } from 'lucide-react';
import { Entity, get, post } from '@/lib/api';

export default function Home() {
  const [projects, setProjects] = useState<Entity[]>([]);
  const [query, setQuery] = useState('');
  const [title, setTitle] = useState('');
  const [idea, setIdea] = useState('');
  const [ratio, setRatio] = useState('16:9');
  const [open, setOpen] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { get<Entity[]>('/projects').then(setProjects).catch(e => setError(e.message)); }, []);
  const visible = useMemo(() => projects.filter(p => p.payload.title?.toLowerCase().includes(query.toLowerCase())), [projects, query]);
  async function create() {
    if (!title.trim()) return;
    setBusy(true); setError('');
    try {
      const result = await post<{ project: Entity }>('/projects', { payload: { title, idea, aspect_ratio: ratio } });
      window.location.href = `/projects/${result.project.id}/01`;
    } catch (e: any) { setError(e.message); setBusy(false); }
  }
  return <main className="home">
    <header className="home-top"><div className="brand"><span className="brand-mark"><Clapperboard size={22}/></span><span>AI FILM <strong>STUDIO</strong></span></div><div className="home-top-note">创作者工作室 · 本地项目　<Link href="/admin">运行管理台</Link></div></header>
    <section className="hero"><div className="eyebrow"><span className="eyebrow-line"/> YOUR CREATIVE SPACE</div><h1>让故事，<em>成为电影。</em></h1><p>从一句想法到最终影片。把重要的创作决定留给你，其余生产工作清晰地放在每一步。</p><button className="primary hero-cta" onClick={() => setOpen(true)}><Plus size={18}/> 新建影片 <ArrowRight size={18}/></button><div className="hero-orbit orbit-one"/><div className="hero-orbit orbit-two"/><div className="hero-glow"/></section>
    <section className="project-section"><div className="section-heading"><div><div className="eyebrow">YOUR FILMS</div><h2>继续创作</h2></div><div className="search-box"><Search size={17}/><input aria-label="搜索项目" placeholder="搜索影片..." value={query} onChange={e => setQuery(e.target.value)}/></div></div>
      {error && <div className="alert error">{error}</div>}
      <div className="project-grid">{visible.map((p, i) => <Link className="project-card" key={p.id} href={`/projects/${p.id}/01`}><div className="project-art"><span className="project-index">{String(i+1).padStart(2,'0')}</span><Film size={34}/></div><div className="project-card-body"><span className="small-label">FILM PROJECT · {p.payload.aspect_ratio || '16:9'}</span><h3>{p.payload.title}</h3><p>{p.payload.idea || '从这里继续，让这个故事慢慢成形。'}</p><span className="continue">进入工作室 <ArrowRight size={15}/></span></div></Link>)}
      <button className="project-card new-project" onClick={() => setOpen(true)}><span className="new-project-icon"><Plus size={26}/></span><strong>开启一个新故事</strong><span>今天想拍什么？</span></button></div>
      {visible.length === 0 && query && <p className="muted">没有找到这个项目。</p>}
    </section>
    {open && <div className="modal-backdrop" onClick={() => setOpen(false)}><div className="modal" role="dialog" aria-modal="true" aria-label="新建影片" onClick={e => e.stopPropagation()}><div className="eyebrow">NEW FILM</div><h2>新建影片</h2><p className="muted">先给故事一个名字。其余内容可以稍后再写。</p><label>项目名称<input autoFocus value={title} onChange={e => setTitle(e.target.value)} placeholder="例如：雨夜车站"/></label><label>一句话想法 / 粘贴剧本<textarea value={idea} onChange={e => setIdea(e.target.value)} rows={4} placeholder="这个故事从哪里开始？"/></label><label>画幅<select value={ratio} onChange={e => setRatio(e.target.value)}><option>16:9</option><option>9:16</option><option>1:1</option><option>4:3</option><option>3:4</option><option>21:9</option></select></label><div className="modal-actions"><button className="ghost" onClick={() => setOpen(false)}>取消</button><button className="primary" disabled={!title.trim() || busy} onClick={create}>{busy ? '创建中…' : '创建影片'} <ArrowRight size={17}/></button></div></div></div>}
    <footer className="home-footer"><span><Sparkles size={13}/> AI FILM STUDIO</span><span>故事 · 制作 · 成片</span></footer>
  </main>;
}
