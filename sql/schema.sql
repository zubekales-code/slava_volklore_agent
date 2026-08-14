-- Spusť tenhle příkaz jednou v Supabase: Projekt -> SQL Editor -> New query
-- -> vlož tenhle text -> Run. Víc není potřeba, tabulka se vytvoří sama.

create table if not exists items (
    id                   bigint generated always as identity primary key,
    url                  text unique not null,
    title                text not null,
    source               text,
    category             text,
    published_at         timestamptz,
    summary              text,
    full_text            text,
    relevance_score      int,
    is_paywalled_snippet boolean default false,
    included_in_daily    boolean default false,
    included_in_weekly   boolean default false,
    created_at           timestamptz default now()
);

-- Index pro rychlé dotazy podle data a skóre (výkon při větším objemu dat).
create index if not exists idx_items_created_at on items (created_at desc);
create index if not exists idx_items_relevance on items (relevance_score desc);
