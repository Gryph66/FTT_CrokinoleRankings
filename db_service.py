from database import (
    get_db_session, Tournament, Player, TournamentResult, 
    RatingChange, SystemParameters, init_db, TournamentFSI,
    SeasonEventPoints, SeasonLeaderboard, PointsParameters
)
from sqlalchemy import desc, func
from sqlalchemy.orm import joinedload
from typing import List, Dict, Optional, Tuple
import pandas as pd
from datetime import datetime
from decimal import Decimal, InvalidOperation


def normalize_season(value) -> str:
    """
    Normalize season values to consistent string format.
    Handles: 16, 16.0, "16", "16.0", " 16 " → "16"
    
    Args:
        value: Season value (int, float, or string)
    
    Returns:
        Normalized season as string (e.g., "16")
    """
    if pd.isna(value):
        raise ValueError("Season cannot be empty")
    
    # Convert to string and strip whitespace
    season_str = str(value).strip()
    
    if not season_str:
        raise ValueError("Season cannot be empty")
    
    try:
        # Try to convert to Decimal to handle both int and float strings
        season_decimal = Decimal(season_str)
        # Convert to int to remove decimals (16.0 → 16)
        season_int = int(season_decimal)
        # Return as string
        return str(season_int)
    except (InvalidOperation, ValueError):
        # If conversion fails, return the cleaned string as-is
        # This handles cases like "2024-25" or other non-numeric formats
        return season_str


def get_tournament_group(tier: str) -> str:
    """
    Map tournament tier to tournament group using smart extraction.
    
    Special case: Tier 1/2/3 → NCA
    General case: Extract group name from tier (e.g., "UK Tier" → "UK", "Hungary Tier" → "Hungary")
    
    Args:
        tier: Tournament tier (e.g., "Tier 1", "UK Tier", "Hungary Tier")
    
    Returns:
        Tournament group (e.g., "NCA", "UK", "Hungary", or "Other")
    """
    if not tier:
        return "Other"
    
    tier_stripped = tier.strip()
    tier_upper = tier_stripped.upper()
    
    # Special case: Tier 1, 2, 3 → NCA
    if tier_upper in ('TIER 1', 'TIER 2', 'TIER 3'):
        return "NCA"
    
    # General case: Extract group name from "{GROUP} Tier" pattern
    # Examples: "UK Tier" → "UK", "Hungary Tier" → "Hungary"
    if ' TIER' in tier_upper:
        # Extract the part before " Tier" and capitalize properly
        group_name = tier_stripped.split(' Tier')[0].strip()
        # Convert to title case for consistency (e.g., "uk" → "UK")
        return group_name.upper()
    
    # If no pattern matches, return the tier as-is (capitalized)
    return tier_stripped.upper() if tier_stripped else "Other"


class DatabaseService:
    def __init__(self):
        init_db()
        self.migrate_tournament_groups()
    
    def get_session(self):
        """Get a database session for bulk operations. Use with context manager."""
        return get_db_session()
    
    def migrate_tournament_groups(self):
        """
        Automatically populate tournament_group for any tournaments that have NULL values.
        This migration runs on startup and is idempotent (safe to run multiple times).
        
        Uses get_tournament_group() to intelligently derive group names from tier:
        - "Tier 1/2/3" → "NCA"
        - "UK Tier" → "UK"
        - "Hungary Tier" → "Hungary"
        - etc.
        """
        db = get_db_session()
        try:
            # Find tournaments with NULL tournament_group
            tournaments_to_update = db.query(Tournament).filter(
                Tournament.tournament_group.is_(None)
            ).all()
            
            if tournaments_to_update:
                updated_count = 0
                for tournament in tournaments_to_update:
                    if tournament.tier:
                        tournament.tournament_group = get_tournament_group(tournament.tier)
                        updated_count += 1
                
                db.commit()
                if updated_count > 0:
                    print(f"✅ Migrated {updated_count} tournaments with tournament_group values")
        except Exception as e:
            db.rollback()
            print(f"⚠️ Tournament group migration failed: {e}")
        finally:
            db.close()
    
    def get_or_create_player(self, name: str, mu: float = 25.0, sigma: float = 8.333) -> Player:
        db = get_db_session()
        try:
            player = db.query(Player).filter(Player.name == name).first()
            if not player:
                player = Player(
                    name=name,
                    current_rating_mu=mu,
                    current_rating_sigma=sigma,
                    tournaments_played=0
                )
                db.add(player)
                db.commit()
                db.refresh(player)
            return player
        finally:
            db.close()
    
    def save_tournament(self, season: str, event_name: str, tier: str, 
                       num_players: int, avg_rating_before: float, 
                       avg_rating_after: float, top_players: List[str]) -> Tournament:
        db = get_db_session()
        try:
            tournament = Tournament(
                season=season,
                event_name=event_name,
                tier=tier,
                tournament_group=get_tournament_group(tier),
                num_players=num_players,
                avg_rating_before=avg_rating_before,
                avg_rating_after=avg_rating_after
            )
            db.add(tournament)
            db.commit()
            db.refresh(tournament)
            return tournament
        finally:
            db.close()
    
    def save_tournament_result(self, tournament_id: int, player_id: int, place: int):
        db = get_db_session()
        try:
            result = TournamentResult(
                tournament_id=tournament_id,
                player_id=player_id,
                place=place
            )
            db.add(result)
            db.commit()
        finally:
            db.close()
    
    def save_rating_change(self, tournament_id: int, player_id: int, place: int,
                          before_mu: float, before_sigma: float, 
                          after_mu: float, after_sigma: float,
                          mu_change: float, sigma_change: float,
                          conservative_before: float, conservative_after: float):
        db = get_db_session()
        try:
            change = RatingChange(
                tournament_id=tournament_id,
                player_id=player_id,
                place=place,
                before_mu=before_mu,
                before_sigma=before_sigma,
                after_mu=after_mu,
                after_sigma=after_sigma,
                mu_change=mu_change,
                sigma_change=sigma_change,
                conservative_rating_before=conservative_before,
                conservative_rating_after=conservative_after
            )
            db.add(change)
            db.commit()
        finally:
            db.close()
    
    def update_player_rating(self, player_id: int, mu: float, sigma: float):
        db = get_db_session()
        try:
            player = db.query(Player).filter(Player.id == player_id).first()
            if player:
                player.current_rating_mu = mu
                player.current_rating_sigma = sigma
                player.tournaments_played += 1
                player.updated_at = datetime.utcnow()
                db.commit()
        finally:
            db.close()
    
    def get_all_players(self) -> List[Player]:
        db = get_db_session()
        try:
            return db.query(Player).all()
        finally:
            db.close()
    
    def get_player_by_name(self, name: str) -> Optional[Player]:
        db = get_db_session()
        try:
            return db.query(Player).filter(Player.name == name).first()
        finally:
            db.close()
    
    def get_player_rating_history(self, player_id: int) -> List[RatingChange]:
        db = get_db_session()
        try:
            # Deterministic ordering: tournament_date → sequence_order → created_at → id
            return db.query(RatingChange).join(
                Tournament, RatingChange.tournament_id == Tournament.id
            ).filter(
                RatingChange.player_id == player_id
            ).order_by(
                Tournament.tournament_date.asc().nullslast(),
                Tournament.sequence_order.asc().nullslast(),
                Tournament.created_at.asc(),
                Tournament.id.asc()
            ).all()
        finally:
            db.close()
    
    def get_all_tournaments(self) -> List[Tournament]:
        """Get all tournaments in chronological order."""
        return self.get_tournaments_chronological()
    
    def get_tournament_details(self, tournament_id: int) -> Optional[Tournament]:
        db = get_db_session()
        try:
            return db.query(Tournament).filter(Tournament.id == tournament_id).first()
        finally:
            db.close()
    
    def get_rating_changes_for_tournament(self, tournament_id: int) -> List[RatingChange]:
        db = get_db_session()
        try:
            return db.query(RatingChange).options(joinedload(RatingChange.player)).filter(
                RatingChange.tournament_id == tournament_id
            ).order_by(RatingChange.place).all()
        finally:
            db.close()
    
    def get_all_rating_changes(self) -> List[RatingChange]:
        db = get_db_session()
        try:
            # Deterministic ordering: tournament_date → sequence_order → created_at → id → place
            return db.query(RatingChange).join(
                Tournament, RatingChange.tournament_id == Tournament.id
            ).options(
                joinedload(RatingChange.player)
            ).order_by(
                Tournament.tournament_date.asc().nullslast(),
                Tournament.sequence_order.asc().nullslast(),
                Tournament.created_at.asc(),
                Tournament.id.asc(),
                RatingChange.place.asc()
            ).all()
        finally:
            db.close()
    
    def get_system_parameters(self) -> SystemParameters:
        db = get_db_session()
        try:
            params = db.query(SystemParameters).filter(
                SystemParameters.is_active == 1
            ).first()
            
            if not params:
                params = SystemParameters(
                    mu=25.0,
                    sigma=8.333,
                    beta=4.166,
                    tau=0.083,
                    draw_probability=0.0,
                    is_active=1,
                    description="Default TrueSkill parameters"
                )
                db.add(params)
                db.commit()
                db.refresh(params)
            
            return params
        finally:
            db.close()
    
    def save_system_parameters(self, mu: float, sigma: float, beta: float, 
                               tau: float, draw_probability: float, 
                               description: str = None) -> SystemParameters:
        db = get_db_session()
        try:
            db.query(SystemParameters).update({SystemParameters.is_active: 0})
            
            params = SystemParameters(
                mu=mu,
                sigma=sigma,
                beta=beta,
                tau=tau,
                draw_probability=draw_probability,
                is_active=1,
                description=description
            )
            db.add(params)
            db.commit()
            db.refresh(params)
            return params
        finally:
            db.close()

    def get_points_parameters(self) -> PointsParameters:
        db = get_db_session()
        try:
            params = db.query(PointsParameters).filter(
                PointsParameters.is_active == 1
            ).first()
            
            if not params:
                # Create default parameters if none exist
                params = PointsParameters(
                    max_points=50.0,
                    alpha=1.4,
                    bonus_scale=0.0,
                    fsi_min=0.8,
                    fsi_max=1.6,
                    fsi_scaling_factor=6.0,
                    top_n_for_fsi=20,
                    best_tournaments_per_season=5,
                    top_tier_fsi_threshold=1.35,
                    top_tier_base_points=60.0,
                    normal_tier_base_points=50.0,
                    low_tier_base_points=40.0,
                    low_tier_fsi_threshold=1.0,
                    doubles_top_n_for_fsi=8,
                    doubles_alpha=2.0,
                    is_active=1,
                    description="Default FWP parameters"
                )
                db.add(params)
                db.commit()
                db.refresh(params)
            
            return params
        finally:
            db.close()

    def save_points_parameters(self, fsi_min: float, fsi_max: float, 
                              fsi_scaling_factor: float = 6.0,
                              description: str = None) -> PointsParameters:
        """
        Update points parameters.
        """
        db = get_db_session()
        try:
            # Get current active params to copy other values
            current = db.query(PointsParameters).filter(
                PointsParameters.is_active == 1
            ).first()
            
            if not current:
                # Should not happen if get_points_parameters was called, but handle safely
                current = self.get_points_parameters()
            
            # Deactivate current
            db.query(PointsParameters).update({PointsParameters.is_active: 0})
            
            # Create new params
            params = PointsParameters(
                max_points=current.max_points,
                alpha=current.alpha,
                bonus_scale=current.bonus_scale,
                fsi_min=fsi_min,
                fsi_max=fsi_max,
                fsi_scaling_factor=fsi_scaling_factor,
                top_n_for_fsi=current.top_n_for_fsi,
                best_tournaments_per_season=current.best_tournaments_per_season,
                top_tier_fsi_threshold=current.top_tier_fsi_threshold,
                top_tier_base_points=current.top_tier_base_points,
                normal_tier_base_points=current.normal_tier_base_points,
                low_tier_base_points=current.low_tier_base_points,
                low_tier_fsi_threshold=current.low_tier_fsi_threshold,
                doubles_top_n_for_fsi=current.doubles_top_n_for_fsi,
                doubles_alpha=current.doubles_alpha,
                is_active=1,
                description=description or f"Updated FSI params: {fsi_min}-{fsi_max}, scale={fsi_scaling_factor}"
            )
            db.add(params)
            db.commit()
            db.refresh(params)
            return params
        finally:
            db.close()
    
    def clear_all_data(self):
        """
        Clear all tournament and player data from the database.
        Deletes tables in correct order to respect foreign key constraints:
        1. Child tables first (season_leaderboards, season_event_points, tournament_fsi, etc.)
        2. Parent tables last (tournaments, players)
        
        Note: SystemParameters and PointsParameters are preserved as they're configuration tables.
        """
        db = get_db_session()
        try:
            # Delete child tables first (in order of dependency)
            db.query(SeasonLeaderboard).delete()      # References season_event_points & players
            db.query(SeasonEventPoints).delete()      # References tournaments & players
            db.query(TournamentFSI).delete()          # References tournaments
            db.query(RatingChange).delete()           # References tournaments & players
            db.query(TournamentResult).delete()       # References tournaments & players
            
            # Delete parent tables last
            db.query(Tournament).delete()             # Parent table
            db.query(Player).delete()                 # Parent table
            
            db.commit()
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()
    
    def tournament_exists(self, season: str, event_name: str, tier: str) -> bool:
        db = get_db_session()
        try:
            tournament = db.query(Tournament).filter(
                Tournament.season == season,
                Tournament.event_name == event_name,
                Tournament.tier == tier
            ).first()
            return tournament is not None
        finally:
            db.close()
    
    def get_tournament_id(self, season: str, event_name: str, tier: str) -> int:
        db = get_db_session()
        try:
            tournament = db.query(Tournament).filter(
                Tournament.season == season,
                Tournament.event_name == event_name,
                Tournament.tier == tier
            ).first()
            return tournament.id if tournament else None
        finally:
            db.close()
    
    def get_players_dataframe(self) -> pd.DataFrame:
        db = get_db_session()
        try:
            players = db.query(Player).all()
            data = []
            for player in players:
                conservative_rating = player.current_rating_mu - 3 * player.current_rating_sigma
                data.append({
                    'player': player.name,
                    'rating': player.current_rating_mu,
                    'uncertainty': player.current_rating_sigma,
                    'conservative_rating': conservative_rating,
                    'tournaments_played': player.tournaments_played
                })
            
            df = pd.DataFrame(data)
            if len(df) > 0:
                df = df.sort_values('conservative_rating', ascending=False).reset_index(drop=True)
                df['rank'] = df.index + 1
                return df[['rank', 'player', 'rating', 'uncertainty', 'conservative_rating', 'tournaments_played']]
            return df
        finally:
            db.close()
    
    def get_tournaments_dataframe(self) -> pd.DataFrame:
        db = get_db_session()
        try:
            tournaments = db.query(Tournament).all()
            data = []
            for t in tournaments:
                data.append({
                    'id': t.id,
                    'tournament': t.event_name,
                    'season': t.season,
                    'tier': t.tier,
                    'tournament_group': t.tournament_group,
                    'tournament_format': t.tournament_format,
                    'tournament_date': t.tournament_date,
                    'num_players': t.num_players,
                    'avg_rating_before': t.avg_rating_before,
                    'avg_rating_after': t.avg_rating_after
                })
            return pd.DataFrame(data)
        finally:
            db.close()
    
    def update_tournament_date(self, tournament_id: int, tournament_date: datetime):
        """Update the date for a tournament."""
        db = get_db_session()
        try:
            tournament = db.query(Tournament).filter(Tournament.id == tournament_id).first()
            if tournament:
                tournament.tournament_date = tournament_date
                db.commit()
        finally:
            db.close()
    
    def update_tournament_sequence(self, tournament_id: int, sequence_order: int):
        """Update the sequence order for a tournament."""
        db = get_db_session()
        try:
            tournament = db.query(Tournament).filter(Tournament.id == tournament_id).first()
            if tournament:
                tournament.sequence_order = sequence_order
                db.commit()
        finally:
            db.close()
    
    def get_tournaments_chronological(self) -> List[Tournament]:
        """Get tournaments in chronological order (by tournament_date, falling back to created_at)."""
        db = get_db_session()
        try:
            # Deterministic ordering: tournament_date → sequence_order → created_at → id
            return db.query(Tournament).order_by(
                Tournament.tournament_date.asc().nullslast(),
                Tournament.sequence_order.asc().nullslast(),
                Tournament.created_at.asc(),
                Tournament.id.asc()
            ).all()
        finally:
            db.close()
    
    def auto_assign_tournament_sequence(self):
        """Automatically assign sequence numbers to tournaments based on their current order."""
        db = get_db_session()
        try:
            tournaments = db.query(Tournament).order_by(
                Tournament.tournament_date.asc().nullslast(),
                Tournament.sequence_order.asc().nullslast(),
                Tournament.created_at.asc()
            ).all()
            
            for i, tournament in enumerate(tournaments, start=1):
                tournament.sequence_order = i
            
            db.commit()
        finally:
            db.close()
    
    def reset_all_player_ratings(self, mu: float = 25.0, sigma: float = 8.333):
        """Reset all player ratings to default values."""
        db = get_db_session()
        try:
            players = db.query(Player).all()
            for player in players:
                player.current_rating_mu = mu
                player.current_rating_sigma = sigma
                player.tournaments_played = 0
            db.commit()
        finally:
            db.close()
    
    def bulk_reset_all_player_ratings(self, session, mu: float = 25.0, sigma: float = 8.333):
        """Bulk reset all player ratings using single UPDATE (optimized for recalculation)."""
        session.query(Player).update({
            Player.current_rating_mu: mu,
            Player.current_rating_sigma: sigma,
            Player.tournaments_played: 0
        })
    
    def clear_rating_changes(self):
        """Clear all rating change records (for recalculation)."""
        db = get_db_session()
        try:
            db.query(RatingChange).delete()
            db.commit()
        finally:
            db.close()
    
    def bulk_clear_rating_changes(self, session):
        """Bulk clear all rating changes using single DELETE (optimized for recalculation)."""
        session.query(RatingChange).delete()
    
    def get_tournament_results_with_players(self, tournament_id: int) -> List[TournamentResult]:
        """Get tournament results with player data eagerly loaded."""
        db = get_db_session()
        try:
            return db.query(TournamentResult).options(
                joinedload(TournamentResult.player)
            ).filter(
                TournamentResult.tournament_id == tournament_id
            ).order_by(TournamentResult.place).all()
        finally:
            db.close()
    
    def bulk_upload_tournaments(self, tournaments_data: List[Dict]) -> Dict:
        """
        Bulk upload tournaments WITHOUT calculating ratings (for CSV import optimization).
        Ratings will be calculated later via recalculate_all_ratings().
        
        Args:
            tournaments_data: List of dicts with keys:
                - season, event_name, tier
                - players_data: List of (player_name, place)
                - tournament_date (optional)
                - sequence_order (optional)
        
        Returns:
            Dict with 'processed', 'skipped', 'status' keys
        """
        from datetime import datetime
        
        session = self.get_session()
        
        try:
            processed_count = 0
            skipped_count = 0
            
            # Step 1: Preload all existing tournaments to detect duplicates
            existing_tournaments = session.query(Tournament).all()
            existing_keys = {
                (t.season, t.event_name, t.tier): t.id 
                for t in existing_tournaments
            }
            
            # Step 2: Preload all players and create lookup
            all_players = session.query(Player).all()
            player_lookup = {p.name: p for p in all_players}
            
            # Collect all new objects for bulk operations
            new_players = []
            new_tournaments = []
            new_results = []
            
            # Step 3: Process each tournament
            for t_data in tournaments_data:
                season = normalize_season(t_data['season'])
                event_name = t_data['event_name']
                tier = t_data['tier']
                key = (season, event_name, tier)
                
                # Check if tournament already exists
                if key in existing_keys:
                    tournament_id = existing_keys[key]
                    tournament = session.query(Tournament).filter(Tournament.id == tournament_id).first()
                    
                    # Update metadata if provided
                    if t_data.get('tournament_date'):
                        tournament.tournament_date = t_data['tournament_date']
                    if t_data.get('sequence_order'):
                        tournament.sequence_order = t_data['sequence_order']
                    
                    skipped_count += 1
                    continue
                
                # Detect tournament format by checking player names
                players_data = t_data['players_data']  # List of (player_name, place)
                
                # Count how many entries contain "/" to detect format
                has_slash_count = sum(1 for player_name, _ in players_data if '/' in player_name)
                
                # Validate: All entries must be same format (all singles OR all doubles, no mixing)
                if has_slash_count > 0 and has_slash_count < len(players_data):
                    raise ValueError(f"Mixed singles/doubles format in tournament {event_name}. All entries must use the same format.")
                
                is_doubles = has_slash_count > 0
                tournament_format = 'doubles' if is_doubles else 'singles'
                
                # Parse teams and create individual player entries for doubles
                parsed_players_data = []  # Will store: (player_name, place, team_key, teammate_name) or (player_name, place, None, None)
                
                if is_doubles:
                    # Parse doubles teams
                    for team_name, place in players_data:
                        # Robust team parsing with error handling
                        if '/' not in team_name:
                            raise ValueError(f"Doubles tournament but entry missing '/': {team_name}")
                        
                        # Split on "/" with maxsplit=1 to handle names with slashes
                        parts = team_name.split('/', maxsplit=1)
                        if len(parts) != 2:
                            raise ValueError(f"Invalid doubles team format: {team_name}. Expected 'Player1/Player2'")
                        
                        player1, player2 = parts[0].strip(), parts[1].strip()
                        
                        # Validate player names are non-empty
                        if not player1 or not player2:
                            raise ValueError(f"Empty player name in team: {team_name}")
                        
                        # Create stable team_key (sorted alphabetically for consistency)
                        team_key = '/'.join(sorted([player1, player2]))
                        
                        # Add both players to parsed list
                        parsed_players_data.append((player1, place, team_key, player2))
                        parsed_players_data.append((player2, place, team_key, player1))
                else:
                    # Singles tournament
                    for player_name, place in players_data:
                        parsed_players_data.append((player_name, place, None, None))
                
                # Create missing players
                for player_name, _, _, _ in parsed_players_data:
                    if player_name not in player_lookup:
                        new_player = Player(
                            name=player_name,
                            current_rating_mu=0.0,  # TTT default (was 25.0)
                            current_rating_sigma=1.667,  # TTT default (was 8.333)
                            tournaments_played=0
                        )
                        new_players.append(new_player)
                
                # Flush players to get IDs
                if new_players:
                    session.bulk_save_objects(new_players, return_defaults=True)
                    session.flush()
                    # Update lookup with new players
                    for p in new_players:
                        player_lookup[p.name] = p
                    new_players = []  # Clear for next batch
                
                # Create tournament
                # IMPORTANT: num_players must match TournamentResult row count for FSI/points calculations
                # For doubles, this is 2x the number of teams since each player gets a row
                tournament = Tournament(
                    season=season,
                    event_name=event_name,
                    tier=tier,
                    tournament_group=get_tournament_group(tier),
                    tournament_format=tournament_format,
                    num_players=len(parsed_players_data),  # Actual number of TournamentResult rows
                    avg_rating_before=0.0,  # Will be calculated during recalculation
                    avg_rating_after=0.0,
                    tournament_date=t_data.get('tournament_date'),
                    sequence_order=t_data.get('sequence_order')
                )
                session.add(tournament)
                session.flush()  # Get tournament ID
                
                # Add tournament to existing_keys to prevent duplicates in same batch
                existing_keys[key] = tournament.id
                
                # Create tournament results with rating snapshots for doubles
                for player_name, place, team_key, teammate_name in parsed_players_data:
                    player = player_lookup[player_name]
                    
                    # For doubles, capture current rating as snapshot (won't be updated by TrueSkill)
                    if is_doubles:
                        result = TournamentResult(
                            tournament_id=tournament.id,
                            player_id=player.id,
                            place=place,
                            before_mu=player.current_rating_mu,
                            before_sigma=player.current_rating_sigma,
                            team_key=team_key
                        )
                    else:
                        # Singles - no snapshots needed (TrueSkill will create RatingChange records)
                        result = TournamentResult(
                            tournament_id=tournament.id,
                            player_id=player.id,
                            place=place
                        )
                    new_results.append(result)
                
                processed_count += 1
            
            # Bulk insert all tournament results
            if new_results:
                session.bulk_save_objects(new_results)
            
            # Commit all changes in one transaction
            session.commit()
            
            return {
                'status': 'success',
                'processed': processed_count,
                'skipped': skipped_count
            }
            
        except Exception as e:
            session.rollback()
            return {
                'status': 'error',
                'message': str(e),
                'processed': 0,
                'skipped': 0
            }
        finally:
            session.close()
