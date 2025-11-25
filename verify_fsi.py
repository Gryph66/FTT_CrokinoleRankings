import sqlite3
import pandas as pd
import os

def verify_fsi():
    # Connect to the public site database
    db_path = 'public_data.db'
    if not os.path.exists(db_path):
        print(f"Error: {db_path} not found.")
        return

    conn = sqlite3.connect(db_path)
    
    print("--- FSI Verification Script ---")
    
    # 1. Get Parameters
    try:
        params = pd.read_sql("SELECT * FROM points_parameters", conn).iloc[0]
        scaling_factor = params['fsi_scaling_factor']
        doubles_top_n = int(params['doubles_top_n_for_fsi'])
        fsi_min = params['fsi_min']
        fsi_max = params['fsi_max']
        print(f"Active Parameters:")
        print(f"  Scaling Factor: {scaling_factor}")
        print(f"  Doubles Top N:  {doubles_top_n}")
        print(f"  FSI Range:      [{fsi_min}, {fsi_max}]")
    except Exception as e:
        print(f"Error reading parameters: {e}")
        conn.close()
        return

    # 2. Get Ontario Doubles Tournaments
    print("\nChecking 'Ontario Doubles' tournaments...")
    sql = "SELECT id, event_name, season, tournament_date FROM tournaments WHERE event_name LIKE '%Ontario Doubles%' ORDER BY tournament_date DESC"
    tourneys = pd.read_sql(sql, conn)
    
    for _, t in tourneys.iterrows():
        t_id = t['id']
        name = t['event_name']
        season = t['season']
        date = t['tournament_date']
        
        print(f"\nTournament: {name} (Season {season}, {date})")
        
        # Get Stored FSI
        stored = pd.read_sql(f"SELECT fsi, avg_top_mu FROM tournament_fsi WHERE tournament_id={t_id}", conn)
        if stored.empty:
            print("  [Stored] No FSI record found.")
            stored_fsi = 0.0
        else:
            stored_fsi = stored.iloc[0]['fsi']
            stored_avg_mu = stored.iloc[0]['avg_top_mu']
            print(f"  [Stored] FSI: {stored_fsi:.4f} | Avg Top Mu: {stored_avg_mu:.4f}")

        # Calculate FSI from Results
        results = pd.read_sql(f"SELECT * FROM tournament_results WHERE tournament_id={t_id}", conn)
        
        if results.empty:
            print("  [Calc]   No results found.")
            continue

        # Group by team
        teams = {}
        for _, r in results.iterrows():
            team_key = r['team_key']
            if not team_key: 
                continue # Skip if no team key (shouldn't happen for doubles)
                
            if team_key not in teams:
                teams[team_key] = []
            
            mu = r['before_mu'] if r['before_mu'] is not None else 0.0
            teams[team_key].append(mu)
            
        # Calculate Team Averages
        team_ratings = []
        for team, mus in teams.items():
            if len(mus) > 0:
                avg_mu = sum(mus) / len(mus)
                team_ratings.append(avg_mu)
        
        # Sort and take Top N
        team_ratings.sort(reverse=True)
        top_teams = team_ratings[:doubles_top_n]
        count_used = len(top_teams)
        
        if not top_teams:
            calc_avg_mu = 0.0
        else:
            calc_avg_mu = sum(top_teams) / len(top_teams)
            
        # Apply Scaling
        calc_fsi_raw = calc_avg_mu / scaling_factor
        calc_fsi = max(fsi_min, min(calc_fsi_raw, fsi_max))
        
        print(f"  [Calc]   FSI: {calc_fsi:.4f} | Avg Top Mu: {calc_avg_mu:.4f} (Used Top {count_used} Teams)")
        print(f"           Math: {calc_avg_mu:.4f} / {scaling_factor} = {calc_fsi_raw:.4f} -> Clamped: {calc_fsi:.4f}")
        
        diff = abs(calc_fsi - stored_fsi)
        if diff > 0.0001:
            print(f"  ⚠️ DISCREPANCY: {diff:.4f}")
        else:
            print("  ✅ MATCH")

    conn.close()

if __name__ == "__main__":
    verify_fsi()
