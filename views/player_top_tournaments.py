"""Player Top Tournaments Page - Shows a player's best tournament performances."""

import streamlit as st
import pandas as pd


def render():
    """Render the Player Top Tournaments page."""
    st.title("🌟 Player Top Tournaments")
    
    # Import cached functions from app.py
    from app import (
        get_cached_players_with_points,
        get_cached_all_seasons,
        get_cached_player_tournament_events,
        show_cache_freshness
    )
    
    # Get cache key from session state
    cache_key = st.session_state.get('data_cache_key', 0)
    
    st.info("""
    **View any player's best tournament performances**
    
    Shows each player's top scoring tournaments with FSI, placement, and overperformance details.
    """)
    
    # Show cache freshness
    show_cache_freshness()
    
    # Get all players who have season points (cached)
    players_df = get_cached_players_with_points(cache_key)
    
    if len(players_df) == 0:
        st.warning("⚠️ No player data available. Please run recalculation from Data Management.")
        return
    
    # Player selector
    player_names = players_df['name'].tolist()
    selected_player = st.selectbox("Select Player", player_names)
    
    # Season filter (cached)
    seasons_df = get_cached_all_seasons(cache_key)
    seasons = ["All Seasons"] + seasons_df['season'].tolist()
    selected_season = st.selectbox("Filter by Season", seasons)
    
    # Get player's event points (cached with parameterized query)
    if selected_season == "All Seasons":
        events_df = get_cached_player_tournament_events(cache_key, selected_player)
    else:
        events_df = get_cached_player_tournament_events(cache_key, selected_player, selected_season)
    
    if len(events_df) == 0:
        st.warning(f"⚠️ No tournament data for {selected_player}")
        return
    
    # Display summary stats
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Events", len(events_df))
    with col2:
        st.metric("Avg Points", f"{events_df['total_points'].mean():.2f}")
    with col3:
        st.metric("Best Result", f"{events_df['total_points'].max():.2f}")
    with col4:
        avg_place = events_df['place'].mean()
        st.metric("Avg Finish", f"{avg_place:.1f}")
    
    st.divider()
    
    # Display top tournaments
    st.subheader(f"Top Tournaments - {selected_player}")
    
    # Format the dataframe
    display_df = events_df.copy()
    display_df['total_points'] = display_df['total_points'].round(2)
    display_df['fsi'] = display_df['fsi'].round(2)
    display_df['tournament_date'] = pd.to_datetime(display_df['tournament_date']).dt.strftime('%Y-%m-%d')
    
    # Add rank column
    display_df.insert(0, 'Rank', range(1, len(display_df) + 1))
    
    # Rename columns
    display_df = display_df.rename(columns={
        'Rank': '#',
        'event_name': 'Tournament',
        'season': 'Season',
        'tournament_date': 'Date',
        'place': 'Place',
        'field_size': 'Field',
        'fsi': 'FSI',
        'expected_rank': 'Exp. Rank',
        'overperformance': 'PVE',
        'total_points': 'Points'
    })
    
    # Highlight top 5 (used for season scoring)
    def highlight_top5(row):
        if row['#'] <= 5:
            return ['background-color: lightyellow'] * len(row)
        else:
            return [''] * len(row)
    
    styled_df = display_df.style.apply(highlight_top5, axis=1)
    
    st.dataframe(
        styled_df, 
        width="stretch", 
        height=750,
        hide_index=True,
        column_config={
            "FSI": st.column_config.NumberColumn("FSI", format="%.2f"),
            "PVE": st.column_config.NumberColumn("PVE", format="%.2f"),
            "Points": st.column_config.NumberColumn("Points", format="%.2f")
        }
    )
    
    # Show best 5 callout
    st.divider()
    st.info(f"""
    **Season Scoring:** Only the **top 5 tournaments** (highlighted) count toward season standings.  
    **{selected_player}'s Season Points:** {display_df.head(5)['Points'].sum():.2f}
    """)
    
    # Individual tournament details
    st.divider()
    st.subheader("Tournament Details")
    
    for idx, row in display_df.head(5).iterrows():
        with st.expander(f"🏆 {row['Tournament']} ({row['Season']}) - {row['Points']:.2f} pts"):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Finish", f"{row['Place']}/{row['Field']}")
                st.metric("Expected Finish", row['Exp. Rank'])
            with col2:
                st.metric("Field Strength (FSI)", f"{row['FSI']:.2f}")
                st.metric("Overperformance (PVE)", f"{row['PVE']:+.1f}")
            with col3:
                st.metric("Date", row['Date'])
                st.metric("Total Points", f"{row['Points']:.2f}")
