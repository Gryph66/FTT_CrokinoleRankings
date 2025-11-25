import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
import os

st.set_page_config(page_title="NCA Ranking System", layout="wide", initial_sidebar_state="expanded")

# Data loading functions
@st.cache_data
def load_json_data(filename):
    """Load data from JSON file."""
    filepath = os.path.join('data', filename)
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            data = json.load(f)
        return pd.DataFrame(data)
    return pd.DataFrame()

@st.cache_data
def get_rankings():
    """Load rankings data."""
    return load_json_data('rankings.json')

@st.cache_data
def get_tournaments():
    """Load tournaments data."""
    return load_json_data('tournaments.json')

@st.cache_data
def get_season_standings():
    """Load season standings data."""
    return load_json_data('season_standings.json')

@st.cache_data
def get_event_points():
    """Load event points data."""
    return load_json_data('event_points.json')

@st.cache_data
def get_fsi_trends():
    """Load FSI trends data."""
    return load_json_data('fsi_trends.json')

@st.cache_data
def get_players():
    """Load players data."""
    return load_json_data('players.json')

# Initialize session state
if 'page' not in st.session_state:
    st.session_state.page = 'Player Rankings'

# Sidebar
with st.sidebar:
    st.title("📊 Data Crokinole")
    st.markdown("**TrueSkill Through Time Rankings**")
    
    st.divider()
    
    # Navigation
    st.subheader("Navigation")
    
    pages = [
        "📊 Player Rankings",
        "🏆 Tournament Analysis",
        "🔮 Tier Prediction",
        "⭐ Season Standings",
        "📈 Event Points",
        "🎯 Player Top 5",
        "📉 FSI Trends"
    ]
    
    for page in pages:
        if st.button(page, use_container_width=True):
            st.session_state.page = page.split(' ', 1)[1]  # Remove emoji
    
    st.divider()
    
    # Stats
    rankings_df = get_rankings()
    tournaments_df = get_tournaments()
    
    st.metric("Total Players", len(rankings_df))
    st.metric("Total Tournaments", len(tournaments_df))
    
    st.divider()
    st.caption("🔒 Read-Only Public View")
    st.caption("Data updated: See admin site")

# Main content area
current_page = st.session_state.page

if current_page == 'Player Rankings':
    st.title("📊 Player Rankings")
    
    st.info("""
    **TrueSkill Through Time (TTT) Rankings**
    
    Rankings are based on a Bayesian skill rating system that accounts for opponent strength and skill evolution over time.
    """)
    
    rankings_df = get_rankings()
    
    if len(rankings_df) == 0:
        st.warning("No rankings data available.")
    else:
        # Tournament group filter
        tournaments_df = get_tournaments()
        tournament_groups = ['All'] + sorted(tournaments_df['tournament_group'].dropna().unique().tolist())
        
        selected_group = st.selectbox("Tournament Group Filter", tournament_groups, index=0)
        
        # Filter rankings by group if needed
        if selected_group != 'All':
            # Get player IDs who participated in this group
            group_tournaments = tournaments_df[tournaments_df['tournament_group'] == selected_group]['id'].tolist()
            event_points_df = get_event_points()
            player_ids_in_group = event_points_df[event_points_df['tournament_id'].isin(group_tournaments)]['player_id'].unique()
            
            # Filter rankings
            # We need to map player names to IDs - for now just show all
            # In a full implementation, we'd need player_id in rankings.json
            display_df = rankings_df.copy()
        else:
            display_df = rankings_df.copy()
        
        # Display rankings table
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            height=600,
            column_config={
                "rank": st.column_config.NumberColumn("Rank", format="%d"),
                "player": st.column_config.TextColumn("Player"),
                "rating": st.column_config.NumberColumn("Rating (μ)", format="%.2f"),
                "uncertainty": st.column_config.NumberColumn("Uncertainty (σ)", format="%.2f"),
                "conservative_rating": st.column_config.NumberColumn("Conservative Rating", format="%.2f"),
                "tournaments_played": st.column_config.NumberColumn("Tournaments", format="%d")
            }
        )
        
        # Stats
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Players", len(display_df))
        with col2:
            st.metric("Avg Rating", f"{display_df['conservative_rating'].mean():.2f}")
        with col3:
            st.metric("Top Player", display_df.iloc[0]['player'] if len(display_df) > 0 else "N/A")

elif current_page == 'Tournament Analysis':
    st.title("🏆 Tournament Analysis")
    
    st.info("""
    **Tournament strength metrics and Field Strength Index (FSI)**
    
    FSI measures tournament difficulty based on participant ratings.
    """)
    
    tournaments_df = get_tournaments()
    
    if len(tournaments_df) == 0:
        st.warning("No tournament data available.")
    else:
        # Filters
        tournament_groups = ['All'] + sorted(tournaments_df['tournament_group'].dropna().unique().tolist())
        tournament_types = ['All', 'Singles', 'Doubles']
        
        col1, col2 = st.columns(2)
        with col1:
            selected_group = st.selectbox("Tournament Group Filter", tournament_groups, index=0, key="ta_group")
        with col2:
            selected_type = st.selectbox("Tournament Type Filter", tournament_types, index=0, key="ta_type")
        
        # Apply filters
        display_df = tournaments_df.copy()
        if selected_group != 'All':
            display_df = display_df[display_df['tournament_group'] == selected_group]
        if selected_type != 'All':
            type_filter = 'singles' if selected_type == 'Singles' else 'doubles'
            display_df = display_df[display_df['tournament_format'] == type_filter]
        
        if len(display_df) == 0:
            st.warning("No tournaments match the selected filters.")
        else:
            # Calculate metrics
            display_df['fsi_raw'] = display_df['avg_top_mu'] / 6.0
            display_df['fsi_all'] = display_df['avg_rating_before'] / 6.0
            
            # Stats header
            col1, col2, col3, col4, col5, col6 = st.columns(6)
            with col1:
                st.metric("Total Tournaments", len(display_df))
            with col2:
                st.metric("Avg Field Size", f"{display_df['num_players'].mean():.1f}")
            with col3:
                st.metric("Avg Rating (all)", f"{display_df['avg_rating_before'].mean():.2f}")
            with col4:
                st.metric("Avg Rating (Top 20)", f"{display_df['avg_top_mu'].mean():.2f}")
            with col5:
                st.metric("FSI Final (Avg)", f"{display_df['fsi'].mean():.3f}")
            with col6:
                st.metric("Scaling Factor", "6.0")
            
            st.divider()
            
            # Table
            st.dataframe(
                display_df[[
                    'event_name', 'season', 'tournament_date', 'tournament_group', 'tournament_format',
                    'num_players', 'avg_rating_before', 'avg_top_mu', 'fsi'
                ]],
                use_container_width=True,
                hide_index=True,
                height=600,
                column_config={
                    "event_name": st.column_config.TextColumn("Tournament"),
                    "season": st.column_config.TextColumn("Season"),
                    "tournament_date": st.column_config.TextColumn("Date"),
                    "tournament_group": st.column_config.TextColumn("Tour"),
                    "tournament_format": st.column_config.TextColumn("Type"),
                    "num_players": st.column_config.NumberColumn("Field Size", format="%d"),
                    "avg_rating_before": st.column_config.NumberColumn("Avg Rating (all)", format="%.2f"),
                    "avg_top_mu": st.column_config.NumberColumn("Avg Rating (Top 20)", format="%.2f"),
                    "fsi": st.column_config.NumberColumn("FSI Final", format="%.3f")
                }
            )

elif current_page == 'Season Standings':
    st.title("⭐ Season Standings")
    
    st.info("""
    **Season leaderboard rankings based on Field-Weighted Points (FWP)**
    
    Points are calculated using tournament Field Strength Index (FSI) and placement.  
    Season rankings use each player's **best 5 tournaments** from that season.
    """)
    
    standings_df = get_season_standings()
    
    if len(standings_df) == 0:
        st.warning("No season standings data available.")
    else:
        # Get available seasons
        seasons = sorted(standings_df['season'].unique().tolist(), key=lambda x: int(x), reverse=True)
        
        # Filters
        col1, col2 = st.columns(2)
        with col1:
            selected_season = st.selectbox("Select Season", seasons, index=0)
        with col2:
            # Tournament group filter would require more complex data structure
            st.selectbox("Tournament Group", ['All'], index=0, disabled=True)
        
        # Filter by season
        display_df = standings_df[standings_df['season'] == selected_season].copy()
        
        # Display leaderboard
        st.subheader(f"Season {selected_season} Leaderboard")
        
        # Format columns
        display_df = display_df.rename(columns={
            'rank': 'Rank',
            'player': 'Player',
            'total_points': 'Total Points',
            'events_counted': 'Events',
            'final_display_rating': 'TrueSkill Rating'
        })
        
        st.dataframe(
            display_df[['Rank', 'Player', 'Total Points', 'Events', 'TrueSkill Rating']],
            use_container_width=True,
            hide_index=True,
            height=600
        )
        
        # Summary stats
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Players", len(display_df))
        with col2:
            st.metric("Average Points", f"{display_df['Total Points'].mean():.2f}")
        with col3:
            st.metric("Winner Points", f"{display_df.iloc[0]['Total Points']:.2f}")

elif current_page == 'Event Points':
    st.title("📈 Event Points")
    
    st.info("""
    **Detailed points breakdown for each tournament**
    
    Shows FSI (Field Strength Index), base points, overperformance bonus, and total points for each player.
    """)
    
    tournaments_df = get_tournaments()
    event_points_df = get_event_points()
    
    if len(tournaments_df) == 0 or len(event_points_df) == 0:
        st.warning("No event points data available.")
    else:
        # Tournament selector
        tournament_options = []
        for idx, row in tournaments_df.iterrows():
            format_str = str(row['tournament_format']).upper() if pd.notna(row['tournament_format']) else 'SINGLES'
            tournament_options.append(
                f"{row['event_name']} (Season {row['season']}) - {format_str} - FSI: {row['fsi']:.2f}"
            )
        
        selected_idx = st.selectbox("Select Tournament", range(len(tournament_options)), 
                                    format_func=lambda x: tournament_options[x])
        
        tournament_id = tournaments_df.iloc[selected_idx]['id']
        tournament_info = tournaments_df.iloc[selected_idx]
        
        # Filter event points for this tournament
        display_df = event_points_df[event_points_df['tournament_id'] == tournament_id].copy()
        
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
        
        # Display points table
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
        
        st.dataframe(
            display_df[['Player', 'Place', 'Field Size', 'FSI', 'Raw Points', 
                       'Base Points', 'Expected Rank', 'PVE', 'Bonus', 'Total Points']],
            use_container_width=True,
            hide_index=True,
            height=600
        )

elif current_page == 'FSI Trends':
    st.title("📉 FSI Trends")
    
    st.info("""
    **Field Strength Index trends over time**
    
    Track how tournament difficulty has evolved across seasons.
    """)
    
    fsi_df = get_fsi_trends()
    
    if len(fsi_df) == 0:
        st.warning("No FSI trends data available.")
    else:
        # Convert date to datetime
        fsi_df['tournament_date'] = pd.to_datetime(fsi_df['tournament_date'])
        
        # Plot FSI over time
        fig = px.line(fsi_df, x='tournament_date', y='fsi', 
                     hover_data=['event_name', 'season'],
                     title='FSI Over Time',
                     labels={'tournament_date': 'Date', 'fsi': 'FSI'})
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Summary stats
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Average FSI", f"{fsi_df['fsi'].mean():.3f}")
        with col2:
            st.metric("Max FSI", f"{fsi_df['fsi'].max():.3f}")
        with col3:
            st.metric("Min FSI", f"{fsi_df['fsi'].min():.3f}")

elif current_page == 'Tier Prediction':
    st.title("🔮 Tier Prediction")
    st.info("Tier prediction functionality - Coming soon in public view")
    
elif current_page == 'Player Top 5':
    st.title("🎯 Player Top 5")
    st.info("Player top 5 tournaments - Coming soon in public view")
