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
    
    # Create all tables
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
        with open('data/players.json', 'r') as f:
            players_data = json.load(f)
        for p in players_data:
            player = Player(
                id=p['id'],
                name=p['name'],
                current_rating_mu=p.get('current_rating_mu', 0.0),
                current_rating_sigma=p.get('current_rating_sigma', 1.667),
                tournaments_played=p.get('tournaments_played', 0)
            )
            session.add(player)
        session.commit()
        print(f"Loaded {len(players_data)} players")
        
        print("Loading tournaments...")
        with open('data/tournaments.json', 'r') as f:
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
        with open('data/fsi_trends.json', 'r') as f:
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
        with open('data/event_points.json', 'r') as f:
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
        with open('data/season_standings.json', 'r') as f:
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
        
        print("✅ All data loaded successfully!")
        
    except Exception as e:
        session.rollback()
        print(f"❌ Error loading data: {e}")
        raise
    finally:
        session.close()

if __name__ == "__main__":
    load_json_data()
