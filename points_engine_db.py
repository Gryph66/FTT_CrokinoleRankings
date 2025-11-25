"""
Field-Weighted Points (FWP) Calculation Engine

This engine calculates season standings based on Field Strength Index (FSI) and placement points.
It runs alongside the existing TrueSkill system without modifying it.
"""

import pandas as pd
from typing import Dict, List, Tuple
from datetime import datetime
from database import (
    get_db_session, 
    PointsParameters, 
    TournamentFSI,
    SeasonEventPoints,
    SeasonLeaderboard,
    Tournament,
    Player,
    RatingChange,
    TournamentResult
)
from sqlalchemy import func
import json


class PointsEngineDB:
    def __init__(self, use_db_params=True):
        """
        Initialize the Points calculation engine.
        
        Args:
            use_db_params: If True, load parameters from database. If False, use defaults.
        """
        if use_db_params:
            with get_db_session() as session:
                params = session.query(PointsParameters).filter_by(is_active=1).first()
                if params:
                    self.max_points = params.max_points  # Legacy - not used in calculations
                    self.alpha = params.alpha
                    self.bonus_scale = params.bonus_scale
                    self.fsi_min = params.fsi_min
                    self.fsi_max = params.fsi_max
                    self.fsi_scaling_factor = getattr(params, 'fsi_scaling_factor', 6.0)
                    self.top_n_for_fsi = params.top_n_for_fsi
                    self.best_tournaments_per_season = params.best_tournaments_per_season
                    
                    # Tiered base points system
                    self.top_tier_fsi_threshold = params.top_tier_fsi_threshold
                    self.top_tier_base_points = params.top_tier_base_points
                    self.normal_tier_base_points = params.normal_tier_base_points
                    self.low_tier_base_points = params.low_tier_base_points
                    self.low_tier_fsi_threshold = params.low_tier_fsi_threshold
                    
                    # Doubles-specific parameters
                    self.doubles_top_n_for_fsi = params.doubles_top_n_for_fsi
                    self.doubles_alpha = params.doubles_alpha
                    
                    # Validate tiered parameters
                    self._validate_parameters()
                else:
                    # No params in DB, create defaults
                    self._use_default_params()
                    self._save_default_params()
        else:
            self._use_default_params()
    
    def _use_default_params(self):
        """Set default FWP parameters."""
        self.max_points = 50.0  # Legacy - not used in calculations
        self.alpha = 1.4
        self.bonus_scale = 0.0
        self.fsi_min = 0.5  # Floor for very weak tournaments
        self.fsi_max = 1.5  # Ceiling for elite tournaments
        self.fsi_scaling_factor = 2.2  # Simple scaling: FSI = avg_top_mu / 2.2
        self.top_n_for_fsi = 20
        self.best_tournaments_per_season = 5
        
        # Tiered base points system
        self.top_tier_fsi_threshold = 1.35
        self.top_tier_base_points = 60.0
        self.normal_tier_base_points = 50.0
        self.low_tier_base_points = 40.0
        self.low_tier_fsi_threshold = 1.0
        
        # Doubles-specific parameters
        self.doubles_top_n_for_fsi = 8
        self.doubles_alpha = 2.0
    
    def _validate_parameters(self):
        """Validate that parameters make sense."""
        # Threshold validation
        if self.low_tier_fsi_threshold >= self.top_tier_fsi_threshold:
            raise ValueError(f"Low tier FSI threshold ({self.low_tier_fsi_threshold}) must be less than top tier threshold ({self.top_tier_fsi_threshold})")
        
        # Positive points validation
        if self.top_tier_base_points <= 0 or self.normal_tier_base_points <= 0 or self.low_tier_base_points <= 0:
            raise ValueError("All base points values must be positive")
        
        # FSI bounds validation
        if self.fsi_min >= self.fsi_max:
            raise ValueError(f"FSI min ({self.fsi_min}) must be less than FSI max ({self.fsi_max})")
    
    def _save_default_params(self):
        """Save default parameters to database."""
        with get_db_session() as session:
            params = PointsParameters(
                max_points=self.max_points,
                alpha=self.alpha,
                bonus_scale=self.bonus_scale,
                fsi_min=self.fsi_min,
                fsi_max=self.fsi_max,
                top_n_for_fsi=self.top_n_for_fsi,
                best_tournaments_per_season=self.best_tournaments_per_season,
                
                # Tiered base points
                top_tier_fsi_threshold=self.top_tier_fsi_threshold,
                top_tier_base_points=self.top_tier_base_points,
                normal_tier_base_points=self.normal_tier_base_points,
                low_tier_base_points=self.low_tier_base_points,
                low_tier_fsi_threshold=self.low_tier_fsi_threshold,
                
                # Doubles-specific
                doubles_top_n_for_fsi=self.doubles_top_n_for_fsi,
                doubles_alpha=self.doubles_alpha,
                
                is_active=1,
                description="Default FWP parameters with tiered base points and doubles support"
            )
            session.add(params)
            session.commit()
            
    def reload_parameters(self):
        """Reload parameters from the database."""
        with get_db_session() as session:
            params = session.query(PointsParameters).filter_by(is_active=1).first()
            if params:
                self.max_points = params.max_points
                self.alpha = params.alpha
                self.bonus_scale = params.bonus_scale
                self.fsi_min = params.fsi_min
                self.fsi_max = params.fsi_max
                self.fsi_scaling_factor = getattr(params, 'fsi_scaling_factor', 6.0)
                self.top_n_for_fsi = params.top_n_for_fsi
                self.best_tournaments_per_season = params.best_tournaments_per_season
                self.top_tier_fsi_threshold = params.top_tier_fsi_threshold
                self.top_tier_base_points = params.top_tier_base_points
                self.normal_tier_base_points = params.normal_tier_base_points
                self.low_tier_base_points = params.low_tier_base_points
                self.low_tier_fsi_threshold = params.low_tier_fsi_threshold
                self.doubles_top_n_for_fsi = params.doubles_top_n_for_fsi
                self.doubles_alpha = params.doubles_alpha
    
    def calculate_fsi(self, pre_event_ratings: Dict[int, Tuple[float, float]]) -> Tuple[float, float]:
        """
        Calculate Field Strength Index for a tournament.
        Uses simple scaling: FSI = avg_top_mu / scaling_factor
        
        Args:
            pre_event_ratings: Dict of {player_id: (mu, sigma)} before the tournament
            
        Returns:
            Tuple of (fsi, avg_top_mu)
        """
        if not pre_event_ratings:
            return 1.0, 0.0
        
        # Get top N player ratings
        mus = [mu for mu, sigma in pre_event_ratings.values()]
        top_mus = sorted(mus, reverse=True)[:min(self.top_n_for_fsi, len(mus))]
        
        if not top_mus:
            return 1.0, 0.0
        
        avg_top_mu = sum(top_mus) / len(top_mus)
        
        # Simple scaling: FSI = avg_top_mu / scaling_factor
        fsi_raw = avg_top_mu / self.fsi_scaling_factor
        
        # Clamp to [fsi_min, fsi_max]
        fsi = max(self.fsi_min, min(fsi_raw, self.fsi_max))
        
        return fsi, avg_top_mu
    
    def get_fsi_details(self, tournament_id: int) -> Dict:
        """
        Get detailed breakdown of FSI calculation for a tournament.
        """
        session = get_db_session()
        try:
            tournament = session.query(Tournament).get(tournament_id)
            if not tournament:
                return {}
            
            top_items = [] # List of dicts (players or teams)
            total_count = 0
            
            if tournament.tournament_format == 'singles':
                # Fetch from RatingChange
                changes = session.query(RatingChange, Player).join(
                    Player, RatingChange.player_id == Player.id
                ).filter(
                    RatingChange.tournament_id == tournament.id
                ).all()
                
                # Deduplicate by player_id to prevent multiple counting
                seen_players = set()
                mus = []
                for rc, player in changes:
                    if player.id in seen_players:
                        continue
                    seen_players.add(player.id)
                    
                    mus.append({
                        'name': player.name,
                        'mu': rc.before_mu,
                        'sigma': rc.before_sigma
                    })
                
                # Sort by mu desc
                sorted_items = sorted(mus, key=lambda x: x['mu'], reverse=True)
                total_count = len(sorted_items)
                
                # Top N
                top_n = min(self.top_n_for_fsi, len(sorted_items))
                top_items = sorted_items[:top_n]
                
            else: # Doubles
                # Fetch from TournamentResult
                results = session.query(TournamentResult, Player).join(
                    Player, TournamentResult.player_id == Player.id
                ).filter(
                    TournamentResult.tournament_id == tournament.id
                ).all()
                
                teams = {} # team_key -> {players: []}
                
                for res, player in results:
                    team_key = res.team_key
                    if team_key not in teams:
                        teams[team_key] = {'players': [], 'player_ids': set()}
                    
                    # Deduplicate players within team
                    if player.id in teams[team_key]['player_ids']:
                        continue
                    teams[team_key]['player_ids'].add(player.id)
                    
                    mu = res.before_mu if res.before_mu is not None else 0.0
                    sigma = res.before_sigma if res.before_sigma is not None else 1.667
                    
                    teams[team_key]['players'].append({
                        'name': player.name,
                        'mu': mu,
                        'sigma': sigma
                    })
                
                # Calculate team averages
                team_ratings = []
                for team_key, data in teams.items():
                    players = data['players']
                    if not players:
                        continue
                    avg_mu = sum(p['mu'] for p in players) / len(players)
                    avg_sigma = sum(p['sigma'] for p in players) / len(players)
                    
                    team_name = " / ".join([p['name'] for p in players])
                    
                    team_ratings.append({
                        'name': team_name,
                        'mu': avg_mu,
                        'sigma': avg_sigma,
                        'is_team': True
                    })
                
                # Sort teams
                sorted_items = sorted(team_ratings, key=lambda x: x['mu'], reverse=True)
                total_count = len(sorted_items)
                
                # Top N Teams
                top_n = min(self.doubles_top_n_for_fsi, len(sorted_items))
                top_items = sorted_items[:top_n]
            
            if not top_items:
                return {'error': 'No players/teams found'}
                
            avg_top_mu = sum(p['mu'] for p in top_items) / len(top_items)
            
            # Simple scaling: FSI = avg_top_mu / scaling_factor
            fsi_raw = avg_top_mu / self.fsi_scaling_factor
                
            fsi_final = max(self.fsi_min, min(fsi_raw, self.fsi_max))
            
            return {
                'tournament': tournament.event_name,
                'format': tournament.tournament_format,
                'total_players': total_count,
                'top_players': top_items, # Can be players or teams
                'avg_top_mu': avg_top_mu,
                'fsi_raw': fsi_raw,
                'fsi_final': fsi_final,
                'params': {
                    'scaling_factor': self.fsi_scaling_factor,
                    'fsi_min': self.fsi_min,
                    'fsi_max': self.fsi_max
                }
            }
            
        finally:
            session.close()

    def calculate_points(self, place: int, field_size: int, fsi: float, 
                        expected_rank: int, alpha: float = None) -> Tuple[float, float, float, float]:
        """
        Calculate points for a player's tournament result using tiered base points.
        
        Args:
            place: Player's finishing position (1 = winner)
            field_size: Total number of players/teams
            fsi: Field Strength Index for this tournament (already clamped)
            expected_rank: Player's expected finish based on pre-event rating
            alpha: Exponential decay factor (defaults to self.alpha, use self.doubles_alpha for doubles)
        
        Returns:
            Tuple of (raw_points, base_points, bonus_points, total_points)
        """
        if alpha is None:
            alpha = self.alpha
        
        # Validate inputs
        if place < 1:
            place = 1
        if place > field_size:
            place = field_size
        if field_size < 1:
            field_size = 1
        
        # Select base points tier based on FSI
        if fsi >= self.top_tier_fsi_threshold:
            base_max_points = self.top_tier_base_points
        elif fsi < self.low_tier_fsi_threshold:
            base_max_points = self.low_tier_base_points
        else:
            base_max_points = self.normal_tier_base_points
        
        # Calculate raw points from placement using tier-specific base
        if field_size == 1:
            raw_points = float(base_max_points)
        else:
            # Normalized rank: 0 for winner, 1 for last place
            # Clamp to [0, 1] to prevent negative numbers that cause complex results
            rnorm = max(0.0, min(1.0, (place - 1) / (field_size - 1)))
            # Top-heavy curve with exponential decay
            # Ensure base is non-negative before raising to power
            base_value = max(0.0, 1.0 - rnorm)
            raw_points = float(base_max_points * (base_value ** alpha))
        
        # Scale by field strength
        base_points = float(raw_points * fsi)
        
        # Overperformance bonus (PVE = Place vs Expected)
        pve = expected_rank - place  # Positive = did better than expected
        bonus_points = float(fsi * self.bonus_scale * pve)
        
        total_points = float(base_points + bonus_points)
        
        return raw_points, base_points, bonus_points, total_points
    
    def _process_doubles_tournament(self, session, tournament, all_players):
        """
        Process a doubles tournament for points calculation.
        Uses TournamentResult with rating snapshots instead of RatingChange records.
        
        Args:
            session: Database session
            tournament: Tournament object
            all_players: Dict of {player_id: player_name}
        """
        from database import TournamentResult
        
        # Get all TournamentResult entries for this doubles tournament
        results = session.query(TournamentResult).filter_by(
            tournament_id=tournament.id
        ).order_by(TournamentResult.place.asc()).all()
        
        if not results:
            return
        
        # Group by team_key to get unique teams
        teams = {}  # team_key -> {place, player_ids: [(id, mu, sigma)]}
        
        for result in results:
            team_key = result.team_key
            if team_key not in teams:
                teams[team_key] = {
                    'place': result.place,
                    'players': []
                }
            
            # Validate rating snapshot exists
            if result.before_mu is None or result.before_sigma is None:
                # Fallback to current player rating if snapshot missing
                player = session.query(Player).filter_by(id=result.player_id).first()
                before_mu = player.current_rating_mu if player.current_rating_mu is not None else 25.0
                before_sigma = player.current_rating_sigma if player.current_rating_sigma is not None else 8.333
            else:
                before_mu = float(result.before_mu)
                before_sigma = float(result.before_sigma)
            
            teams[team_key]['players'].append({
                'player_id': result.player_id,
                'before_mu': before_mu,
                'before_sigma': before_sigma
            })
        
        # Validate each team has exactly 2 players
        for team_key, team_data in teams.items():
            if len(team_data['players']) != 2:
                raise ValueError(f"Doubles team {team_key} has {len(team_data['players'])} players, expected 2")
        
        # Build team-level ratings (average of both players)
        team_ratings = {}  # team_key -> (avg_mu, avg_sigma)
        team_places = {}   # team_key -> place
        
        for team_key, team_data in teams.items():
            p1, p2 = team_data['players']
            avg_mu = float((p1['before_mu'] + p2['before_mu']) / 2)
            avg_sigma = float((p1['before_sigma'] + p2['before_sigma']) / 2)
            team_ratings[team_key] = (avg_mu, avg_sigma)
            team_places[team_key] = team_data['place']
        
        # Calculate FSI using top N team averages (doubles_top_n_for_fsi)
        team_mus = [mu for mu, sigma in team_ratings.values()]
        top_mus = sorted(team_mus, reverse=True)[:min(self.doubles_top_n_for_fsi, len(team_mus))]
        
        if not top_mus:
            fsi, avg_top_mu = 1.0, 0.0
        else:
            avg_top_mu = sum(top_mus) / len(top_mus)
            
            # Simple scaling: FSI = avg_top_mu / scaling_factor
            fsi_raw = avg_top_mu / self.fsi_scaling_factor
            
            fsi = max(self.fsi_min, min(fsi_raw, self.fsi_max))

        
        # Save tournament FSI
        tournament_fsi = TournamentFSI(
            tournament_id=tournament.id,
            season=tournament.season,
            fsi=fsi,
            avg_top_mu=avg_top_mu
        )
        session.add(tournament_fsi)
        
        # Calculate avg_rating_before for the tournament (all players)
        all_mus = []
        for team_data in teams.values():
            for player_data in team_data['players']:
                all_mus.append(float(player_data['before_mu']))
        
        if all_mus:
            avg_rating_all = sum(all_mus) / len(all_mus)
            tournament.avg_rating_before = avg_rating_all
            tournament.avg_rating_after = avg_rating_all # Ratings don't change in doubles
            session.add(tournament)

        
        # Calculate expected ranks at team level (sort by avg mu)
        sorted_teams = sorted(team_ratings.keys(), key=lambda tk: team_ratings[tk][0], reverse=True)
        expected_ranks = {team_key: rank + 1 for rank, team_key in enumerate(sorted_teams)}
        
        # Field size is number of teams
        field_size = len(teams)
        
        # Calculate points for each team and award to both players
        for team_key, team_data in teams.items():
            place = team_data['place']
            expected_rank = expected_ranks[team_key]
            
            # Calculate points using doubles_alpha
            raw_points, base_points, bonus_points, total_points = self.calculate_points(
                place, field_size, fsi, expected_rank, alpha=self.doubles_alpha
            )
            
            overperformance = expected_rank - place
            
            # Award identical points to BOTH players on the team
            for player_data in team_data['players']:
                player_id = player_data['player_id']
                before_mu = float(player_data['before_mu'])
                before_sigma = float(player_data['before_sigma'])
                
                # For doubles, post ratings = pre ratings (no TrueSkill update)
                post_mu = float(before_mu)
                post_sigma = float(before_sigma)
                display_rating = float(post_mu - 3 * post_sigma)
                
                event_points = SeasonEventPoints(
                    tournament_id=tournament.id,
                    player_id=player_id,
                    season=tournament.season,
                    place=place,
                    field_size=field_size,  # Number of teams
                    pre_mu=before_mu,
                    pre_sigma=before_sigma,
                    post_mu=post_mu,
                    post_sigma=post_sigma,
                    display_rating=display_rating,
                    fsi=fsi,
                    raw_points=raw_points,
                    base_points=base_points,
                    expected_rank=expected_rank,
                    overperformance=overperformance,
                    bonus_points=bonus_points,
                    total_points=total_points
                )
                session.add(event_points)
    
    def _update_doubles_rating_snapshots(self, session, tournament, player_rating_tracker):
        """
        Update TournamentResult records with correct pre-event rating snapshots.
        Uses chronologically tracked ratings instead of static values from CSV upload.
        
        Args:
            session: Database session
            tournament: Doubles tournament to update
            player_rating_tracker: Dict of {player_id: (mu, sigma)} from previous tournaments
        """
        from database import TournamentResult
        
        # Get all TournamentResult entries for this doubles tournament
        results = session.query(TournamentResult).filter_by(
            tournament_id=tournament.id
        ).all()
        
        # Update each result with tracked rating (or default if never seen)
        for result in results:
            if result.player_id in player_rating_tracker:
                mu, sigma = player_rating_tracker[result.player_id]
            else:
                # New player - use TTT default rating
                mu, sigma = 0.0, 1.667
            
            result.before_mu = float(mu)
            result.before_sigma = float(sigma)
        
        # Flush to persist changes before processing
        session.flush()
    
    def recalculate_all(self, progress_callback=None):
        """
        Recalculate all points for all tournaments in chronological order.
        This is the main method that processes the entire database.
        
        Args:
            progress_callback: Optional function(current, total, tournament_name) for progress updates
        """
        with get_db_session() as session:
            # Clear existing points data
            session.query(SeasonEventPoints).delete()
            session.query(SeasonLeaderboard).delete()
            session.query(TournamentFSI).delete()
            
            # Get all tournaments in chronological order (same as TrueSkill)
            tournaments = session.query(Tournament).order_by(
                Tournament.tournament_date.asc().nulls_last(),
                Tournament.sequence_order.asc().nulls_last(),
                Tournament.created_at.asc(),
                Tournament.id.asc()
            ).all()
            
            total_tournaments = len(tournaments)
            
            # Preload all players for ID lookups
            all_players = {p.id: p.name for p in session.query(Player).all()}
            
            # Track player ratings chronologically for doubles tournaments
            # This dict stores each player's rating snapshot as tournaments are processed
            player_rating_tracker = {}  # {player_id: (mu, sigma)}
            
            # Process each tournament
            for idx, tournament in enumerate(tournaments):
                if progress_callback:
                    progress_callback(idx + 1, total_tournaments, tournament.event_name)
                
                # Branch based on tournament format
                if tournament.tournament_format == 'doubles':
                    # DOUBLES PROCESSING: Update rating snapshots before processing
                    self._update_doubles_rating_snapshots(session, tournament, player_rating_tracker)
                    self._process_doubles_tournament(session, tournament, all_players)
                    continue  # Skip singles-only logic below
                
                # SINGLES PROCESSING: Use RatingChange records (existing logic)
                # Get tournament results
                results = session.query(RatingChange).filter_by(
                    tournament_id=tournament.id
                ).order_by(RatingChange.place.asc()).all()
                
                if not results:
                    continue
                
                # Build pre-event ratings dict
                pre_event_ratings = {}
                player_places = {}
                post_event_ratings = {}
                
                for result in results:
                    pre_event_ratings[result.player_id] = (result.before_mu, result.before_sigma)
                    post_event_ratings[result.player_id] = (result.after_mu, result.after_sigma)
                    player_places[result.player_id] = result.place
                
                # Calculate FSI for this tournament
                fsi, avg_top_mu = self.calculate_fsi(pre_event_ratings)
                
                # Save tournament FSI
                tournament_fsi = TournamentFSI(
                    tournament_id=tournament.id,
                    season=tournament.season,
                    fsi=fsi,
                    avg_top_mu=avg_top_mu
                )
                session.add(tournament_fsi)
                
                # Calculate expected ranks based on pre-event mu
                sorted_players = sorted(pre_event_ratings.keys(), 
                                      key=lambda p: pre_event_ratings[p][0], 
                                      reverse=True)
                expected_ranks = {player_id: rank + 1 for rank, player_id in enumerate(sorted_players)}
                
                # Calculate points for each player
                field_size = len(results)
                
                for result in results:
                    player_id = result.player_id
                    place = result.place
                    expected_rank = expected_ranks[player_id]
                    
                    # Calculate points
                    raw_points, base_points, bonus_points, total_points = self.calculate_points(
                        place, field_size, fsi, expected_rank
                    )
                    
                    # Calculate overperformance
                    overperformance = expected_rank - place
                    
                    # Save event points
                    event_points = SeasonEventPoints(
                        tournament_id=tournament.id,
                        player_id=player_id,
                        season=tournament.season,
                        place=place,
                        field_size=field_size,
                        pre_mu=result.before_mu,
                        pre_sigma=result.before_sigma,
                        post_mu=result.after_mu,
                        post_sigma=result.after_sigma,
                        display_rating=result.after_mu - 3 * result.after_sigma,
                        fsi=fsi,
                        raw_points=raw_points,
                        base_points=base_points,
                        expected_rank=expected_rank,
                        overperformance=overperformance,
                        bonus_points=bonus_points,
                        total_points=total_points
                    )
                    session.add(event_points)
                    
                    # Track post-tournament rating for future doubles tournaments
                    player_rating_tracker[player_id] = (result.after_mu, result.after_sigma)
            
            # Commit all event points and FSI data
            session.commit()
            
            # Now calculate season leaderboards
            self._calculate_season_leaderboards(session)
            
            session.commit()
    
    def _calculate_season_leaderboards(self, session):
        """Calculate season standings from event points (best N tournaments per player)."""
        # Get all seasons
        seasons = session.query(SeasonEventPoints.season).distinct().all()
        seasons = [s[0] for s in seasons]
        
        for season in seasons:
            # Get all event points for this season
            season_events = session.query(SeasonEventPoints).filter_by(season=season).all()
            
            # Group by player
            player_events = {}
            for event in season_events:
                if event.player_id not in player_events:
                    player_events[event.player_id] = []
                player_events[event.player_id].append(event)
            
            # Calculate standings
            standings = []
            for player_id, events in player_events.items():
                # Sort by total_points descending, take best N
                best_events = sorted(events, key=lambda e: e.total_points, reverse=True)[
                    :self.best_tournaments_per_season
                ]
                
                total_points = sum(e.total_points for e in best_events)
                events_counted = len(best_events)
                top_five_ids = [e.tournament_id for e in best_events]
                
                # Get final display rating (from last event chronologically)
                final_rating = sorted(events, key=lambda e: e.created_at)[-1].display_rating
                
                standings.append({
                    'player_id': player_id,
                    'total_points': total_points,
                    'events_counted': events_counted,
                    'top_five_event_ids': top_five_ids,  # SQLAlchemy JSON column auto-serializes
                    'final_display_rating': final_rating
                })
            
            # Sort by total_points descending, then by final_display_rating
            standings.sort(key=lambda x: (x['total_points'], x['final_display_rating']), reverse=True)
            
            # Assign ranks and save
            for rank, standing in enumerate(standings, start=1):
                leaderboard_entry = SeasonLeaderboard(
                    season=season,
                    player_id=standing['player_id'],
                    total_points=standing['total_points'],
                    events_counted=standing['events_counted'],
                    top_five_event_ids=standing['top_five_event_ids'],  # SQLAlchemy JSON auto-serializes
                    final_display_rating=standing['final_display_rating'],
                    rank=rank
                )
                session.add(leaderboard_entry)
    
    def get_season_standings(self, season: str = None) -> pd.DataFrame:
        """Get season standings, optionally filtered by season."""
        with get_db_session() as session:
            query = session.query(
                SeasonLeaderboard.rank,
                SeasonLeaderboard.season,
                Player.name.label('player'),
                SeasonLeaderboard.total_points,
                SeasonLeaderboard.events_counted,
                SeasonLeaderboard.final_display_rating
            ).join(Player, SeasonLeaderboard.player_id == Player.id)
            
            if season:
                query = query.filter(SeasonLeaderboard.season == season)
            
            query = query.order_by(
                SeasonLeaderboard.season.desc(),
                SeasonLeaderboard.rank.asc()
            )
            
            df = pd.read_sql(query.statement, session.bind)
            return df
    
    def get_event_points(self, tournament_id: int = None, season: str = None) -> pd.DataFrame:
        """Get event-level points, optionally filtered by tournament or season."""
        with get_db_session() as session:
            query = session.query(
                Tournament.event_name,
                Tournament.season,
                Player.name.label('player'),
                SeasonEventPoints.place,
                SeasonEventPoints.field_size,
                SeasonEventPoints.fsi,
                SeasonEventPoints.raw_points,
                SeasonEventPoints.base_points,
                SeasonEventPoints.expected_rank,
                SeasonEventPoints.overperformance,
                SeasonEventPoints.bonus_points,
                SeasonEventPoints.total_points
            ).join(
                Tournament, SeasonEventPoints.tournament_id == Tournament.id
            ).join(
                Player, SeasonEventPoints.player_id == Player.id
            )
            
            if tournament_id:
                query = query.filter(SeasonEventPoints.tournament_id == tournament_id)
            elif season:
                query = query.filter(SeasonEventPoints.season == season)
            
            query = query.order_by(SeasonEventPoints.total_points.desc())
            
            df = pd.read_sql(query.statement, session.bind)
            return df
    
    def get_tournament_fsi(self, season: str = None) -> pd.DataFrame:
        """Get tournament FSI data, optionally filtered by season."""
        with get_db_session() as session:
            query = session.query(
                Tournament.id,
                Tournament.event_name,
                Tournament.season,
                Tournament.tournament_date,
                TournamentFSI.fsi,
                TournamentFSI.avg_top_mu
            ).join(
                TournamentFSI, Tournament.id == TournamentFSI.tournament_id
            )
            
            if season:
                query = query.filter(Tournament.season == season)
            
            query = query.order_by(
                Tournament.tournament_date.asc().nulls_last(),
                Tournament.sequence_order.asc().nulls_last(),
                Tournament.created_at.asc()
            )
            
            df = pd.read_sql(query.statement, session.bind)
            return df
    
    def get_player_top_events(self, player_name: str, season: str = None) -> pd.DataFrame:
        """Get a player's top events with detailed breakdown."""
        with get_db_session() as session:
            # Get player ID
            player = session.query(Player).filter_by(name=player_name).first()
            if not player:
                return pd.DataFrame()
            
            query = session.query(
                Tournament.event_name,
                Tournament.season,
                Tournament.tournament_date,
                SeasonEventPoints.place,
                SeasonEventPoints.field_size,
                SeasonEventPoints.fsi,
                SeasonEventPoints.expected_rank,
                SeasonEventPoints.overperformance,
                SeasonEventPoints.total_points
            ).join(
                Tournament, SeasonEventPoints.tournament_id == Tournament.id
            ).filter(
                SeasonEventPoints.player_id == player.id
            )
            
            if season:
                query = query.filter(SeasonEventPoints.season == season)
            
            query = query.order_by(SeasonEventPoints.total_points.desc())
            
            df = pd.read_sql(query.statement, session.bind)
            return df
