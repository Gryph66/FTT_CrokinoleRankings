# Mock engine class to provide player history from JSON
class MockEngine:
    def __init__(self):
        self.players_df = load_json_data('players.json')
        self.event_points_df = load_json_data('event_points.json')
        self.tournaments_df = load_json_data('tournaments.json')
    
    def get_player_history(self, player_name):
        """Get player tournament history from event points data."""
        # Filter event points for this player
        player_events = self.event_points_df[self.event_points_df['player'] == player_name].copy()
        
        if len(player_events) == 0:
            return []
        
        # Merge with tournament data to get dates and names
        history = []
        for _, event in player_events.iterrows():
            # Find tournament info
            tournament = self.tournaments_df[self.tournaments_df['id'] == event['tournament_id']]
            if len(tournament) > 0:
                t = tournament.iloc[0]
                history.append({
                    'tournament': t['event_name'],
                    'season': t['season'],
                    'tournament_date': t['tournament_date'],
                    'place': event['place'],
                    'conservative_rating': event['display_rating'],  # Use display rating as proxy
                    'conservative_rating_before': event['pre_mu'] - 3 * event['pre_sigma'],
                    'after_mu': event['post_mu'],
                    'after_sigma': event['post_sigma']
                })
        
        # Sort by date
        history.sort(key=lambda x: x['tournament_date'])
        return history
    
    def get_tournament_strength(self):
        """Return tournaments dataframe."""
        return self.tournaments_df.copy()
