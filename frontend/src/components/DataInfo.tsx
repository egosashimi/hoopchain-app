// ============================================================
// HOOPCHAIN — DataInfo page component
// Shows dataset metadata, coverage info, and known gaps.
// ============================================================

import { useState, useEffect } from 'react';
import { healthApi } from '../api/client';

interface GraphStats {
  nodes: number;
  edges: number;
}

export function DataInfo() {
  const [stats, setStats] = useState<GraphStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    healthApi.check()
      .then((r) => setStats({ nodes: r.graph_nodes, edges: r.graph_edges }))
      .catch(() => setStats(null))
      .finally(() => setLoading(false));
  }, []);

  const DATASET_UPDATED = 'June 2026';
  const MOST_RECENT_SEASON = '2024–25';

  return (
    <div className="max-w-2xl mx-auto py-10 px-4">
      <h1
        className="font-display font-black text-3xl mb-1"
        style={{ color: 'var(--color-accent)' }}
      >
        Data & Coverage
      </h1>
      <p className="text-hc-text-2 text-sm mb-8">
        Information about the dataset powering Hoopchain connections.
      </p>

      {/* Dataset summary card */}
      <section className="rounded-xl border border-hc-border bg-hc-surface p-5 mb-6">
        <h2 className="font-display font-bold text-lg text-hc-text mb-4">Dataset Overview</h2>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
          <div>
            <dt className="text-hc-text-3 uppercase tracking-wider text-[11px] font-semibold mb-0.5">
              Last Updated
            </dt>
            <dd className="text-hc-text font-medium">{DATASET_UPDATED}</dd>
          </div>
          <div>
            <dt className="text-hc-text-3 uppercase tracking-wider text-[11px] font-semibold mb-0.5">
              Most Recent Season
            </dt>
            <dd className="text-hc-text font-medium">{MOST_RECENT_SEASON}</dd>
          </div>
          <div>
            <dt className="text-hc-text-3 uppercase tracking-wider text-[11px] font-semibold mb-0.5">
              Players in Graph
            </dt>
            <dd className="text-hc-text font-medium">
              {loading ? '…' : stats ? stats.nodes.toLocaleString() : 'unavailable'}
            </dd>
          </div>
          <div>
            <dt className="text-hc-text-3 uppercase tracking-wider text-[11px] font-semibold mb-0.5">
              Total Connections
            </dt>
            <dd className="text-hc-text font-medium">
              {loading ? '…' : stats ? stats.edges.toLocaleString() : 'unavailable'}
            </dd>
          </div>
        </dl>
      </section>

      {/* Connection types */}
      <section className="rounded-xl border border-hc-border bg-hc-surface p-5 mb-6">
        <h2 className="font-display font-bold text-lg text-hc-text mb-4">Connection Types</h2>
        <ul className="space-y-3 text-sm">
          {[
            {
              label: 'Teammates',
              modes: 'CLASSIC + WILD',
              desc: 'Players on the same roster in the same season, derived from box scores and play-by-play records.',
            },
            {
              label: 'College',
              modes: 'WILD',
              desc: 'Players who attended the same college or university.',
            },
            {
              label: 'Draft Class',
              modes: 'WILD',
              desc: 'Players drafted in the same NBA Draft year.',
            },
            {
              label: 'Coached by',
              modes: 'WILD',
              desc: 'Players who played for the same head coach on the same team in the same season.',
            },
            {
              label: 'All-Star',
              modes: 'WILD',
              desc: 'Players who appeared in the same NBA All-Star Game.',
            },
          ].map(({ label, modes, desc }) => (
            <li key={label} className="flex gap-3">
              <div className="min-w-[100px]">
                <div className="text-hc-accent font-bold">{label}</div>
                <div
                  className="text-[10px] font-semibold uppercase tracking-wider mt-0.5"
                  style={{ color: 'var(--color-text-3)' }}
                >
                  {modes}
                </div>
              </div>
              <span className="text-hc-text-2">{desc}</span>
            </li>
          ))}
        </ul>
      </section>

      {/* Known gaps */}
      <section className="rounded-xl border border-hc-border bg-hc-surface p-5 mb-6">
        <h2 className="font-display font-bold text-lg text-hc-text mb-1">Known Gaps</h2>
        <p className="text-hc-text-2 text-sm mb-4">
          Teammate edges cover 1946–47 through 2024–25. Other connection types have partial
          coverage — see below.
        </p>
        <ul className="space-y-3 text-sm">
          {[
            {
              name: 'Coach edges — partial list',
              status: 'partial',
              note: 'Only ~20 prominent head coaches from 1980 onward are tracked. Players who played primarily under less-prominent coaches may have no "Coached by" connection. Coverage ends at 2024–25.',
            },
            {
              name: 'All-Star edges — notable players only',
              status: 'partial',
              note: 'All-Star selections are hardcoded for ~40 well-known players from 1984–2024. Many legitimate All-Stars are not in the list and will not connect through All-Star appearances.',
            },
            {
              name: 'College data — best effort',
              status: 'partial',
              note: 'College is sourced from nbadb; missing entries are filled via Wikipedia. Some players may still have missing or incorrect college data.',
            },
            {
              name: 'Pre-1980 coaching',
              status: 'partial',
              note: 'Coaching records begin with the 1979–80 season. Pre-1980 players have no "Coached by" edges.',
            },
          ].map(({ name, status, note }) => (
            <li key={name} className="flex gap-3 items-start">
              <span className="text-xs font-bold px-2 py-0.5 rounded-full mt-0.5 whitespace-nowrap bg-yellow-500/15 text-yellow-400 border border-yellow-500/30">
                {status}
              </span>
              <div>
                <div className="text-hc-text font-medium">{name}</div>
                <div className="text-hc-text-3 text-xs mt-0.5">{note}</div>
              </div>
            </li>
          ))}
        </ul>
      </section>

      {/* Data sources */}
      <section className="rounded-xl border border-hc-border bg-hc-surface p-5 mb-6">
        <h2 className="font-display font-bold text-lg text-hc-text mb-3">Data Sources</h2>
        <ul className="space-y-2 text-sm text-hc-text-2">
          <li>
            <a
              href="https://www.kaggle.com/datasets/wyattowalsh/basketball"
              target="_blank"
              rel="noopener noreferrer"
              className="text-hc-accent hover:underline"
            >
              nbadb (wyattowalsh/basketball)
            </a>{' '}
            — primary historical dataset (players, rosters, draft history) through 2022–23
          </li>
          <li>
            <a
              href="https://github.com/swar/nba_api"
              target="_blank"
              rel="noopener noreferrer"
              className="text-hc-accent hover:underline"
            >
              nba_api (NBA.com Stats)
            </a>{' '}
            — official NBA roster data for 2023–24 and 2024–25; canonical NBA.com player IDs
          </li>
          <li>
            <a
              href="https://www.wikipedia.org"
              target="_blank"
              rel="noopener noreferrer"
              className="text-hc-accent hover:underline"
            >
              Wikipedia REST API
            </a>{' '}
            — supplemental college data and coaching records (head coaches per team per season, 1980–2024)
          </li>
        </ul>
      </section>

      {/* Report error */}
      <div className="text-center py-4">
        <p className="text-hc-text-2 text-sm">Found a missing connection or wrong data?</p>
        <p className="text-hc-text-3 text-xs mt-1">
          Email us at{' '}
          <a
            href="mailto:hoopchainapp@gmail.com?subject=Hoopchain%20Data%20Error"
            className="text-hc-accent hover:underline"
          >
            hoopchainapp@gmail.com
          </a>
        </p>
      </div>
    </div>
  );
}
