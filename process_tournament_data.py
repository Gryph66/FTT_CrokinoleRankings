import pandas as pd
import streamlit as st


def process_tournament_data(df: pd.DataFrame, engine, progress_callback=None):
    """
    OPTIMIZED: Bulk upload tournaments WITHOUT calculating ratings.
    Ratings will be calculated via recalculate_all_ratings() after upload.
    """
    from datetime import datetime
    
    # Group tournaments
    tournaments = df.groupby(['season', 'event', 'tier'])
    
    # Convert to list and normalize data
    tournaments_data = []
    total_tournaments = len(tournaments)
    
    # Handle empty dataset
    if total_tournaments == 0:
        if progress_callback:
            progress_callback(0, 0, "No tournaments found")
        return 0, 0
    
    for idx, ((season, event, tier), group) in enumerate(tournaments, 1):
        first_row = group.iloc[0]
        
        # Extract tournament_date if available
        tournament_date = None
        if 'tournament_date' in first_row and pd.notna(first_row['tournament_date']) and first_row['tournament_date'] != '':
            try:
                tournament_date = pd.to_datetime(first_row['tournament_date'])
            except:
                pass
        
        # Extract sequence_order if available
        sequence_order = None
        if 'sequence_order' in first_row and pd.notna(first_row['sequence_order']) and first_row['sequence_order'] != '':
            try:
                sequence_order = int(first_row['sequence_order'])
            except:
                pass
        
        # Build players data from group
        players_data = []
        for _, row in group.iterrows():
            players_data.append((row['player'], int(row['place'])))
        
        # Add to tournaments payload
        tournaments_data.append({
            'season': season,
            'event_name': event,
            'tier': tier,
            'players_data': players_data,
            'tournament_date': tournament_date,
            'sequence_order': sequence_order
        })
        
        # Update progress if callback provided
        if progress_callback:
            progress_callback(idx, total_tournaments, f"{season} {event}")
    
    # Bulk upload all tournaments in one transaction
    # Check if st.session_state.db is available (when running from app)
    # Or if we need to use a direct db service (when running from script)
    
    if hasattr(st, 'session_state') and 'db' in st.session_state:
        db_service = st.session_state.db
    else:
        # Fallback for script usage
        from db_service import DatabaseService
        db_service = DatabaseService()

    result = db_service.bulk_upload_tournaments(tournaments_data)
    
    if result['status'] == 'success':
        return result['processed'], result['skipped']
    else:
        # If bulk upload failed, fall back to old method for debugging
        if hasattr(st, 'error'):
            st.error(f"⚠️ Bulk upload failed: {result.get('message', 'Unknown error')}")
        else:
            print(f"⚠️ Bulk upload failed: {result.get('message', 'Unknown error')}")
        return 0, 0
