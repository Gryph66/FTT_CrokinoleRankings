"""
Load exported JSON data into SQLite database for public site.
Run this after exporting data from admin site.
"""
import json
import pandas as pd
from database import engine, Base, Tournament, Player, TournamentResult, RatingChange, TournamentFSI, SeasonEventPoints, SeasonLeaderboard, SystemParameters, PointsParameters
from sqlalchemy.orm import sessionmaker

def load_json_data():
    """Load all JSON files into SQLite database."""
    
    # Drop all tables and recreate to ensure schema is up to date
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Clear existing data
        session.query(SeasonEventPoints).delete()
        session.query(SeasonLeaderboard).delete()
        session.query(TournamentFSI).delete()
        session.query(RatingChange).delete()
        session.query(TournamentResult).delete()
        session.query(Tournament).delete()
        session.query(Player).delete()
        session.commit()
        
        print("Loading players...")
        with open('data/players.json', 'r', encoding='utf-8') as f:
            players_data = json.load(f)
        for p in players_data:
            player = Player(
                id=p['id'],
                name=p['name'],
                current_rating_mu=p.get('current_rating_mu', 0.0),
                current_rating_sigma=p.get('current_rating_sigma', 1.667),
                tournaments_played=p.get('tournaments_played', 0),
                # New multi-model rating columns
                current_rating_mu_singles=p.get('current_rating_mu_singles'),
                current_rating_sigma_singles=p.get('current_rating_sigma_singles'),
                current_rating_mu_combined=p.get('current_rating_mu_combined'),
                current_rating_sigma_combined=p.get('current_rating_sigma_combined'),
                current_rating_mu_doubles=p.get('current_rating_mu_doubles'),
                current_rating_sigma_doubles=p.get('current_rating_sigma_doubles'),
                singles_tournaments_played=p.get('singles_tournaments_played', 0),
                doubles_tournaments_played=p.get('doubles_tournaments_played', 0)
            )
            session.add(player)
        session.commit()
        print(f"Loaded {len(players_data)} players")
        
        print("Loading tournaments...")
        with open('data/tournaments.json', 'r', encoding='utf-8') as f:
            tournaments_data = json.load(f)
        for t in tournaments_data:
            tournament = Tournament(
                id=t['id'],
                season=t['season'],
                event_name=t['event_name'],
                tournament_group=t.get('tournament_group'),
                tournament_format=t.get('tournament_format', 'singles'),
                num_players=t.get('num_players', 0),
                avg_rating_before=t.get('avg_rating_before'),
                avg_rating_after=t.get('avg_rating_after'),
                tournament_date=pd.to_datetime(t.get('tournament_date')) if t.get('tournament_date') else None
            )
            session.add(tournament)
        session.commit()
        print(f"Loaded {len(tournaments_data)} tournaments")
        
        print("Loading FSI data...")
        with open('data/fsi_trends.json', 'r', encoding='utf-8') as f:
            fsi_data = json.load(f)
        # Group by tournament ID to avoid duplicates
        fsi_by_tournament = {}
        for f in fsi_data:
            # Find tournament ID by name and season
            tournament = session.query(Tournament).filter_by(
                event_name=f['event_name'],
                season=f['season']
            ).first()
            if tournament and tournament.id not in fsi_by_tournament:
                fsi_by_tournament[tournament.id] = f
        
        for tournament_id, f in fsi_by_tournament.items():
            fsi = TournamentFSI(
                tournament_id=tournament_id,
                season=f['season'],
                fsi=f['fsi'],
                avg_top_mu=f.get('avg_top_mu', 0.0)
            )
            session.add(fsi)
        session.commit()
        print(f"Loaded {len(fsi_by_tournament)} FSI records")
        
        print("Loading event points...")
        with open('data/event_points.json', 'r', encoding='utf-8') as f:
            event_points_data = json.load(f)
        for ep in event_points_data:
            event_point = SeasonEventPoints(
                tournament_id=ep['tournament_id'],
                player_id=ep['player_id'],
                season=ep['season'],
                place=ep['place'],
                field_size=ep['field_size'],
                pre_mu=ep.get('pre_mu', 0.0),
                pre_sigma=ep.get('pre_sigma', 1.667),
                post_mu=ep.get('post_mu', 0.0),
                post_sigma=ep.get('post_sigma', 1.667),
                display_rating=ep.get('display_rating', 0.0),
                fsi=ep.get('fsi', 1.0),
                raw_points=ep.get('raw_points', 0.0),
                base_points=ep.get('base_points', 0.0),
                expected_rank=ep.get('expected_rank', 0),
                overperformance=ep.get('overperformance', 0.0),
                bonus_points=ep.get('bonus_points', 0.0),
                total_points=ep.get('total_points', 0.0)
            )
            session.add(event_point)
        session.commit()
        print(f"Loaded {len(event_points_data)} event points")
        
        print("Loading season standings...")
        with open('data/season_standings.json', 'r', encoding='utf-8') as f:
            standings_data = json.load(f)
        
        # Get player name to ID mapping
        players = session.query(Player).all()
        player_name_to_id = {p.name: p.id for p in players}
        
        for s in standings_data:
            # Get player_id from player name if not present
            if 'player_id' not in s and 'player' in s:
                player_id = player_name_to_id.get(s['player'])
                if not player_id:
                    continue  # Skip if player not found
            else:
                player_id = s.get('player_id')
            
            standing = SeasonLeaderboard(
                season=s['season'],
                player_id=player_id,
                total_points=s['total_points'],
                events_counted=s['events_counted'],
                final_display_rating=s.get('final_display_rating', 0.0),
                rank=s['rank']
            )
            session.add(standing)
        session.commit()
        print(f"Loaded {len(standings_data)} season standings")
        
        print("Loading rating changes...")
        with open('data/rating_changes.json', 'r', encoding='utf-8') as f:
            rating_changes_data = json.load(f)
        
        # Deduplicate by ID (keep first occurrence)
        seen_ids = set()
        unique_rating_changes = []
        for rc in rating_changes_data:
            if rc['id'] not in seen_ids:
                seen_ids.add(rc['id'])
                unique_rating_changes.append(rc)
        
        for rc in unique_rating_changes:
            rating_change = RatingChange(
                id=rc['id'],
                player_id=rc['player_id'],
                tournament_id=rc['tournament_id'],
                place=rc.get('place'),
                before_mu=rc['before_mu'],
                before_sigma=rc['before_sigma'],
                after_mu=rc['after_mu'],
                after_sigma=rc['after_sigma'],
                mu_change=rc.get('mu_change'),
                sigma_change=rc.get('sigma_change'),
                conservative_rating_before=rc.get('conservative_rating_before'),
                conservative_rating_after=rc.get('conservative_rating_after'),
                rating_model=rc.get('rating_model', 'singles_only')
            )
            session.add(rating_change)
        session.commit()
        print(f"Loaded {len(rating_changes_data)} rating changes")
        
        print("Loading tournament results...")
        with open('data/tournament_results.json', 'r', encoding='utf-8') as f:
            results_data = json.load(f)
        for r in results_data:
            result = TournamentResult(
                id=r['id'],
                tournament_id=r['tournament_id'],
                player_id=r['player_id'],
                place=r['place'],
                before_mu=r.get('before_mu'),
                before_sigma=r.get('before_sigma'),
                team_key=r.get('team_key')
            )
            session.add(result)
        session.commit()
        print(f"Loaded {len(results_data)} tournament results")

        print("Loading system parameters...")
        try:
            with open('data/system_parameters.json', 'r', encoding='utf-8') as f:
                sys_params = json.load(f)
            if sys_params:
                # Clear existing
                session.query(SystemParameters).delete()
                p = sys_params[0] # Should be only one row
                params = SystemParameters(
                    id=p['id'],
                    mu=p['mu'],
                    sigma=p['sigma'],
                    beta=p['beta'],
                    tau=p['tau'],
                    gamma=p.get('gamma', 0.03),  # TTT skill drift parameter
                    draw_probability=p['draw_probability'],
                    z_score_baseline_mean=p.get('z_score_baseline_mean', 0.0),
                    z_score_baseline_std=p.get('z_score_baseline_std', 1.0),
                    rating_mode=p.get('rating_mode', 'singles_only'),
                    doubles_contribution_weight=p.get('doubles_contribution_weight', 0.5)
                )
                session.add(params)
                session.commit()
                print(f"Loaded system parameters (gamma={p.get('gamma', 0.03)})")
        except FileNotFoundError:
            print("⚠️ system_parameters.json not found, skipping")

        print("Loading points parameters...")
        try:
            with open('data/points_parameters.json', 'r', encoding='utf-8') as f:
                points_params = json.load(f)
            if points_params:
                # Clear existing
                session.query(PointsParameters).delete()
                p = points_params[0] # Should be only one row
                params = PointsParameters(
                    id=p['id'],
                    alpha=p['alpha'],
                    doubles_alpha=p['doubles_alpha'],
                    bonus_scale=p.get('bonus_scale', 0.0),
                    top_n_for_fsi=p.get('singles_top_n_for_fsi', 20),
                    doubles_top_n_for_fsi=p.get('doubles_top_n_for_fsi', 20),
                    fsi_scaling_factor=p.get('fsi_scaling_factor', 25.0),
                    fsi_min=p.get('fsi_min', 0.8),
                    fsi_max=p.get('fsi_max', 1.6),
                    best_tournaments_per_season=p.get('best_tournaments_per_season', 5),
                    # Tiered base points
                    top_tier_fsi_threshold=p.get('top_tier_fsi_threshold', 1.35),
                    top_tier_base_points=p.get('top_tier_base_points', 60.0),
                    normal_tier_base_points=p.get('normal_tier_base_points', 50.0),
                    low_tier_base_points=p.get('low_tier_base_points', 40.0),
                    low_tier_fsi_threshold=p.get('low_tier_fsi_threshold', 1.0),
                    doubles_weight_high=p.get('doubles_weight_high', 0.65),
                    is_active=1
                )
                session.add(params)
                session.commit()
                print("Loaded points parameters")
        except FileNotFoundError:
            print("⚠️ points_parameters.json not found, skipping")
        
        print("✅ All data loaded successfully!")
        
    except Exception as e:
        session.rollback()
        print(f"❌ Error loading data: {e}")
        raise
    finally:
        session.close()

if __name__ == "__main__":
    load_json_data()
