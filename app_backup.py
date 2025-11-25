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
if 'data_cache_key' not in st.session_state:
    st.session_state.data_cache_key = 0

# Main app
st.title("🎯 National Crokinole Association Ranking System")
st.markdown("*TrueSkill Through Time player rankings and tournament analysis*")

with st.sidebar:
    st.header("Navigation")
    
    # Add Refresh Button
    if st.button("🔄 Refresh Data", help="Reload latest data"):
        st.session_state.data_cache_key += 1
        st.rerun()
        
    page = st.radio(
        "Go to",
        [
            "📊 Player Rankings",
            "🏆 Tournament Analysis", 
            "🎲 Tier Prediction",
            "---",
            "🌟 Season Standings",
            "📊 Event Points",
            "🎯 Player Top 5",
            "📈 FSI Trends"
        ],
        label_visibility="collapsed")
    
    st.divider()
    
    st.subheader("System Status")
    rankings_df = get_rankings()
    tournaments_df = get_tournaments()
    
    if len(rankings_df) > 0:
        st.success("✅ Data Loaded")
        st.metric("Total Players", len(rankings_df))
        st.metric("Tournaments Processed", len(tournaments_df))
    else:
        st.info("ℹ️ No Data Available")

# Route to pages
if page == "📊 Player Rankings":
    # Import and use the exact admin implementation
    exec(open('/Users/shagarty/Downloads/CrokinoleRanker-3/app.py').read().split('def show_player_rankings():')[1].split('def show_tournament_analysis():')[0])
    
elif page == "🏆 Tournament Analysis":
    from views import fsi_trends
    # We'll use the admin's show_tournament_analysis
    exec(open('/Users/shagarty/Downloads/CrokinoleRanker-3/app.py').read().split('def show_tournament_analysis():')[1].split('def show_tier_prediction():')[0])
    
elif page == "🎲 Tier Prediction":
    st.title("🎲 Tier Prediction")
    st.info("Tier prediction functionality - Coming soon in public view")
    
elif page == "🌟 Season Standings":
    from views import season_standings
    season_standings.render()
    
elif page == "📊 Event Points":
    from views import event_points
    event_points.render()
    
elif page == "🎯 Player Top 5":
    from views import player_top_tournaments
    player_top_tournaments.render()
    
elif page == "📈 FSI Trends":
    from views import fsi_trends
    fsi_trends.render()
    
elif page == "---":
    st.info("Please select a page from the sidebar.")
