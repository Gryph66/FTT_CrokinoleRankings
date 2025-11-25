import trueskillthroughtime as ttt
import pandas as pd
from typing import Dict, List
from datetime import datetime
import copy
from db_service import DatabaseService
from database import get_db_session, Tournament, RatingChange, Player, TournamentResult
from sqlalchemy import func

class TTTRankingEngine:
    def __init__(self, sigma=1.667, gamma=0.03, beta=1.0):
        """
        Initialize TTT Engine.
        
        Args:
            sigma: Initial uncertainty (default 6.0 for TTT vs 8.333 for TrueSkill)
            gamma: Skill drift over time (default 0.03)
            beta: Performance variance (default 1.0 for TTT vs 4.166 for TrueSkill)
        """
        self.db = DatabaseService()
        self.sigma = sigma
        self.gamma = gamma
        self.beta = beta
        self.mu = 0.0 # TTT standard mean is 0
        
    def get_parameters(self) -> Dict[str, float]:
        """Get current TTT parameters."""
        return {
            'mu': self.mu,
            'sigma': self.sigma,
            'gamma': self.gamma,
            'beta': self.beta,
            'tau': 0.0, # Not used in TTT
            'draw_probability': 0.0 # Not used in TTT
        }

    def update_parameters(self, mu=None, sigma=None, gamma=None, beta=None, tau=None, draw_probability=None):
        """
        Update TTT parameters.
        Note: mu is fixed at 0 for TTT standard implementation.
        tau and draw_probability are ignored.
        """
        if sigma is not None:
            self.sigma = float(sigma)
        if gamma is not None:
            self.gamma = float(gamma)
        if beta is not None:
            self.beta = float(beta)
        # mu, tau, draw_probability are ignored/fixed
        
    def reload_from_db(self):
        """
        Reload data from database.
        For TTT engine, this is a no-op as it fetches fresh data on each request.
        Kept for compatibility with app.py calls.
        """
        pass
        
    def recalculate_all_ratings(self, progress_callback=None):
        """
        Recalculate all ratings using TrueSkill Through Time.
        This processes the entire tournament history as a single batch.
        """
        import trueskill
        import math
        
        try:
            session = self.db.get_session()
            
            # Step 1: Fetch all tournaments and results
            tournaments = session.query(Tournament).order_by(
                Tournament.tournament_date.asc().nullslast(),
                Tournament.sequence_order.asc().nullslast(),
                Tournament.created_at.asc(),
                Tournament.id.asc()
            ).all()
            
            if not tournaments:
                return {'status': 'success', 'message': 'No tournaments to process'}
                
            # Filter out doubles for rating calculation
            singles_tournaments = [t for t in tournaments if t.tournament_format == 'singles']
            
            # Step 2: Prepare data for TTT
            composition = []
            times = []
            
            # Map to keep track of tournament metadata for later update
            tournament_map = [] # List of (tournament_obj, player_ids_in_order)
            
            # Pre-fetch all players to map names to IDs
            all_players = session.query(Player).all()
            player_map = {p.id: p for p in all_players}
            
            # FORWARD PASS STATE
            # We need to calculate "Entering Ratings" (Filtered) for FSI
            # This simulates the online process: what did we know BEFORE the tournament?
            forward_env = trueskill.TrueSkill(
                mu=self.mu, 
                sigma=self.sigma, 
                beta=self.beta, 
                tau=0.0, # TTT uses Gamma for drift, not Tau
                draw_probability=0.0
            )
            
            # {player_id: {'mu': mu, 'sigma': sigma, 'last_time': timestamp}}
            player_forward_state = {}
            
            # Store filtered "before" ratings: {(tournament_id, player_id): (mu, sigma)}
            filtered_entering_ratings = {}
            
            for idx, tournament in enumerate(singles_tournaments):
                results = session.query(TournamentResult).filter(
                    TournamentResult.tournament_id == tournament.id
                ).order_by(TournamentResult.place).all()
                
                if len(results) < 2:
                    continue
                    
                # Time: Days since epoch
                if tournament.tournament_date:
                    ts = tournament.tournament_date.timestamp() / (60 * 60 * 24)
                else:
                    ts = idx * 1.0 
                
                times.append(ts)
                
                # Prepare teams for TTT (composition) and Forward Pass
                teams = []
                player_ids_in_match = []
                forward_teams = [] # For trueskill library
                
                for res in results:
                    p = player_map.get(res.player_id)
                    if p:
                        teams.append([str(p.id)])
                        player_ids_in_match.append(p.id)
                        
                        # FORWARD PASS: Get entering rating
                        state = player_forward_state.get(p.id, {
                            'mu': self.mu, 
                            'sigma': self.sigma, 
                            'last_time': ts # Initialize at current time if new
                        })
                        
                        # Apply Gamma Drift (Brownian Motion)
                        # sigma_new = sqrt(sigma_old^2 + gamma * dt)
                        dt = ts - state['last_time']
                        # Ensure dt is non-negative (should be if sorted correctly)
                        dt = max(0.0, dt)
                        
                        inflated_sigma = math.sqrt(state['sigma']**2 + self.gamma * dt)
                        
                        # Store this "Entering Rating" for FSI/DB
                        filtered_entering_ratings[(tournament.id, p.id)] = (state['mu'], inflated_sigma)
                        
                        # Create rating object for TrueSkill update
                        forward_teams.append((trueskill.Rating(state['mu'], inflated_sigma),))
                
                if len(teams) < 2:
                    continue

                composition.append(teams)
                
                tournament_map.append({
                    'tournament': tournament,
                    'player_ids': player_ids_in_match,
                    'results': results
                })
                
                # FORWARD PASS: Update
                # trueskill.rate expects list of tuples
                try:
                    new_forward_ratings = forward_env.rate(forward_teams)
                    
                    # Update state
                    for i, p_id in enumerate(player_ids_in_match):
                        new_r = new_forward_ratings[i][0]
                        player_forward_state[p_id] = {
                            'mu': new_r.mu,
                            'sigma': new_r.sigma,
                            'last_time': ts
                        }
                except Exception as e:
                    print(f"Forward pass error at {tournament.event_name}: {e}")
                
                if progress_callback:
                    progress_callback(idx, len(singles_tournaments), f"Prep: {tournament.event_name}")

            # Step 3: Run TTT (Smoothing)
            if not composition:
                 return {'status': 'success', 'message': 'No valid singles tournaments found'}

            history = ttt.History(
                composition=composition,
                times=times,
                sigma=self.sigma,
                gamma=self.gamma,
                beta=self.beta
            )
            
            history.convergence(epsilon=0.01, iterations=10)
            
            # Step 4: Update Database
            self.db.bulk_clear_rating_changes(session)
            
            # Get learning curves (history of ratings)
            lc = history.learning_curves()
            
            all_rating_changes = []
            player_final_ratings = {} # player_id -> (mu, sigma)
            
            for t_idx, t_data in enumerate(tournament_map):
                tournament = t_data['tournament']
                player_ids = t_data['player_ids']
                results = t_data['results']
                
                # Calculate tournament averages
                mus_after = []
                mus_before = []
                
                # Track smoothed "before" ratings for each player
                smoothed_before_ratings = {}  # player_id -> (mu, sigma)
                
                for p_idx, player_id in enumerate(player_ids):
                    p_id_str = str(player_id)
                    
                    # Get Smoothed Rating AFTER this tournament
                    player_history = lc.get(p_id_str, [])
                    target_time = times[t_idx]
                    
                    rating_after = None
                    rating_before_smoothed = None
                    
                    # Find the rating at this time and the previous time
                    for h_idx, (time, rating) in enumerate(player_history):
                        if abs(time - target_time) < 0.001:
                            rating_after = rating
                            # Get the previous smoothed rating (before this tournament)
                            if h_idx > 0:
                                rating_before_smoothed = player_history[h_idx - 1][1]
                            else:
                                # First tournament, use initial rating
                                rating_before_smoothed = rating  # or use default (0, 1.667)
                            break
                    
                    if rating_after:
                        # Use SMOOTHED rating for before (not forward pass)
                        # This shows the actual rating progression, not forward pass overestimate
                        if rating_before_smoothed:
                            smooth_mu = rating_before_smoothed.mu
                            smooth_sigma = rating_before_smoothed.sigma
                        else:
                            smooth_mu = self.mu
                            smooth_sigma = self.sigma
                        
                        # Get Filtered Entering Rating (from Forward Pass) for FSI calculation
                        filt_mu, filt_sigma = filtered_entering_ratings.get((tournament.id, player_id), (self.mu, self.sigma))
                        
                        mus_after.append(rating_after.mu)
                        mus_before.append(filt_mu)  # Still use forward pass for FSI
                        
                        smoothed_before_ratings[player_id] = (smooth_mu, smooth_sigma)
                        
                        # Create RatingChange record
                        # before_mu/sigma = Smoothed rating from previous tournament
                        # after_mu/sigma = Smoothed rating after this tournament
                        rc = RatingChange(
                            tournament_id=tournament.id,
                            player_id=player_id,
                            place=results[p_idx].place,
                            before_mu=smooth_mu,  # CHANGED: Use smoothed, not forward pass
                            before_sigma=smooth_sigma,  # CHANGED: Use smoothed, not forward pass
                            after_mu=rating_after.mu,
                            after_sigma=rating_after.sigma,
                            mu_change=rating_after.mu - smooth_mu,  # CHANGED: Smoothed change
                            sigma_change=rating_after.sigma - smooth_sigma,
                            conservative_rating_before=smooth_mu - 3 * smooth_sigma,
                            conservative_rating_after=rating_after.mu - 3 * rating_after.sigma
                        )
                        all_rating_changes.append(rc)
                        
                        # Update final rating tracker
                        player_final_ratings[player_id] = rating_after

                # Update tournament averages (still use forward pass for FSI)
                if mus_after:
                    tournament.avg_rating_after = sum(mus_after) / len(mus_after)
                    tournament.avg_rating_before = sum(mus_before) / len(mus_before)
                
                if progress_callback:
                    progress_callback(t_idx, len(tournament_map), f"Saving: {tournament.event_name}")

            # Bulk save rating changes
            session.bulk_save_objects(all_rating_changes)
            
            # Update Players table with final ratings
            for player_id, rating in player_final_ratings.items():
                player = player_map.get(player_id)
                if player:
                    player.current_rating_mu = rating.mu
                    player.current_rating_sigma = rating.sigma
                    player.tournaments_played = len(lc.get(str(player_id), []))
                    player.updated_at = datetime.utcnow()
            
            session.commit()
            return {'status': 'success', 'message': 'TTT Recalculation Complete'}
            
        except Exception as e:
            session.rollback()
            import traceback
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}
        finally:
            session.close()


    def get_rankings(self):
        return self.db.get_players_dataframe()

    def get_player_history(self, player_name: str) -> List[Dict]:
        player = self.db.get_player_by_name(player_name)
        if not player:
            return []
        
        changes = self.db.get_player_rating_history(player.id)
        history = []
        
        for change in changes:
            tournament = self.db.get_tournament_details(change.tournament_id)
            history.append({
                'tournament_date': tournament.tournament_date if tournament else None,
                'tournament': tournament.event_name if tournament else 'Unknown',
                'season': tournament.season if tournament else 'Unknown',
                'tier': tournament.tier if tournament else 'Unknown',
                'place': change.place,
                'before_mu': change.before_mu,
                'after_mu': change.after_mu,
                'mu': change.after_mu,  # Keep for backward compatibility
                'before_sigma': change.before_sigma,
                'sigma': change.after_sigma,
                'after_sigma': change.after_sigma,
                'conservative_rating_before': change.conservative_rating_before,
                'conservative_rating': change.conservative_rating_after,
                'mu_change': change.mu_change,
                'sigma_change': change.sigma_change
            })
        
        return history

    def get_tournament_strength(self) -> pd.DataFrame:
        return self.db.get_tournaments_dataframe()

    def get_detailed_logs(self) -> List[Dict]:
        """
        Get detailed logs/summary of processed tournaments.
        Returns a list of dicts with keys: season, tournament, tier, num_players, rating_changes.
        """
        session = self.db.get_session()
        try:
            # Step 1: Fetch all tournaments
            tournaments = session.query(Tournament).order_by(
                Tournament.tournament_date.desc()
            ).all()
            
            # Step 2: Fetch all rating changes joined with Player
            # Order by tournament and place
            changes = session.query(RatingChange, Player.name).join(
                Player, RatingChange.player_id == Player.id
            ).all()
            
            # Step 3: Group changes by tournament_id
            changes_by_tournament = {}
            for rc, player_name in changes:
                if rc.tournament_id not in changes_by_tournament:
                    changes_by_tournament[rc.tournament_id] = {}
                
                changes_by_tournament[rc.tournament_id][player_name] = {
                    'place': rc.place,
                    'before_mu': rc.before_mu,
                    'after_mu': rc.after_mu,
                    'mu_change': rc.mu_change,
                    'before_sigma': rc.before_sigma,
                    'after_sigma': rc.after_sigma,
                    'sigma_change': rc.sigma_change,
                    'conservative_rating_before': rc.conservative_rating_before,
                    'conservative_rating_after': rc.conservative_rating_after
                }
            
            # Step 4: Construct logs
            logs = []
            for t in tournaments:
                tournament_changes = changes_by_tournament.get(t.id, {})
                num_players = len(tournament_changes)
                
                logs.append({
                    'season': t.season,
                    'tournament': t.event_name,
                    'tier': t.tier,
                    'num_players': num_players,
                    'date': t.tournament_date,
                    'rating_changes': tournament_changes
                })
            return logs
        except Exception as e:
            print(f"Error getting detailed logs: {e}")
            import traceback
            traceback.print_exc()
            return []
        finally:
            session.close()

