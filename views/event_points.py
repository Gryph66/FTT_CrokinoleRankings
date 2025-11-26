"""Event Points Breakdown Page - Shows detailed points calculation for tournaments."""

import streamlit as st
import pandas as pd


def render():
    """Render the Event Points Breakdown page."""
    st.title("📊 Event Points Breakdown")
    
    # Import cached functions from app.py
    from app import (
        get_cached_tournaments_with_fsi,
        get_cached_event_points,
        get_cached_team_info,
        get_cached_tournament_groups,
        show_cache_freshness
    )
    
    # Get cache key from session state
    cache_key = st.session_state.get('data_cache_key', 0)
    
    st.info("""
    **Detailed points breakdown for each tournament**
    
    Shows FSI (Field Strength Index), base points, overperformance bonus, and total points for each player.
    """)
    
    # Show cache freshness
    show_cache_freshness()
    
    # Get tournament groups for filter
    groups_df = get_cached_tournament_groups(cache_key)
    tournament_groups = ['All'] + groups_df['tournament_group'].tolist() if len(groups_df) > 0 else ['All']
    
    # Tournament group filter
    selected_group = st.selectbox("Tournament Group", tournament_groups, index=0, key="event_points_group")
    group_filter = None if selected_group == 'All' else selected_group
    
    # Get available tournaments with FSI data (cached)
    tournaments_df = get_cached_tournaments_with_fsi(cache_key, tournament_group=group_filter)
    
    if len(tournaments_df) == 0:
        st.warning("⚠️ No tournament points data available. Please run recalculation from Data Management.")
        return
    
    # Tournament selector
    tournament_options = []
    for idx, row in tournaments_df.iterrows():
        format_str = str(row['tournament_format']).upper() if pd.notna(row['tournament_format']) else 'SINGLES'
        tournament_options.append(
            f"{row['event_name']} (Season {row['season']}) - {format_str} - FSI: {row['fsi']:.2f}"
        )
    tournament_ids = tournaments_df['id'].tolist()
    
    selected_idx = st.selectbox("Select Tournament", range(len(tournament_options)), 
                                format_func=lambda x: tournament_options[x])
    
    tournament_id = tournament_ids[selected_idx]
    tournament_info = tournaments_df.iloc[selected_idx]
    
    # Get cached event points for selected tournament
    event_points_df = get_cached_event_points(cache_key, tournament_id=tournament_id)
    
    if len(event_points_df) == 0:
        st.warning(f"⚠️ No points data available for this tournament")
        return
    
    # Display tournament info
    is_doubles = tournament_info.get('tournament_format') == 'doubles'
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Tournament", tournament_info['event_name'])
    with col2:
        st.metric("Season", tournament_info['season'])
    with col3:
        format_label = "🎾 DOUBLES" if is_doubles else "🎯 SINGLES"
        st.metric("Format", format_label)
    with col4:
        st.metric("Field Strength (FSI)", f"{tournament_info['fsi']:.2f}")
    
    st.divider()
    
    # Display points breakdown
    if is_doubles:
        st.subheader("Points Breakdown by Team")
        
        # For doubles, fetch team information (cached)
        team_info_df = get_cached_team_info(cache_key, tournament_id)
        
        # Merge team info with event points using player_id for safe join
        display_df = event_points_df.merge(
            team_info_df, 
            on='player_id',
            how='left'
        )
        
        # Add team column
        display_df['Team'] = display_df['team_key'].fillna(display_df['player'])
        
        # Format numeric columns
        numeric_cols = ['fsi', 'raw_points', 'base_points', 'bonus_points', 'total_points']
        for col in numeric_cols:
            if col in display_df.columns:
                display_df[col] = display_df[col].round(2)
        
        # Select and rename columns for display
        display_df = display_df.rename(columns={
            'player': 'Player',
            'place': 'Place',
            'field_size': 'Teams',
            'fsi': 'FSI',
            'raw_points': 'Raw Points',
            'base_points': 'Base Points',
            'expected_rank': 'Expected Rank',
            'overperformance': 'PVE',
            'bonus_points': 'Bonus',
            'total_points': 'Total Points'
        })
        
        # Reorder columns to show Team first
        columns_order = ['Team', 'Player', 'Place', 'Teams', 'FSI', 'Raw Points', 
                        'Base Points', 'Expected Rank', 'PVE', 'Bonus', 'Total Points']
        display_df = display_df[[col for col in columns_order if col in display_df.columns]]
    else:
        st.subheader("Points Breakdown by Player")
        
        # Format the dataframe for display
        display_df = event_points_df.copy()
        numeric_cols = ['fsi', 'raw_points', 'base_points', 'bonus_points', 'total_points']
        for col in numeric_cols:
            if col in display_df.columns:
                display_df[col] = display_df[col].round(2)
        
        # Rename columns for display
        display_df = display_df.rename(columns={
            'player': 'Player',
            'place': 'Place',
            'field_size': 'Field Size',
            'fsi': 'FSI',
            'raw_points': 'Raw Points',
            'base_points': 'Base Points',
            'expected_rank': 'Expected Rank',
            'overperformance': 'PVE',
            'bonus_points': 'Bonus',
            'total_points': 'Total Points'
        })
    
    # Color-code based on overperformance
    def highlight_performance(row):
        colors = []
        for col in display_df.columns:
            if col == 'PVE':
                if row[col] > 0:
                    colors.append('background-color: lightgreen')
                elif row[col] < 0:
                    colors.append('background-color: lightcoral')
                else:
                    colors.append('')
            else:
                colors.append('')
        return colors
    
    styled_df = display_df.style.apply(highlight_performance, axis=1)
    
    st.dataframe(styled_df, width="stretch", hide_index=True)
    
    # Explanation
    st.divider()
    if is_doubles:
        st.markdown("""
        **Column Explanations (Doubles):**
        - **Team**: Both players' names (alphabetically sorted)
        - **Player**: Individual player name
        - **Teams**: Number of competing teams (field size)
        - **FSI**: Field Strength Index (avg of top 8 team ratings / 25.0)
        - **Raw Points**: Base points from team placement before FSI scaling
        - **Base Points**: Raw points × FSI
        - **Expected Rank**: Predicted team finish based on average pre-event ratings
        - **PVE** (Place vs Expected): Positive = beat expectations (green), Negative = underperformed (red)
        - **Bonus**: FSI × bonus_scale × PVE (currently disabled with bonus_scale=0)
        - **Total Points**: Base Points + Bonus (both teammates receive identical points)
        
        _Note: Doubles tournaments do NOT affect individual TrueSkill ratings, only Season Points._
        """)
    else:
        st.markdown("""
        **Column Explanations:**
        - **FSI**: Field Strength Index (avg of top 20 pre-event ratings / 25.0)
        - **Raw Points**: Base points from placement before FSI scaling
        - **Base Points**: Raw points × FSI
        - **Expected Rank**: Predicted finish based on pre-event TrueSkill rating
        - **PVE** (Place vs Expected): Positive = beat expectations (green), Negative = underperformed (red)
        - **Bonus**: FSI × bonus_scale × PVE (currently disabled with bonus_scale=0)
        - **Total Points**: Base Points + Bonus
        """)
