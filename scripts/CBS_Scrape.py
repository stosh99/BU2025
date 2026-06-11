import os
import sys
import json
import numpy as np
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, date as date_type
import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load .env from the project root (one level up from scripts/)
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))

# Make the app package importable so the league formulas (single source of truth)
# can be shared with the web app instead of duplicated here.
sys.path.insert(0, os.path.join(SCRIPTS_DIR, '..'))
from app.services import formulas

DB_URL = os.environ.get('DATABASE_URL')
engine = create_engine(DB_URL, pool_pre_ping=True)

team_dict = {'Awo': 'Awobs',
             'Big': 'Big Units',
             'Doo': 'Doorights',
             'Isl': 'Islanders',
             'Keg': 'Keggers',
             'Lee': 'Leemos',
             'Low': 'Low Life',
             'Mon': 'Money Ballers',
             'Ram': 'Ramrods',
             'Sha': 'Shaggers',
             'Sti': 'Stiefels',
             'Wob': 'Wobblies',
             'FA': 'FA',
             'ALL': 'AL Guy'
             }

REQUEST_URL_TEAM   = 'https://bu.baseball.cbssports.com/stats/stats-main/teamtotals/ytd:f/2018TeamView/'
REQUEST_URL_HIT    = 'https://bu.baseball.cbssports.com/stats/stats-main/all:C:1B:2B:3B:SS:OF:U/ytd:p/2018TeamView/?print_rows=9999'
REQUEST_URL_PITCH  = 'https://bu.baseball.cbssports.com/stats/stats-main/all:P/ytd:p/2018TeamView/?print_rows=9999'
REQUEST_URL_H_YEST = 'https://bu.baseball.cbssports.com/stats/stats-main/all:C:1B:2B:3B:SS:OF:U/y:p/2018TeamView/?print_rows=9999'
REQUEST_URL_P_YEST = 'https://bu.baseball.cbssports.com/stats/stats-main/all:P/y:p/2018TeamView/?print_rows=9999'
REQUEST_URL_GAMES  = 'https://bu.baseball.cbssports.com/stats/stats-main/teamtotals/ytd:f/gamesPlayed/'

with open(os.path.join(SCRIPTS_DIR, "cbs_cookies.json"), "r") as f:
    cookies_list = json.load(f)
cookies = {cookie["name"]: cookie["value"] for cookie in cookies_list}


def get_web_stats(url, cookies):
    response = requests.get(url, cookies=cookies)
    return BeautifulSoup(response.text, 'lxml')


def get_table_date(table_name):
    """Return the max date in a table, or a far-past date on first run / empty table."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text(f'SELECT MAX("Date") FROM {table_name}')).scalar()
            return result if result is not None else date_type(2000, 1, 1)
    except Exception:
        return date_type(2000, 1, 1)


def convert_both_stats(soup):
    stats_date = datetime.strptime(soup.find("div", {"class": "tableLastUpdatedTimestamp"}).text.split()[4], '%m/%d/%y')
    stats_date = stats_date - timedelta(days=1)
    team_hit_list = []
    for row in soup.find_all('table')[0].find_all('tr')[4:16]:
        hit_row = [stats_date]
        for cell in row.find_all('td'):
            hit_row.append(cell.text)
        team_hit_list.append(hit_row)
    team_pitch_list = []
    for row in soup.find_all('table')[1].find_all('tr')[4:16]:
        pitch_row = [stats_date]
        for cell in row.find_all('td'):
            pitch_row.append(cell.text)
        team_pitch_list.append(pitch_row)
    return team_hit_list, team_pitch_list


def convert_hit_stats(soup):
    stats_date = soup.find("div", class_="tableLastUpdatedTimestamp").get_text(strip=True).replace("Report Updated as of ", "").split()[0]
    stats_date = datetime.strptime(stats_date, "%m/%d/%y") - timedelta(days=1)
    player_hit_list = []
    for row in soup.find_all('table')[0].find_all('tr')[3:-1]:
        hit_row = [stats_date]
        for cell in row.find_all('td')[1:-1]:
            hit_row.append(cell.text)
        if 'AL' in hit_row[1]:
            pass
        else:
            team_code = hit_row[1][:3]
            resolved = team_dict.get(team_code)
            if resolved is None:
                print(f"WARNING: unknown team code '{team_code}' in hit stats — skipping row")
                continue
            hit_row[1] = resolved
        player_hit_list.append(hit_row)
    return player_hit_list


def convert_pitch_stats(soup):
    stats_date = soup.find("div", class_="tableLastUpdatedTimestamp").get_text(strip=True).replace("Report Updated as of ", "").split()[0]
    stats_date = datetime.strptime(stats_date, "%m/%d/%y") - timedelta(days=1)
    player_pitch_list = []
    for row in soup.find_all('table')[0].find_all('tr')[3:-1]:
        pitch_row = [stats_date]
        for cell in row.find_all('td')[1:-1]:
            pitch_row.append(cell.text)
        if 'AL' in pitch_row[1]:
            pass
        else:
            team_code = pitch_row[1][:3]
            resolved = team_dict.get(team_code)
            if resolved is None:
                print(f"WARNING: unknown team code '{team_code}' in pitch stats — skipping row")
                continue
            pitch_row[1] = resolved
        player_pitch_list.append(pitch_row)
    return player_pitch_list


def convert_gamesplayed(soup):
    stats_date = datetime.strptime(soup.find_all('table')[1].find_all('tr')[-1].text.split()[4], '%m/%d/%y')
    stats_date = stats_date - timedelta(days=1)
    gamesplayed_list = []
    for row in soup.find_all('table')[0].find_all('tr')[4:16]:
        gamesplayed_row = [stats_date]
        for cell in row.find_all('td'):
            gamesplayed_row.append(cell.text)
        gamesplayed_list.append(gamesplayed_row)
    return gamesplayed_list


def create_team_df(team_hit_list, team_pitch_list):
    hit_columns   = ['Date', 'BUTeam', 'Salary', 'G', 'AB', 'H', '2B', '3B', 'HR', 'BB', 'HP', 'SB', 'CS', 'E', 'KO', 'RC', 'OPS']
    pitch_columns = ['Date', 'BUTeam', 'Salary', 'APP', 'GS', 'QS', 'INN', 'ER', 'RA', 'ERA', 'HA', 'K', 'BBI', 'W', 'L', 'S']
    df_hit   = pd.DataFrame(team_hit_list,   columns=hit_columns)
    df_pitch = pd.DataFrame(team_pitch_list, columns=pitch_columns)
    for col in df_hit.columns[2:]:
        df_hit[col] = df_hit[col].astype(float)
    for col in df_pitch.columns[2:]:
        df_pitch[col] = df_pitch[col].astype(float)
    df_teamstat = pd.merge(df_hit, df_pitch, on=('Date', 'BUTeam'), how='left')
    df_teamstat['Salary'] = df_teamstat['Salary_x'] + df_teamstat['Salary_y']
    df_teamstat.drop(['Salary_x', 'Salary_y'], axis=1, inplace=True)
    return df_teamstat


def create_player_hit_df(player_hit_list):
    hit_columns = ['Date', 'BUTeam', 'Player', 'Salary', 'G', 'AB', 'H', '2B', '3B', 'HR', 'BB', 'HP', 'SB', 'CS', 'E', 'KO', 'RC', 'OPS']
    df = pd.DataFrame(player_hit_list, columns=hit_columns)
    for col in df.columns[3:]:
        df[col] = df[col].astype(float)
    return df


def create_player_pitch_df(player_pitch_list):
    pitch_columns = ['Date', 'BUTeam', 'Player', 'Salary', 'APP', 'GS', 'QS', 'INN', 'ER', 'RA', 'ERA', 'HA', 'K', 'BBI', 'W', 'L', 'S']
    df = pd.DataFrame(player_pitch_list, columns=pitch_columns)
    for col in df.columns[3:]:
        df[col] = df[col].astype(float)
    return df


def create_gamesplayed_df(gamesplayed_list):
    cols = ['Date', 'BUTeam', 'GPC', 'GP1B', 'GP2B', 'GPSS', 'GP3B', 'GPOF', 'E', 'AB', 'RC', 'BA', 'OBP', 'SLG']
    return pd.DataFrame(gamesplayed_list, columns=cols)


def calc_wp(df_teamstat):
    d = df_teamstat
    # Per-team RC/RA (vectorized: the pure formulas accept pandas Series).
    d['RC'] = formulas.runs_created(d['AB'], d['H'], d['2B'], d['3B'], d['HR'],
                                    d['BB'], d['HP'], d['SB'], d['CS'])
    d['RA'] = formulas.runs_allowed(d['ER'], d['E'], d['INN'])

    # League X-factor from the league-wide RC/RA (computed on column sums).
    sum_RC = formulas.runs_created(d['AB'].sum(), d['H'].sum(), d['2B'].sum(), d['3B'].sum(),
                                   d['HR'].sum(), d['BB'].sum(), d['HP'].sum(), d['SB'].sum(), d['CS'].sum())
    sum_RA = formulas.runs_allowed(d['ER'].sum(), d['E'].sum(), d['INN'].sum())

    df_teamstat['X_factor'] = formulas.x_factor(sum_RC, sum_RA)
    df_teamstat['WP'] = formulas.winning_pct(d['RC'], d['RA'], d['X_factor'])

    with engine.connect() as conn:
        games_played = conn.execute(
            text("SELECT games FROM cubsschedule WHERE date <= CURRENT_DATE ORDER BY date DESC LIMIT 1")
        ).scalar()
    if games_played is None:
        raise ValueError("cubsschedule has no rows on or before today — cannot determine BUGames")

    df_teamstat['BUGames'] = games_played
    df_teamstat['Wins']      = df_teamstat['BUGames'] * df_teamstat['WP']
    df_teamstat['Losses']    = df_teamstat['BUGames'] - df_teamstat['Wins']
    df_teamstat['GamesBack'] = df_teamstat['Wins'].max() - df_teamstat['Wins']

    # Last-6-games performance: wins/losses earned over the most recent 6 BU games
    games_six = int(games_played) - 6
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT \"BUTeam\", \"Wins\", \"Losses\" FROM teamstat WHERE \"Date\" = "
                 "(SELECT MAX(\"Date\") FROM teamstat WHERE \"BUGames\" = :g)"),
            {"g": games_six}
        ).fetchall()
    six_games_map = {row[0]: (row[1], row[2]) for row in rows}
    last6W, last6L = [], []
    for _, team_row in df_teamstat.iterrows():
        if team_row['BUTeam'] in six_games_map:
            prev_w, prev_l = six_games_map[team_row['BUTeam']]
            last6W.append(team_row['Wins'] - prev_w)
            last6L.append(team_row['Losses'] - prev_l)
        else:
            last6W.append(0)
            last6L.append(0)
    df_teamstat['Last6W'] = last6W
    df_teamstat['Last6L'] = last6L

    return df_teamstat


def update_xfactor(date):
    query = text("""
        UPDATE cubsschedule AS cs
        SET xfactor = t."X_factor"
        FROM teamstat t
        WHERE cs.date = t."Date"
        AND cs.date = :date
    """)
    with engine.begin() as conn:
        conn.execute(query, {"date": date})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def check_auth(soup, label):
    """Raise if the page looks like a CBS login redirect instead of real stats."""
    if soup.find("form", {"id": "loginForm"}) or not soup.find("div", class_="tableLastUpdatedTimestamp"):
        raise RuntimeError(
            f"CBS returned a login page for {label} — session cookies have expired. "
            "Update cbs_cookies.json to continue."
        )


def run_table(label, fetch_fn, table_name, player_table=False):
    """Fetch, parse, and write one table. Errors are logged but do not abort other tables."""
    try:
        df, web_date = fetch_fn()
        if web_date > get_table_date(table_name):
            df.to_sql(table_name, con=engine, if_exists='append', index=False)
            print(f'table {table_name} updated ({len(df)} rows)')
        else:
            print(f'table {table_name} pass')
    except Exception as exc:
        print(f'ERROR updating {table_name}: {exc}')


# ---------------------------------------------------------------------------
# Main execution
# ---------------------------------------------------------------------------

errors = []

# --- teamstat ---
try:
    soup = get_web_stats(REQUEST_URL_TEAM, cookies)
    check_auth(soup, 'team stats')
    hit_list, pitch_list = convert_both_stats(soup)
    df_teamstat = create_team_df(hit_list, pitch_list)
    df_teamstat = calc_wp(df_teamstat)
    df_teamstat.replace([np.inf, 'NaN'], value=0, inplace=True)
    web_date = df_teamstat['Date'].max().date()
    df_teamstat['Date'] = web_date
    if web_date > get_table_date('teamstat'):
        df_teamstat.to_sql('teamstat', con=engine, if_exists='append', index=False)
        print(f'table teamstat updated ({len(df_teamstat)} rows)')
        update_xfactor(web_date)
        print('x factor updated')
    else:
        print('table teamstat pass')
except Exception as exc:
    print(f'ERROR updating teamstat: {exc}')
    errors.append(f'teamstat: {exc}')

# --- hitterstats ---
try:
    soup = get_web_stats(REQUEST_URL_HIT, cookies)
    check_auth(soup, 'hitter stats')
    hit_list = convert_hit_stats(soup)
    df_player_hit = create_player_hit_df(hit_list)
    df_player_hit.replace([np.inf, 'NaN'], value=0, inplace=True)
    web_date = df_player_hit['Date'].max().date()
    df_player_hit['Date'] = web_date
    df_player_hit['Player'] = [p.strip() for p in df_player_hit['Player']]
    df_player_hit = df_player_hit.drop_duplicates(subset=['Date', 'BUTeam', 'Player'])
    if web_date > get_table_date('hitterstats'):
        df_player_hit.to_sql('hitterstats', con=engine, if_exists='append', index=False)
        print(f'table hitterstats updated ({len(df_player_hit)} rows)')
    else:
        print('table hitterstats pass')
except Exception as exc:
    print(f'ERROR updating hitterstats: {exc}')
    errors.append(f'hitterstats: {exc}')

# --- hitterstats_yest ---
try:
    soup = get_web_stats(REQUEST_URL_H_YEST, cookies)
    check_auth(soup, 'hitter yesterday stats')
    hit_list = convert_hit_stats(soup)
    df_player_hit_yest = create_player_hit_df(hit_list)
    df_player_hit_yest.replace([np.inf, 'NaN'], value=0, inplace=True)
    web_date = df_player_hit_yest['Date'].max().date()
    df_player_hit_yest['Date'] = web_date
    df_player_hit_yest['Player'] = [p.strip() for p in df_player_hit_yest['Player']]
    df_player_hit_yest = df_player_hit_yest.drop_duplicates(subset=['Date', 'BUTeam', 'Player'])
    if web_date > get_table_date('hitterstats_yest'):
        df_player_hit_yest.to_sql('hitterstats_yest', con=engine, if_exists='append', index=False)
        print(f'table hitterstats_yest updated ({len(df_player_hit_yest)} rows)')
    else:
        print('table hitterstats_yest pass')
except Exception as exc:
    print(f'ERROR updating hitterstats_yest: {exc}')
    errors.append(f'hitterstats_yest: {exc}')

# --- pitcherstats ---
try:
    soup = get_web_stats(REQUEST_URL_PITCH, cookies)
    check_auth(soup, 'pitcher stats')
    pitch_list = convert_pitch_stats(soup)
    df_player_pitch = create_player_pitch_df(pitch_list)
    df_player_pitch.replace([np.inf, 'NaN'], value=0, inplace=True)
    web_date = df_player_pitch['Date'].max().date()
    df_player_pitch['Date'] = web_date
    df_player_pitch['Player'] = [p.strip() for p in df_player_pitch['Player']]
    df_player_pitch = df_player_pitch.drop_duplicates(subset=['Date', 'BUTeam', 'Player'])
    if web_date > get_table_date('pitcherstats'):
        df_player_pitch.to_sql('pitcherstats', con=engine, if_exists='append', index=False)
        print(f'table pitcherstats updated ({len(df_player_pitch)} rows)')
    else:
        print('table pitcherstats pass')
except Exception as exc:
    print(f'ERROR updating pitcherstats: {exc}')
    errors.append(f'pitcherstats: {exc}')

# --- pitcherstats_yest ---
try:
    soup = get_web_stats(REQUEST_URL_P_YEST, cookies)
    check_auth(soup, 'pitcher yesterday stats')
    pitch_list = convert_pitch_stats(soup)
    df_player_pitch_yest = create_player_pitch_df(pitch_list)
    df_player_pitch_yest.replace([np.inf, 'NaN'], value=0, inplace=True)
    web_date = df_player_pitch_yest['Date'].max().date()
    df_player_pitch_yest['Date'] = web_date
    df_player_pitch_yest['Player'] = [p.strip() for p in df_player_pitch_yest['Player']]
    df_player_pitch_yest = df_player_pitch_yest.drop_duplicates(subset=['Date', 'BUTeam', 'Player'])
    if web_date > get_table_date('pitcherstats_yest'):
        df_player_pitch_yest.to_sql('pitcherstats_yest', con=engine, if_exists='append', index=False)
        print(f'table pitcherstats_yest updated ({len(df_player_pitch_yest)} rows)')
    else:
        print('table pitcherstats_yest pass')
except Exception as exc:
    print(f'ERROR updating pitcherstats_yest: {exc}')
    errors.append(f'pitcherstats_yest: {exc}')

# --- games ---
try:
    soup = get_web_stats(REQUEST_URL_GAMES, cookies)
    check_auth(soup, 'games')
    games_list = convert_gamesplayed(soup)
    df_gamesplayed = create_gamesplayed_df(games_list)
    df_gamesplayed.replace([np.inf, 'NaN'], value=0, inplace=True)
    web_date = df_gamesplayed['Date'].max().date()
    df_gamesplayed['Date'] = web_date
    if web_date > get_table_date('games'):
        df_gamesplayed.to_sql('games', con=engine, if_exists='append', index=False)
        print(f'table games updated ({len(df_gamesplayed)} rows)')
    else:
        print('table games pass')
except Exception as exc:
    print(f'ERROR updating games: {exc}')
    errors.append(f'games: {exc}')

if errors:
    print(f'\nSCRAPE COMPLETED WITH {len(errors)} ERROR(S):')
    for e in errors:
        print(f'  - {e}')
    raise SystemExit(1)
else:
    print('\nScrape completed successfully.')
