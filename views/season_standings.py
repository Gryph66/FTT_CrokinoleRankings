"""Season Standings Page - Displays season leaderboards based on Field-Weighted Points."""

import streamlit as st
import pandas as pd


def render():
    """Render the Season Standings page."""
    st.title("🏆 Season Standings")
    
    # Import cached functions from app.py
    from app import get_cached_season_standings, get_cached_tournament_groups, show_cache_freshness
    from db_service import normalize_season
    
    # Get cache key from session state
    cache_key = st.session_state.get('data_cache_key', 0)
    
    st.info("""
    **Season leaderboard rankings based on Field-Weighted Points (FWP)**
    
    Points are calculated using tournament Field Strength Index (FSI) and placement.  
    Season rankings use each player's **best 5 tournaments** from that season.
    """)
    
    # Show cache freshness
    show_cache_freshness()
    
    # Get all standings to extract available seasons (cached via get_cached_season_standings)
    all_standings_df = get_cached_season_standings(cache_key)
    
    if len(all_standings_df) == 0:
        st.warning("⚠️ No season standings available. Please run recalculation from Data Management to generate points.")
        st.info("💡 Upload tournament data and click 'Recalculate All Rankings' to compute season points.")
        return
    
    # Extract and normalize seasons
    seasons_raw = all_standings_df['season'].unique().tolist()
    seasons_normalized = list(set(normalize_season(s) for s in seasons_raw))
    # Sort numerically (convert to int) so Season 16 comes before Season 9
    seasons = sorted(seasons_normalized, key=lambda x: int(x), reverse=True)
    
    # Get tournament groups for filter
    groups_df = get_cached_tournament_groups(cache_key)
    tournament_groups = ['All'] + groups_df['tournament_group'].tolist() if len(groups_df) > 0 else ['All']
    
    # Filters row
    col1, col2 = st.columns(2)
    with col1:
        selected_season = st.selectbox("Select Season", seasons, index=0)
    with col2:
        selected_group = st.selectbox("Tournament Group", tournament_groups, index=0)
    
    # Get cached standings for selected season and group
    group_filter = None if selected_group == 'All' else selected_group
    standings_df = get_cached_season_standings(cache_key, season=selected_season, tournament_group=group_filter)
    
    if len(standings_df) == 0:
        st.warning(f"⚠️ No standings data available for Season {selected_season}")
        return
    
    # Display leaderboard
    st.subheader(f"Season {selected_season} Leaderboard")
    
    # Format the dataframe for display
    display_df = standings_df.copy()
    display_df['total_points'] = display_df['total_points'].round(2)
    display_df['final_display_rating'] = display_df['final_display_rating'].round(2)
    
    # Rename columns for display
    display_df = display_df.rename(columns={
        'rank': 'Rank',
        'player': 'Player',
        'total_points': 'Total Points',
        'events_counted': 'Events',
        'final_display_rating': 'TrueSkill Rating',
        'pseudo_elo': 'Pseudo-ELO'
    })
    
    # Color-code top 3
    def highlight_top3(row):
        if row['Rank'] == 1:
            return ['background-color: gold'] * len(row)
        elif row['Rank'] == 2:
            return ['background-color: silver'] * len(row)
        elif row['Rank'] == 3:
            return ['background-color: #CD7F32'] * len(row)  # bronze
        else:
            return [''] * len(row)
    
    styled_df = display_df.style.apply(highlight_top3, axis=1)
    
    st.dataframe(
        styled_df, 
        width="stretch", 
        height=750,
        hide_index=True,
        column_config={
            "Total Points": st.column_config.NumberColumn("Total Points", format="%.2f"),
            "TrueSkill Rating": st.column_config.NumberColumn("TrueSkill Rating", format="%.2f"),
            "Pseudo-ELO": st.column_config.NumberColumn("Pseudo-ELO", format="%d")
        }
    )
    
    # Summary stats
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Players", len(display_df))
    with col2:
        st.metric("Average Points", f"{display_df['Total Points'].mean():.2f}")
    with col3:
        st.metric("Winner Points", f"{display_df.iloc[0]['Total Points']:.2f}")
    
    # Top 3 callout
    st.divider()
    st.subheader("🥇 Top 3 Players")
    top3 = display_df.head(3)
    
    for idx, row in top3.iterrows():
        medal = ["🥇", "🥈", "🥉"][idx]
        st.markdown(f"**{medal} {row['Player']}** - {row['Total Points']:.2f} points ({row['Events']} events)")
