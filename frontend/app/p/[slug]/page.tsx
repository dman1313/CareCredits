'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { BookOpen, ExternalLink, Printer } from 'lucide-react';
import { Brand } from '@/components/Brand';

type PublicData = {
  name: string;
  bio: string;
  evidence_status: string;
  items: { title: string; provider: string; attended_on: string; source_url: string; demo: boolean }[];
};

export default function PublicProfile() {
  const { slug } = useParams<{ slug: string }>();
  const [data, setData] = useState<PublicData | null>(null);
  const [error, setError] = useState('');

  function load() {
    setError('');
    setData(null);
    fetch('/api/v1/public/' + encodeURIComponent(slug), { cache: 'no-store' })
      .then(async (r) => {
        if (!r.ok) throw new Error('This training profile is private or unavailable.');
        return r.json();
      })
      .then(setData)
      .catch((e) => setError(e.message));
  }

  useEffect(load, [slug]);

  return (
    <main id="main-content" className="public-page">
      <a className="skip-link" href="#main-content">
        Skip to public profile
      </a>
      <a href="/">
        <Brand />
      </a>
      {error ? (
        <div className="empty-state">
          <h1>Private by choice.</h1>
          <p>{error}</p>
          <button className="text-btn" type="button" onClick={load}>
            Retry
          </button>
        </div>
      ) : !data ? (
        <p className="empty-state">Loading training profile…</p>
      ) : (
        <>
          <header className="public-header">
            <span className="pill">A PERSONAL COMMITMENT TO LEARNING</span>
            <h1>{data.name}</h1>
            <p>{data.bio}</p>
            <small>{data.evidence_status}</small>
          </header>
          <div className="section-heading">
            <h2>Selected professional learning</h2>
            <span>{data.items.length} courses</span>
          </div>
          {data.items.length ? (
            data.items.map((c, i) => (
              <article className="public-course" key={i}>
                <span className="round-icon">
                  <BookOpen />
                </span>
                <div>
                  {c.demo && <span className="tag">Fictional demo course</span>}
                  <h3>{c.title}</h3>
                  <p>
                    {c.provider} · Completed {c.attended_on}
                  </p>
                </div>
                <a className="text-btn" href={c.source_url} target="_blank" rel="noreferrer">
                  Source <ExternalLink size={14} />
                </a>
              </article>
            ))
          ) : (
            <p className="empty-state">No training has been selected for this public profile.</p>
          )}
          <div className="button-row">
            <button className="secondary" onClick={() => window.print()}>
              <Printer size={16} /> Print or save as PDF
            </button>
          </div>
          <footer>
            Published with permission of the profile owner. This page does not establish specialist status or
            independently verified accreditation.
          </footer>
        </>
      )}
    </main>
  );
}
