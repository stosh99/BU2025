"""Phase 3: backfill PlayerID on historical player rows.

Historical hitter/pitcher rows predate PlayerID capture, so they only carry the
free-text Player string ("Alec Burleson 1B,OF * STL"). This script fetches the
live CBS full-universe YTD pages (which expose each player's stable id via the
/players/playerpage/<id> link), builds a name->id map, and fills in the NULL
PlayerID values by matching on the player's core name (and MLB team to break
ties). It only assigns an id when the match is unambiguous; anything ambiguous or
not present in the current CBS universe is left NULL.

Dry-run by default (prints coverage); pass --commit to write.

    python scripts/backfill_player_ids.py            # dry-run
    python scripts/backfill_player_ids.py --commit   # write
"""

import os
import re
import sys
import json
import argparse
from collections import defaultdict

import requests
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '..'))
from app.services.stats import clean_player_name  # noqa: E402

load_dotenv(os.path.join(SCRIPTS_DIR, '..', '.env'))
engine = create_engine(os.environ['DATABASE_URL'], pool_pre_ping=True)

PLAYERPAGE_RE = re.compile(r'/players/playerpage/(\d+)')
# Fielding-position abbreviations that trail the player name in the cell text.
POSITIONS = {'C', '1B', '2B', '3B', 'SS', 'OF', 'LF', 'CF', 'RF', 'DH',
             'U', 'UT', 'P', 'SP', 'RP', 'MI', 'CI'}

HIT_URL   = 'https://bu.baseball.cbssports.com/stats/stats-main/all:C:1B:2B:3B:SS:OF:U/ytd:p/2018TeamView/?print_rows=9999'
PITCH_URL = 'https://bu.baseball.cbssports.com/stats/stats-main/all:P/ytd:p/2018TeamView/?print_rows=9999'

# Hit maps backfill the hitter tables; pitch maps backfill the pitcher tables.
TABLE_SOURCES = [
    ('hitterstats',       'hit'),
    ('hitterstats_yest',  'hit'),
    ('pitcherstats',      'pitch'),
    ('pitcherstats_yest', 'pitch'),
]


def load_cookies():
    with open(os.path.join(SCRIPTS_DIR, 'cbs_cookies.json')) as f:
        return {c['name']: c['value'] for c in json.load(f)}


def norm(s):
    """Canonical comparison key for a player name (handles the \\x95/bullet
    separator and nbsp via clean_player_name, case-insensitive)."""
    return clean_player_name(s or '').casefold()


def split_name_team(full):
    """('alec burleson', 'STL') from 'Alec Burleson 1B,OF * STL'.

    Everything after the bullet/control-char separator is the MLB team; the
    trailing position tokens before it are stripped, leaving the core name."""
    parts = re.split(r'[•\x95]', full)
    team = parts[-1].strip() if len(parts) > 1 else ''
    toks = parts[0].split()
    while toks and all(t in POSITIONS for t in toks[-1].split(',')):
        toks.pop()
    return norm(' '.join(toks)), team


def build_maps(url, cookies):
    """Return (by_name, by_name_team): name->{ids} and (name,team)->{ids}."""
    resp = requests.get(url, cookies=cookies, timeout=60)
    soup = BeautifulSoup(resp.text, 'lxml')
    if soup.find('form', {'id': 'loginForm'}) or not soup.find('div', class_='tableLastUpdatedTimestamp'):
        raise RuntimeError(f"CBS returned a login page for {url} — refresh scripts/cbs_cookies.json")
    by_name = defaultdict(set)
    by_name_team = defaultdict(set)
    for row in soup.find_all('table')[0].find_all('tr')[3:-1]:
        a = row.find('a', href=PLAYERPAGE_RE)
        if not a:
            continue
        pid = PLAYERPAGE_RE.search(a['href']).group(1)
        cells = row.find_all('td')[1:-1]
        full = cells[1].get_text() if len(cells) > 1 else a.get_text()
        name, team = split_name_team(full)
        by_name[name].add(pid)
        by_name_team[(name, team)].add(pid)
    return by_name, by_name_team


def make_resolver(by_name, by_name_team):
    def resolve(full):
        name, team = split_name_team(full)
        ids = by_name_team.get((name, team))
        if ids and len(ids) == 1:
            return next(iter(ids)), 'name+team'
        ids = by_name.get(name)
        if ids and len(ids) == 1:
            return next(iter(ids)), 'name'
        if ids and len(ids) > 1:
            return None, 'ambiguous'
        return None, 'unmatched'
    return resolve


def backfill_table(conn, table, resolve, commit):
    rows = conn.execute(text(
        f'SELECT "Player", COUNT(*) FROM {table} WHERE "PlayerID" IS NULL GROUP BY "Player"'
    )).fetchall()
    updates = []
    rows_by_tier = defaultdict(int)
    for player, cnt in rows:
        pid, tier = resolve(player)
        rows_by_tier[tier] += cnt
        if pid:
            updates.append({'pid': pid, 'player': player})

    total_rows = sum(c for _, c in rows)
    covered_rows = rows_by_tier['name+team'] + rows_by_tier['name']
    pct = (100 * covered_rows / total_rows) if total_rows else 0.0
    print(f"\n[{table}] NULL rows: {total_rows} across {len(rows)} distinct names")
    print(f"  resolvable: {covered_rows} rows ({pct:.2f}%) via {len(updates)} names")
    print(f"  rows by tier: name+team={rows_by_tier['name+team']} name={rows_by_tier['name']} "
          f"ambiguous={rows_by_tier['ambiguous']} unmatched={rows_by_tier['unmatched']}")

    if commit and updates:
        # One set-based UPDATE...FROM a temp (name -> id) table beats a per-name
        # UPDATE (which would seq-scan the big table once per name).
        tmp = f'_bf_{table}'
        conn.execute(text(f'CREATE TEMP TABLE "{tmp}" (player text, pid text) ON COMMIT DROP'))
        conn.execute(text(f'INSERT INTO "{tmp}" (player, pid) VALUES (:player, :pid)'), updates)
        result = conn.execute(text(
            f'UPDATE {table} AS t SET "PlayerID" = m.pid FROM "{tmp}" AS m '
            f'WHERE t."Player" = m.player AND t."PlayerID" IS NULL'))
        conn.execute(text(f'DROP TABLE "{tmp}"'))
        print(f"  COMMITTED {result.rowcount} rows updated ({len(updates)} names)")
    elif updates:
        print(f"  (dry-run) would update {len(updates)} names")
    return covered_rows, total_rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--commit', action='store_true', help='write updates (default: dry-run)')
    args = ap.parse_args()

    cookies = load_cookies()
    print("Fetching live CBS full-universe YTD pages...")
    hit_bn, hit_bnt = build_maps(HIT_URL, cookies)
    pit_bn, pit_bnt = build_maps(PITCH_URL, cookies)
    print(f"hit map:   {len(hit_bn)} names ({sum(1 for v in hit_bn.values() if len(v) > 1)} ambiguous)")
    print(f"pitch map: {len(pit_bn)} names ({sum(1 for v in pit_bn.values() if len(v) > 1)} ambiguous)")

    resolvers = {'hit': make_resolver(hit_bn, hit_bnt),
                 'pitch': make_resolver(pit_bn, pit_bnt)}

    grand_cov = grand_tot = 0
    with engine.begin() as conn:
        for table, source in TABLE_SOURCES:
            cov, tot = backfill_table(conn, table, resolvers[source], args.commit)
            grand_cov += cov
            grand_tot += tot

    mode = "COMMIT" if args.commit else "DRY-RUN"
    pct = (100 * grand_cov / grand_tot) if grand_tot else 0.0
    print(f"\n=== {mode}: {grand_cov}/{grand_tot} NULL rows resolvable ({pct:.2f}%) ===")
    if not args.commit:
        print("Re-run with --commit to write.")


if __name__ == '__main__':
    main()
