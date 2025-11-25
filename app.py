import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from ranking_engine_ttt import TTTRankingEngine
from points_engine_db import PointsEngineDB
from db_service import DatabaseService
from database import engine as db_engine
import io

st.set_page_config(page_title="NCA Ranking System", layout="wide", initial_sidebar_state="expanded")

@st.cache_data
def load_initial_data():
    """
    Auto-seeding disabled - use Data Management page to manually upload CSV files.
    This prevents loading outdated/incorrect data on startup.
    """
    return pd.DataFrame()

@st.cache_data
def get_cached_system_stats(_cache_key):
    """Cache sidebar system statistics using direct SQL queries."""
    player_count = pd.read_sql("SELECT COUNT(*) as count FROM players", db_engine).iloc[0]['count']
    tournament_count = pd.read_sql("SELECT COUNT(*) as count FROM tournaments", db_engine).iloc[0]['count']
    
    return {
        'player_count': int(player_count),
        'tournament_count': int(tournament_count),
        'has_data': player_count > 0
    }

def get_latest_db_update():
    """Get the latest update timestamp from the players table to use as cache key."""
    try:
        sql = "SELECT MAX(updated_at) as last_update FROM players"
        result = pd.read_sql(sql, db_engine)
        if not result.empty and result.iloc[0]['last_update']:
            return result.iloc[0]['last_update'].isoformat()
    except:
        pass
    return "0"

@st.cache_data
def get_cached_rankings(_cache_key, db_version, tournament_group=None):
    """
    Cache player rankings using direct SQL query.
    Updated for TTT migration.
    
    Args:
        _cache_key: Manual cache invalidation key
        db_version: Database version key (timestamp) to auto-invalidate on DB updates
        tournament_group: Optional tournament group filter (e.g., 'NCA', 'UK')
                         If provided, only shows players who participated in that group's singles tournaments
                         Ratings remain unchanged (calculated from all singles tournaments)
    """
    if tournament_group:
        # Filter to only players who participated in singles tournaments from the selected group
        sql = """
            SELECT DISTINCT
                p.name as player,
                p.current_rating_mu as rating,
                p.current_rating_sigma as uncertainty,
                (p.current_rating_mu - 3 * p.current_rating_sigma) as conservative_rating,
                p.tournaments_played
            FROM players p
            JOIN tournament_results tr ON p.id = tr.player_id
            JOIN tournaments t ON tr.tournament_id = t.id
            WHERE t.tournament_group = :group
              AND t.tournament_format = 'singles'
            ORDER BY conservative_rating DESC
        """
        rankings_df = pd.read_sql(sql, db_engine, params={'group': tournament_group})
    else:
        # Show all players
        sql = """
            SELECT 
                name as player,
                current_rating_mu as rating,
                current_rating_sigma as uncertainty,
                (current_rating_mu - 3 * current_rating_sigma) as conservative_rating,
                tournaments_played
            FROM players
            ORDER BY conservative_rating DESC
        """
        rankings_df = pd.read_sql(sql, db_engine)
    
    if len(rankings_df) == 0:
        return pd.DataFrame()
    
    # Round numerical columns
    rankings_df['rating'] = rankings_df['rating'].round(2)
    rankings_df['uncertainty'] = rankings_df['uncertainty'].round(2)
    rankings_df['conservative_rating'] = rankings_df['conservative_rating'].round(2)
    
    # Add rank column
    rankings_df.insert(0, 'rank', range(1, len(rankings_df) + 1))
    
    return rankings_df

@st.cache_data
def get_cached_tournaments(_cache_key):
    """Cache tournament list using direct SQL query."""
    sql = """
        SELECT 
            id, season, event_name, tier, num_players,
            avg_rating_before, avg_rating_after,
            to_char(tournament_date, 'YYYY-MM-DD') as tournament_date,
            sequence_order
        FROM tournaments
        ORDER BY 
            tournament_date ASC NULLS LAST,
            sequence_order ASC NULLS LAST,
            created_at ASC,
            id ASC
    """
    tournaments_df = pd.read_sql(sql, db_engine)
    
    return tournaments_df

@st.cache_data
def get_cached_season_standings(_cache_key, season=None, tournament_group=None):
    """Cache season standings with optional filters using parameterized queries."""
    params = {}
    where_clauses = []
    
    if season:
        where_clauses.append("t.season = :season")
        params['season'] = season
    
    if tournament_group:
        where_clauses.append("t.tournament_group = :tournament_group")
        params['tournament_group'] = tournament_group
    
    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    
    sql = f"""
        WITH ranked_events AS (
            SELECT 
                p.id as player_id,
                p.name as player,
                sep.season,
                sep.total_points,
                p.current_rating_mu,
                p.current_rating_sigma,
                ROW_NUMBER() OVER (PARTITION BY p.id, sep.season ORDER BY sep.total_points DESC) as event_rank
            FROM season_event_points sep
            JOIN tournaments t ON sep.tournament_id = t.id
            JOIN players p ON sep.player_id = p.id
            {where_sql}
        ),
        player_totals AS (
            SELECT 
                player_id,
                player,
                season,
                SUM(total_points) as total_points,
                COUNT(*) as events_counted,
                MAX(current_rating_mu - 3 * current_rating_sigma) as final_display_rating
            FROM ranked_events
            WHERE event_rank <= 5
            GROUP BY player_id, player, season
        )
        SELECT 
            ROW_NUMBER() OVER (PARTITION BY season ORDER BY total_points DESC) as rank,
            season,
            player,
            total_points,
            events_counted,
            final_display_rating
        FROM player_totals
        ORDER BY season DESC, rank ASC
    """
    
    df = pd.read_sql(sql, db_engine, params=params)
    return df if len(df) > 0 else pd.DataFrame()

@st.cache_data
def get_cached_event_points(_cache_key, tournament_id=None, season=None):
    """Cache event points using parameterized SQL queries."""
    if tournament_id:
        sql = """
            SELECT t.event_name, t.season, p.id as player_id, p.name as player, 
                   sep.place, sep.field_size,
                   sep.fsi, sep.raw_points, sep.base_points, sep.expected_rank,
                   sep.overperformance, sep.bonus_points, sep.total_points
            FROM season_event_points sep
            JOIN tournaments t ON sep.tournament_id = t.id
            JOIN players p ON sep.player_id = p.id
            WHERE sep.tournament_id = :tournament_id
            ORDER BY sep.total_points DESC
        """
        df = pd.read_sql(sql, db_engine, params={'tournament_id': tournament_id})
    elif season:
        sql = """
            SELECT t.event_name, t.season, p.id as player_id, p.name as player, 
                   sep.place, sep.field_size,
                   sep.fsi, sep.raw_points, sep.base_points, sep.expected_rank,
                   sep.overperformance, sep.bonus_points, sep.total_points
            FROM season_event_points sep
            JOIN tournaments t ON sep.tournament_id = t.id
            JOIN players p ON sep.player_id = p.id
            WHERE sep.season = :season
            ORDER BY sep.total_points DESC
        """
        df = pd.read_sql(sql, db_engine, params={'season': season})
    else:
        sql = """
            SELECT t.event_name, t.season, p.id as player_id, p.name as player, 
                   sep.place, sep.field_size,
                   sep.fsi, sep.raw_points, sep.base_points, sep.expected_rank,
                   sep.overperformance, sep.bonus_points, sep.total_points
            FROM season_event_points sep
            JOIN tournaments t ON sep.tournament_id = t.id
            JOIN players p ON sep.player_id = p.id
            ORDER BY sep.total_points DESC
        """
        df = pd.read_sql(sql, db_engine)
    return df if len(df) > 0 else pd.DataFrame()

@st.cache_data
def get_cached_tournament_fsi(_cache_key, season=None):
    """Cache tournament FSI data using parameterized SQL queries."""
    if season:
        sql = """
            SELECT t.id, t.event_name, t.season, t.tournament_date,
                   tf.fsi, tf.avg_top_mu
            FROM tournament_fsi tf
            JOIN tournaments t ON tf.tournament_id = t.id
            WHERE t.season = :season
            ORDER BY t.tournament_date ASC NULLS LAST,
                     t.sequence_order ASC NULLS LAST,
                     t.created_at ASC
        """
        df = pd.read_sql(sql, db_engine, params={'season': season})
    else:
        sql = """
            SELECT t.id, t.event_name, t.season, t.tournament_date,
                   tf.fsi, tf.avg_top_mu
            FROM tournament_fsi tf
            JOIN tournaments t ON tf.tournament_id = t.id
            ORDER BY t.tournament_date ASC NULLS LAST,
                     t.sequence_order ASC NULLS LAST,
                     t.created_at ASC
        """
        df = pd.read_sql(sql, db_engine)
    return df if len(df) > 0 else pd.DataFrame()

@st.cache_data
def get_cached_players_with_points(_cache_key):
    """Cache list of players who have season points."""
    sql = """
        SELECT DISTINCT p.id, p.name
        FROM players p
        JOIN season_event_points sep ON p.id = sep.player_id
        ORDER BY p.name
    """
    return pd.read_sql(sql, db_engine)

@st.cache_data
def get_cached_all_seasons(_cache_key):
    """Cache list of all distinct seasons."""
    sql = "SELECT DISTINCT season FROM tournaments ORDER BY season DESC"
    return pd.read_sql(sql, db_engine)

@st.cache_data
def get_cached_tournament_groups(_cache_key):
    """Cache list of all distinct tournament groups."""
    sql = "SELECT DISTINCT tournament_group FROM tournaments WHERE tournament_group IS NOT NULL ORDER BY tournament_group"
    return pd.read_sql(sql, db_engine)

@st.cache_data
def get_cached_player_tournament_events(_cache_key, player_name, season=None):
    """Cache a player's tournament events with parameterized queries."""
    if season:
        sql = """
            SELECT t.event_name, t.season, t.tournament_date, t.tournament_format,
                   sep.place, sep.field_size, sep.fsi,
                   sep.expected_rank, sep.overperformance,
                   sep.total_points
            FROM season_event_points sep
            JOIN tournaments t ON sep.tournament_id = t.id
            JOIN players p ON sep.player_id = p.id
            WHERE p.name = :player_name AND t.season = :season
            ORDER BY sep.total_points DESC
        """
        df = pd.read_sql(sql, db_engine, params={'player_name': player_name, 'season': season})
    else:
        sql = """
            SELECT t.event_name, t.season, t.tournament_date, t.tournament_format,
                   sep.place, sep.field_size, sep.fsi,
                   sep.expected_rank, sep.overperformance,
                   sep.total_points
            FROM season_event_points sep
            JOIN tournaments t ON sep.tournament_id = t.id
            JOIN players p ON sep.player_id = p.id
            WHERE p.name = :player_name
            ORDER BY sep.total_points DESC
        """
        df = pd.read_sql(sql, db_engine, params={'player_name': player_name})
    return df if len(df) > 0 else pd.DataFrame()

@st.cache_data
def get_cached_tournaments_list(_cache_key, season=None):
    """Cache tournaments list for dropdown selections."""
    if season:
        sql = """
            SELECT id, event_name, season, tournament_date, num_players, tournament_format
            FROM tournaments
            WHERE season = :season
            ORDER BY tournament_date DESC NULLS LAST, sequence_order ASC NULLS LAST
        """
        df = pd.read_sql(sql, db_engine, params={'season': season})
    else:
        sql = """
            SELECT id, event_name, season, tournament_date, num_players, tournament_format
            FROM tournaments
            ORDER BY tournament_date DESC NULLS LAST, sequence_order ASC NULLS LAST
        """
        df = pd.read_sql(sql, db_engine)
    return df if len(df) > 0 else pd.DataFrame()

@st.cache_data
def get_cached_tournaments_with_fsi(_cache_key, tournament_group=None):
    """Cache tournaments with FSI data for event points page."""
    if tournament_group:
        sql = """
            SELECT t.id, t.season, t.event_name, t.tournament_date, t.tournament_format, t.tournament_group, tf.fsi
            FROM tournaments t
            JOIN tournament_fsi tf ON t.id = tf.tournament_id
            WHERE t.tournament_group = :tournament_group
            ORDER BY t.tournament_date DESC NULLS LAST, t.created_at DESC
        """
        return pd.read_sql(sql, db_engine, params={'tournament_group': tournament_group})
    else:
        sql = """
            SELECT t.id, t.season, t.event_name, t.tournament_date, t.tournament_format, t.tournament_group, tf.fsi
            FROM tournaments t
            JOIN tournament_fsi tf ON t.id = tf.tournament_id
            ORDER BY t.tournament_date DESC NULLS LAST, t.created_at DESC
        """
        return pd.read_sql(sql, db_engine)

@st.cache_data
def get_cached_team_info(_cache_key, tournament_id):
    """Cache team information for doubles tournaments."""
    sql = """
        SELECT tr.player_id, tr.team_key, p.name as player_name
        FROM tournament_results tr
        JOIN players p ON tr.player_id = p.id
        WHERE tr.tournament_id = :tournament_id
        ORDER BY tr.place, p.name
    """
    return pd.read_sql(sql, db_engine, params={'tournament_id': int(tournament_id)})

@st.cache_data
def get_cached_points_by_place(_cache_key, tournament_group=None):
    """Cache points distribution data for FSI trends visualization."""
    if tournament_group:
        sql = """
            SELECT 
                t.id as tournament_id,
                t.event_name,
                t.season,
                t.tournament_format,
                t.tournament_group,
                t.tournament_date,
                sep.place,
                sep.total_points,
                sep.field_size,
                tf.fsi
            FROM season_event_points sep
            JOIN tournaments t ON sep.tournament_id = t.id
            JOIN tournament_fsi tf ON sep.tournament_id = tf.tournament_id
            WHERE t.tournament_group = :tournament_group
            ORDER BY t.tournament_date DESC, t.id, sep.place
        """
        return pd.read_sql(sql, db_engine, params={'tournament_group': tournament_group})
    else:
        sql = """
            SELECT 
                t.id as tournament_id,
                t.event_name,
                t.season,
                t.tournament_format,
                t.tournament_group,
                t.tournament_date,
                sep.place,
                sep.total_points,
                sep.field_size,
                tf.fsi
            FROM season_event_points sep
            JOIN tournaments t ON sep.tournament_id = t.id
            JOIN tournament_fsi tf ON sep.tournament_id = tf.tournament_id
            ORDER BY t.tournament_date DESC, t.id, sep.place
        """
        return pd.read_sql(sql, db_engine)

def get_cache_timestamp():
    """Get a human-readable timestamp for when data was last updated."""
    import datetime
    if 'last_cache_update' not in st.session_state:
        st.session_state.last_cache_update = datetime.datetime.now()
    return st.session_state.last_cache_update

def show_cache_freshness():
    """Display cache freshness indicator."""
    import datetime
    last_update = get_cache_timestamp()
    time_diff = datetime.datetime.now() - last_update
    
    if time_diff.total_seconds() < 60:
        freshness = "🟢 Fresh data (updated just now)"
    elif time_diff.total_seconds() < 300:
        mins = int(time_diff.total_seconds() / 60)
        freshness = f"🟢 Cached data (updated {mins} min ago)"
    elif time_diff.total_seconds() < 3600:
        mins = int(time_diff.total_seconds() / 60)
        freshness = f"🟡 Cached data (updated {mins} mins ago)"
    else:
        hours = int(time_diff.total_seconds() / 3600)
        freshness = f"🟡 Cached data (updated {hours}h ago)"
    
    st.caption(freshness)

def invalidate_data_cache():
    """Increment cache key to invalidate all cached data after mutations."""
    import datetime
    st.session_state.data_cache_key += 1
    st.session_state.last_cache_update = datetime.datetime.now()

def initialize_engine():
    if 'engine' not in st.session_state:
        st.session_state.engine = TTTRankingEngine()
    
    if 'points_engine' not in st.session_state:
        st.session_state.points_engine = PointsEngineDB(use_db_params=True)
        
    if 'db' not in st.session_state:
        st.session_state.db = DatabaseService()
    
    if 'data_cache_key' not in st.session_state:
        st.session_state.data_cache_key = 0

def seed_initial_data_if_empty():
    """Automatically load initial tournament data if database is empty (first run)."""
    if 'seeding_attempted' not in st.session_state:
        st.session_state.seeding_attempted = False
    
    if st.session_state.seeding_attempted:
        return
    
    tournaments = st.session_state.db.get_all_tournaments()
    
    if len(tournaments) == 0:
        st.session_state.seeding_attempted = True
        
        try:
            # Create progress tracking UI for initialization
            progress_bar = st.progress(0)
            progress_text = st.empty()
            progress_text.text("🔄 Loading historical tournament data...")
            
            df = load_initial_data()
            
            def update_init_progress(current, total, tournament_name):
                if total == 0:
                    progress_bar.progress(100)
                    progress_text.text("⚠️ No tournaments found in data file")
                    return
                progress_pct = int((current / total) * 100)
                progress_bar.progress(progress_pct)
                progress_text.text(f"Initializing database: {current}/{total} tournaments - {tournament_name}")
            
            processed, skipped = process_tournament_data(df, st.session_state.engine, progress_callback=update_init_progress)
            
            progress_bar.progress(100)
            progress_text.text(f"✅ Upload complete!")
            
            if processed > 0:
                # Run full recalculation (TrueSkill + Points)
                st.info("🔄 Calculating ratings and points...")
                
                # TrueSkill recalculation
                recalc_progress_bar = st.progress(0)
                recalc_progress_text = st.empty()
                
                def update_recalc_progress(current, total, tournament_name):
                    if total > 0:
                        progress_pct = int((current / total) * 100)
                        recalc_progress_bar.progress(progress_pct)
                        recalc_progress_text.text(f"TrueSkill: {current}/{total} - {tournament_name}")
                
                result = st.session_state.engine.recalculate_all_ratings(progress_callback=update_recalc_progress)
                
                if result['status'] == 'success':
                    recalc_progress_bar.progress(100)
                    recalc_progress_text.text("✅ TrueSkill complete!")
                    
                    # Points recalculation (ensure points_engine exists)
                    if 'points_engine' in st.session_state and st.session_state.points_engine is not None:
                        points_progress_bar = st.progress(0)
                        points_progress_text = st.empty()
                        
                        def update_points_progress(current, total, tournament_name):
                            if total > 0:
                                progress_pct = int((current / total) * 100)
                                points_progress_bar.progress(progress_pct)
                                points_progress_text.text(f"Season Points: {current}/{total} - {tournament_name}")
                        
                        try:
                            st.session_state.points_engine.recalculate_all(progress_callback=update_points_progress)
                            points_progress_bar.progress(100)
                            points_progress_text.text("✅ Season points complete!")
                            st.success(f"✅ Database initialized with {processed} tournaments, ratings, and season points!")
                        except Exception as e:
                            points_progress_text.text(f"❌ Points calculation error")
                            st.warning(f"⚠️ Ratings calculated but points failed: {str(e)}")
                            st.success(f"✅ Database initialized with {processed} tournaments and ratings!")
                    else:
                        st.warning("⚠️ Points engine not available during initialization. Please manually recalculate from Data Management.")
                        st.success(f"✅ Database initialized with {processed} tournaments and ratings!")
                else:
                    st.error(f"❌ Recalculation error: {result['message']}")
                    st.info(f"Uploaded {processed} tournaments but ratings calculation failed.")
                
                invalidate_data_cache()
                st.cache_data.clear()  # Force clear all cached data
                st.rerun()
        except Exception as e:
            st.error(f"⚠️ Auto-initialization failed: {str(e)}")
            st.info("Please use the 'Load Pre-loaded Tournament Data' button in Data Management section.")
    else:
        st.session_state.seeding_attempted = True

from process_tournament_data import process_tournament_data

def main():
    initialize_engine()
    seed_initial_data_if_empty()
    
    st.title("🎯 National Crokinole Association Ranking System")
    st.markdown("*TrueSkill Through Time player rankings and tournament analysis*")
    
    with st.sidebar:
        st.header("Navigation")
        
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
                "📈 FSI Trends",
                "---",
                "⚙️ System Parameters"
            ],
            label_visibility="collapsed")
        
        st.divider()
        
        st.subheader("System Status")
        stats = get_cached_system_stats(st.session_state.data_cache_key)
        
        if stats['has_data']:
            st.success("✅ Database Connected")
            st.metric("Total Players", stats['player_count'])
            st.metric("Tournaments Processed", stats['tournament_count'])
        else:
            st.info("ℹ️ Database Ready - Load Data")
    
    if page == "📊 Player Rankings":
        show_player_rankings()
    elif page == "🏆 Tournament Analysis":
        show_tournament_analysis()
    elif page == "🎲 Tier Prediction":
        from views import tier_prediction
        tier_prediction.render()
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
    elif page == "⚙️ System Parameters":
        from views import system_parameters
        system_parameters.render()
    elif page == "---":
        st.info("Please select a page from the sidebar.")

def show_technical_guide():
    st.header("📄 NCA Ranking System: Technical Guide")
    st.markdown("*Understanding the Dual Ranking System with Linder Wendt as Example*")
    
    col1, col2 = st.columns([3, 1])
    with col2:
        with open("NCA_Ranking_System_Technical_Guide.md", "rb") as file:
            st.download_button(
                label="📥 Download as Markdown",
                data=file,
                file_name="NCA_Ranking_System_Technical_Guide.md",
                mime="text/markdown",
                help="Download the complete guide as a markdown file"
            )
    
    st.divider()
    
    with open("NCA_Ranking_System_Technical_Guide.md", "r") as f:
        content = f.read()
    
    sections = content.split('\n## ')
    
    st.markdown(sections[0])
    
    for section in sections[1:]:
        lines = section.split('\n')
        section_title = lines[0]
        section_content = '\n'.join(lines[1:])
        
        with st.expander(f"## {section_title}", expanded=(section_title == "System Overview")):
            if "TrueSkill Player Rankings" in section_title:
                st.image("attached_assets/generated_images/TrueSkill_rating_components_diagram_b71680be.png", 
                        caption="TrueSkill Rating Components")
                section_content = section_content.replace(
                    "![TrueSkill Components](attached_assets/generated_images/TrueSkill_rating_components_diagram_b71680be.png)",
                    ""
                )
            
            if "Field Strength Index" in section_title:
                st.image("attached_assets/generated_images/FSI_calculation_comparison_diagram_2f012ec3.png",
                        caption="FSI Calculation: Singles vs Doubles")
                section_content = section_content.replace(
                    "![FSI Comparison](attached_assets/generated_images/FSI_calculation_comparison_diagram_2f012ec3.png)",
                    ""
                )
            
            if "Season Points System" in section_title:
                st.image("attached_assets/generated_images/Season_points_distribution_curve_1e56fb1a.png",
                        caption="Season Points Distribution Curve")
                section_content = section_content.replace(
                    "![Points Distribution](attached_assets/generated_images/Season_points_distribution_curve_1e56fb1a.png)",
                    ""
                )
            
            st.markdown(section_content)

def show_player_rankings():
    st.header("Player Rankings")
    
    stats = get_cached_system_stats(st.session_state.data_cache_key)
    if not stats['has_data']:
        st.info("Please load tournament data in the Data Management section to see rankings.")
        return
    
    # Tournament group filter
    groups_df = get_cached_tournament_groups(st.session_state.data_cache_key)
    tournament_groups = ['All'] + groups_df['tournament_group'].tolist() if len(groups_df) > 0 else ['All']
    
    st.info("""
    **Note on TTT Ratings:** TrueSkill Through Time uses a different scale than standard TrueSkill. 
    Ratings typically range from -2 to 8, with top players around 6-8. 
    (Standard TrueSkill ranges from 0-50).
    """)
    
    st.caption("TrueSkill ratings are calculated from all singles tournaments. The filter below shows only players who participated in the selected group's tournaments.")
    selected_group = st.selectbox("Tournament Group Filter", tournament_groups, index=0, key="player_rankings_group")
    
    # Pass tournament group to rankings query (None if "All" is selected)
    filter_group = None if selected_group == 'All' else selected_group
    # Get latest DB version for cache invalidation
    latest_db_update = get_latest_db_update()
    rankings_df = get_cached_rankings(st.session_state.data_cache_key, latest_db_update, tournament_group=filter_group)
    
    if len(rankings_df) == 0:
        st.info("Please load tournament data in the Data Management section to see rankings.")
        return
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Players", len(rankings_df))
    with col2:
        if len(rankings_df) > 0:
            top_player = rankings_df.iloc[0]
            st.metric("Top Ranked Player", top_player['player'], 
                     delta=f"Rating: {top_player['conservative_rating']:.2f}")
        else:
            st.metric("Top Ranked Player", "N/A")
    with col3:
        if len(rankings_df) > 0:
            top_player = rankings_df.iloc[0]
            st.metric("Top Player μ", f"{top_player['rating']:.2f}", 
                     delta=f"{top_player['tournaments_played']} tournaments")
        else:
            st.metric("Top Player μ", "N/A")
    with col4:
        avg_rating = rankings_df['rating'].mean() if len(rankings_df) > 0 else 0
        st.metric("Average Rating (all players)", f"{avg_rating:.2f}")
    
    st.divider()
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        min_tournaments = st.slider("Minimum Tournaments Played", 0, 10, 0)
    
    with col2:
        search_player = st.text_input("🔍 Search Player", "")
    
    filtered_df = rankings_df[rankings_df['tournaments_played'] >= min_tournaments]
    
    if search_player:
        filtered_df = filtered_df[filtered_df['player'].str.contains(search_player, case=False, na=False)]
    
    st.subheader(f"Rankings ({len(filtered_df)} players)")
    
    display_df = filtered_df.copy()
    display_df['rating'] = display_df['rating'].round(2)
    display_df['uncertainty'] = display_df['uncertainty'].round(2)
    display_df['conservative_rating'] = display_df['conservative_rating'].round(2)
    
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "rank": st.column_config.NumberColumn("Rank", format="%d"),
            "player": st.column_config.TextColumn("Player Name"),
            "rating": st.column_config.NumberColumn("Rating (μ)", format="%.2f"),
            "uncertainty": st.column_config.NumberColumn("Uncertainty (σ)", format="%.2f"),
            "conservative_rating": st.column_config.NumberColumn("Conservative Rating", format="%.2f", help="μ - 3σ"),
            "tournaments_played": st.column_config.NumberColumn("Tournaments", format="%d")
        }
    )
    
    if len(rankings_df) > 0:
        st.divider()
        st.subheader("Player Performance Analysis")
        
        selected_player = st.selectbox("Select Player for Detailed View", rankings_df['player'].tolist())
        
        if selected_player:
            player_history = st.session_state.engine.get_player_history(selected_player)
            
            if player_history:
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown(f"### {selected_player} - Rating History")
                    history_df = pd.DataFrame(player_history)
                    
                    # Create tournament labels (tournament name + season on one line)
                    tournament_labels = [f"{row['tournament']} S{row['season']}" 
                                        for _, row in history_df.iterrows()]
                    
                    fig = go.Figure()
                    
                    # Trace 1: Revised Conservative Rating (Smoothed)
                    fig.add_trace(go.Scatter(
                        x=tournament_labels,
                        y=history_df['conservative_rating'],
                        mode='lines+markers',
                        name='Revised Conservative (Smoothed)',
                        line=dict(color='#1f77b4', width=3),
                        hovertemplate='<b>Revised Cons.: %{y:.2f}</b><br><i>(Current estimate based on full history)</i><extra></extra>'
                    ))
                    
                    # Trace 2: Live Conservative Rating (Original)
                    fig.add_trace(go.Scatter(
                        x=tournament_labels,
                        y=history_df['conservative_rating_before'],
                        mode='lines+markers',
                        name='Live Conservative (Original)',
                        line=dict(color='#d62728', width=2, dash='dash'),
                        hovertemplate='<b>Live Cons.: %{y:.2f}</b><br><i>(Rating entering this tournament)</i><extra></extra>'
                    ))
                    
                    # Trace 3: Mu (Mean Rating)
                    fig.add_trace(go.Scatter(
                        x=tournament_labels,
                        y=history_df['after_mu'],
                        mode='lines+markers',
                        name='Mean Rating (μ)',
                        line=dict(color='#ff7f0e', width=2, dash='dot'),
                        hovertemplate='<b>Mean Rating: %{y:.2f}</b><br><i>(Raw skill estimate without uncertainty penalty)</i><extra></extra>'
                    ))
                    
                    # Calculate Y-axis range to prevent micro-movements from looking huge
                    all_y_values = pd.concat([
                        history_df['conservative_rating'], 
                        history_df['conservative_rating_before'],
                        history_df['after_mu']
                    ])
                    y_min = all_y_values.min()
                    y_max = all_y_values.max()
                    y_range = y_max - y_min
                    
                    # Enforce a minimum range of 0.5
                    min_range = 0.5
                    if y_range < min_range:
                        midpoint = (y_max + y_min) / 2
                        y_axis_range = [midpoint - (min_range / 2), midpoint + (min_range / 2)]
                    else:
                        # Add a little padding (5%) so points aren't on the edge
                        padding = y_range * 0.05
                        y_axis_range = [y_min - padding, y_max + padding]

                    fig.update_layout(
                        title=dict(
                            text="<b>Live vs. Revised Conservative Rating</b>",
                            x=0.05,
                            xanchor='left'
                        ),
                        xaxis_title="Tournament",
                        yaxis_title="Conservative Rating (μ - 3σ)",
                        hovermode='x unified',
                        height=500,
                        legend=dict(
                            orientation="h",
                            yanchor="bottom",
                            y=1.02,
                            xanchor="right",
                            x=1
                        ),
                        xaxis=dict(
                            tickfont=dict(size=9),
                            tickangle=90,
                            showgrid=True,
                            gridcolor='lightgray',
                            gridwidth=1
                        ),
                        yaxis=dict(
                            showgrid=True,
                            gridcolor='lightgray',
                            range=y_axis_range
                        ),
                        margin=dict(t=80)  # Add margin for title/legend
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                    
                    st.caption("""
                    **Understanding the Chart:**
                    - **🔵 Revised Conservative (Solid Blue)**: The player's conservative rating (μ - 3σ) as calculated *today*, using all historical data.
                    - **🔴 Live Conservative (Dashed Red)**: The player's conservative rating *entering* that tournament, based only on past results.
                    - **The Gap**: The difference shows how TTT retroactively corrected the rating.
                        - **Blue > Red**: The player was *underrated* at the time (performed better than expected).
                        - **Red > Blue**: The player was *overrated* at the time (performed worse than expected).
                    """)
                
                with col2:
                    st.markdown("### Tournament Results")
                    
                    # Select columns (removed Tier, before_mu, before_sigma)
                    display_history = history_df[['tournament_date', 'tournament', 'season', 'place', 
                                                 'after_mu', 'after_sigma', 
                                                 'conservative_rating_before', 'conservative_rating']].copy()
                    
                    # Sort by date descending (most recent first)
                    display_history = display_history.sort_values('tournament_date', ascending=False)
                    
                    # Format date as YYYY-MM
                    display_history['date'] = pd.to_datetime(display_history['tournament_date']).dt.strftime('%Y-%m')
                    
                    # Calculate Delta on Conservative Rating (Event Delta)
                    display_history['delta_cons'] = display_history['conservative_rating'] - display_history['conservative_rating_before']
                    
                    # Convert to numeric and round (handle any string/None values)
                    cols_to_round = ['after_mu', 'after_sigma', 
                                    'conservative_rating_before', 'conservative_rating', 'delta_cons']
                    for col in cols_to_round:
                        display_history[col] = pd.to_numeric(display_history[col], errors='coerce').round(2)
                    
                    # Rename columns with clear labels
                    display_history = display_history.rename(columns={
                        'date': 'Date',
                        'tournament': 'Tournament',
                        'season': 'Season',
                        'place': 'Place',
                        'after_mu': 'μ',
                        'after_sigma': 'σ',
                        'conservative_rating_before': 'Cons. In',
                        'conservative_rating': 'Cons. Out',
                        'delta_cons': 'Δ'
                    })
                    
                    # Reorder columns
                    display_history = display_history[['Date', 'Tournament', 'Season', 'Place', 
                                                       'μ', 'σ',
                                                       'Cons. In', 'Cons. Out', 'Δ']]
                    
                    st.dataframe(
                        display_history, 
                        use_container_width=True, 
                        hide_index=True,
                        column_config={
                            "Date": st.column_config.TextColumn("Date", width="small"),
                            "Tournament": st.column_config.TextColumn("Tournament", width="medium"),
                            "Season": st.column_config.NumberColumn("Season", format="%d", width="small"),
                            "Place": st.column_config.NumberColumn("Place", format="%d", width="small"),
                            "μ": st.column_config.NumberColumn("μ", format="%.2f", width="small"),
                            "σ": st.column_config.NumberColumn("σ", format="%.2f", width="small"),
                            "Cons. In": st.column_config.NumberColumn("Cons. In", format="%.2f", width="small"),
                            "Cons. Out": st.column_config.NumberColumn("Cons. Out", format="%.2f", width="small"),
                            "Δ": st.column_config.NumberColumn("Δ", format="%.2f", width="small"),
                        }
                    )
                    
                    # Add detailed explanation
                    st.caption("""
                    **Column Legend:**
                    - **μ (Mu)**: The player's estimated skill rating.
                    - **σ (Sigma)**: The uncertainty in the rating (lower is more confident).
                    - **Cons. In**: Conservative Rating (μ - 3σ) *entering* the tournament.
                    - **Cons. Out**: Conservative Rating *after* the tournament.
                    - **Δ (Delta)**: The change in Conservative Rating due to this event.
                    
                    *Note: TTT recalculates history, so "Cons. In" represents the rating you would have had entering the tournament given what we know now.*
                    """)
            
            else:
                st.info("No tournament history available for this player.")
    
    st.divider()
    
    st.subheader("Export Data")
    csv = rankings_df.to_csv(index=False)
    st.download_button(
        label="📥 Download Rankings CSV",
        data=csv,
        file_name="nca_player_rankings.csv",
        mime="text/csv"
    )

def show_tournament_analysis():
    st.header("Tournament Analysis")
    
    tournaments = st.session_state.db.get_all_tournaments()
    if len(tournaments) == 0:
        st.info("Please load tournament data in the Data Management section to see analysis.")
        return
    
    # Tournament group filter
    groups_df = get_cached_tournament_groups(st.session_state.data_cache_key)
    tournament_groups = ['All'] + groups_df['tournament_group'].tolist() if len(groups_df) > 0 else ['All']
    
    col1, col2 = st.columns(2)
    with col1:
        selected_group = st.selectbox("Tournament Group Filter", tournament_groups, index=0, key="tournament_analysis_group")
    with col2:
        selected_type = st.selectbox("Tournament Type Filter", ['All', 'Singles', 'Doubles'], index=0, key="tournament_analysis_type")
    
    # Get tournament strength data (now includes id, date, group, avg_rating_before, tournament_format)
    tournament_df = st.session_state.engine.get_tournament_strength()
    
    # Get FSI data
    fsi_df = get_cached_tournament_fsi(st.session_state.data_cache_key)
    
    # Merge FSI data if available
    if not fsi_df.empty:
        # Merge on id
        tournament_df = pd.merge(tournament_df, fsi_df[['id', 'fsi', 'avg_top_mu']], on='id', how='left')
    else:
        tournament_df['fsi'] = 0.0
        tournament_df['avg_top_mu'] = 0.0
        
    # Get scaling factor
    scaling_factor = 6.0
    if 'points_engine' in st.session_state and st.session_state.points_engine:
        scaling_factor = st.session_state.points_engine.fsi_scaling_factor
    
    # Calculate new metrics
    # Handle NaN values for tournaments without FSI data
    tournament_df['avg_top_mu'] = tournament_df['avg_top_mu'].fillna(0.0)
    tournament_df['fsi'] = tournament_df['fsi'].fillna(0.0)
    
    tournament_df['fsi_raw'] = tournament_df['avg_top_mu'] / scaling_factor
    tournament_df['fsi_all'] = tournament_df['avg_rating_before'] / scaling_factor
    
    # Apply filters
    if selected_group != 'All':
        tournament_df = tournament_df[tournament_df['tournament_group'] == selected_group]
        
    if selected_type != 'All':
        type_filter = 'singles' if selected_type == 'Singles' else 'doubles'
        tournament_df = tournament_df[tournament_df['tournament_format'] == type_filter]
    
    if len(tournament_df) == 0:
        st.warning(f"No tournament data available for selected filters.")
        return
    
    # Stats Header
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        st.metric("Total Tournaments", len(tournament_df))
    with col2:
        avg_field_size = tournament_df['num_players'].mean()
        st.metric("Avg Field Size", f"{avg_field_size:.1f}")
    with col3:
        avg_rating_all = tournament_df['avg_rating_before'].mean()
        st.metric("Avg Rating (all)", f"{avg_rating_all:.2f}")
    with col4:
        avg_rating_top20 = tournament_df['avg_top_mu'].mean()
        st.metric("Avg Rating (Top 20)", f"{avg_rating_top20:.2f}")
    with col5:
        avg_fsi_final = tournament_df['fsi'].mean()
        st.metric("FSI Final (Avg)", f"{avg_fsi_final:.3f}")
    with col6:
        st.metric("Scaling Factor", f"{scaling_factor:.1f}")
    
    st.divider()
    
    st.subheader("Tournament Strength Metrics")
    
    display_tournament_df = tournament_df.copy()
    display_tournament_df['avg_rating_before'] = pd.to_numeric(display_tournament_df['avg_rating_before'], errors='coerce').round(2)
    display_tournament_df['avg_rating_after'] = pd.to_numeric(display_tournament_df['avg_rating_after'], errors='coerce').round(2)
    
    # Format date
    display_tournament_df['tournament_date'] = pd.to_datetime(display_tournament_df['tournament_date']).dt.strftime('%Y-%m-%d')
    
    # Sort by date desc
    display_tournament_df = display_tournament_df.sort_values('tournament_date', ascending=False)
    
    st.dataframe(
        display_tournament_df[[
            'tournament', 'season', 'tournament_date', 'tournament_group', 'tournament_format',
            'num_players', 'avg_rating_before', 'avg_top_mu', 'fsi'
        ]],
        use_container_width=True,
        hide_index=True,
        height=1000, # Taller canvas (approx 30+ rows)
        column_config={
            "tournament": st.column_config.TextColumn("Tournament", width="medium"),
            "season": st.column_config.TextColumn("Season", width="small"),
            "tournament_date": st.column_config.TextColumn("Date", width="small"),
            "tournament_group": st.column_config.TextColumn("Tour", width="small"),
            "tournament_format": st.column_config.TextColumn("Type", width="small"),
            "num_players": st.column_config.NumberColumn("Field Size", format="%d"),
            "avg_rating_before": st.column_config.NumberColumn("Avg Rating (all)", format="%.2f"),
            "avg_top_mu": st.column_config.NumberColumn("Avg Rating (Top 20)", format="%.2f"),
            "fsi": st.column_config.NumberColumn("FSI Final", format="%.3f")
        }
    )
    
    st.divider()
    
    st.subheader("Field Strength Distribution")

def show_admin_section():
    st.header("Admin & Calculation Logs")
    
    tournaments = st.session_state.db.get_all_tournaments()
    if len(tournaments) == 0:
        st.info("Please load tournament data in the Data Management section to see logs.")
        return
    
    params = st.session_state.engine.get_parameters()
    
    st.subheader("TrueSkill Parameters")
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Initial μ (mu)", f"{params['mu']:.3f}")
    with col2:
        st.metric("Initial σ (sigma)", f"{params['sigma']:.3f}")
    with col3:
        st.metric("β (beta)", f"{params['beta']:.3f}")
    with col4:
        st.metric("τ (tau)", f"{params['tau']:.3f}")
    with col5:
        st.metric("Draw Probability", f"{params['draw_probability']:.3f}")
    
    st.info("""
    **Parameter Explanations:**
    - **μ (mu)**: Initial skill rating (default: 25.0)
    - **σ (sigma)**: Initial uncertainty (default: 8.333)
    - **β (beta)**: Skill class width (default: 4.166)
    - **τ (tau)**: Skill dynamics factor, prevents sigma from getting too small (default: 0.083)
    - **Draw Probability**: Probability of draws in matches (0.0 for tournaments)
    """)
    
    st.divider()
    
    st.subheader("Tournament Processing Logs")
    
    logs = st.session_state.engine.get_detailed_logs()
    
    if len(logs) > 0:
        selected_log_idx = st.selectbox(
            "Select Tournament to View Details",
            range(len(logs)),
            format_func=lambda i: f"{logs[i]['season']} - {logs[i]['tournament']} ({logs[i]['tier']}) - {logs[i]['num_players']} players"
        )
        
        selected_log = logs[selected_log_idx]
        
        st.markdown(f"### {selected_log['tournament']}")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Season", selected_log['season'])
        with col2:
            st.metric("Tier", selected_log['tier'])
        with col3:
            st.metric("Players", selected_log['num_players'])
        
        st.subheader("Rating Changes")
        
        changes_data = []
        for player, changes in selected_log['rating_changes'].items():
            changes_data.append({
                'Player': player,
                'Place': changes['place'],
                'Before μ': round(changes['before_mu'], 2),
                'After μ': round(changes['after_mu'], 2),
                'Δμ': round(changes['mu_change'], 2),
                'Before σ': round(changes['before_sigma'], 2),
                'After σ': round(changes['after_sigma'], 2),
                'Δσ': round(changes['sigma_change'], 2),
                'Conservative Before': round(changes['conservative_rating_before'], 2),
                'Conservative After': round(changes['conservative_rating_after'], 2)
            })
        
        changes_df = pd.DataFrame(changes_data)
        
        if not changes_df.empty:
            changes_df = changes_df.sort_values('Place')
            
            st.dataframe(changes_df, use_container_width=True, hide_index=True)
            
            st.divider()
            
            st.subheader("Rating Change Visualization")
            fig = px.scatter(changes_df, x='Place', y='Δμ', 
                             hover_data=['Player', 'Before μ', 'After μ'],
                             title="Rating Change vs Place",
                             labels={'Δμ': 'Rating Change (mu)', 'Place': 'Tournament Place'})
            fig.add_hline(y=0, line_dash="dash", line_color="gray")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No rating changes recorded for this tournament (likely Doubles or unprocessed).")
        
        st.divider()
        
        if not changes_df.empty:
            csv = changes_df.to_csv(index=False)
            st.download_button(
                label="📥 Download Tournament Log CSV",
                data=csv,
                file_name=f"tournament_log_{selected_log['tournament'].replace(' ', '_')}.csv",
                mime="text/csv"
            )
    else:
        st.warning("No calculation logs available.")

def show_data_management():
    st.header("Data Management")
    
    st.subheader("Upload Tournament Data")
    
    st.markdown("""
    Upload a CSV file with the following columns:
    
    **Required:**
    - `season`: Tournament season (e.g., 14, 15)
    - `event`: Tournament name
    - `tier`: Tournament tier (e.g., Tier 1, Tier 2, Major)
    - `place`: Player placement (1, 2, 3, etc.)
    - `player`: Player name
    
    **Optional (for chronological ordering):**
    - `tournament_date`: Date tournament occurred (YYYY-MM-DD format)
    - `sequence_order`: Manual sequence number (1, 2, 3...)
    """)
    
    uploaded_file = st.file_uploader("Choose a CSV file", type="csv")
    
    if uploaded_file is not None:
        try:
            # Try multiple encodings to handle files from different sources
            df = None
            encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
            
            for encoding in encodings:
                try:
                    uploaded_file.seek(0)  # Reset file pointer
                    # Force season column to be read as string to prevent float conversion
                    df = pd.read_csv(uploaded_file, encoding=encoding, dtype={'season': str})
                    break  # Success! Exit the loop
                except UnicodeDecodeError:
                    continue  # Try next encoding
            
            if df is None:
                st.error("❌ Unable to read file. Please ensure it's a valid CSV file with UTF-8 or Latin-1 encoding.")
            else:
                required_cols = ['season', 'event', 'tier', 'place', 'player']
                if all(col in df.columns for col in required_cols):
                    # Check for empty season values
                    empty_seasons = df['season'].isna() | (df['season'].astype(str).str.strip() == '')
                    if empty_seasons.any():
                        empty_count = empty_seasons.sum()
                        st.error(f"❌ Found {empty_count} row(s) with empty season values. Please ensure all rows have a valid season.")
                        st.dataframe(df[empty_seasons][['season', 'event', 'player', 'place']].head(20), use_container_width=True)
                    else:
                        # Normalize season column to ensure consistent format (16.0 → "16")
                        from db_service import normalize_season
                        df['season'] = df['season'].apply(normalize_season)
                        
                        st.success("✅ File format validated!")
                        
                        # Show column info for debugging
                        optional_found = []
                        if 'tournament_date' in df.columns:
                            optional_found.append(f"tournament_date ({df['tournament_date'].notna().sum()} values)")
                        if 'sequence_order' in df.columns:
                            optional_found.append(f"sequence_order ({df['sequence_order'].notna().sum()} values)")
                        
                        if optional_found:
                            st.info(f"📋 Optional fields found: {', '.join(optional_found)}")
                        
                        st.dataframe(df.head(10), use_container_width=True)
                        
                        st.warning("⚠️ **Stay on this page during upload!** Navigating away will interrupt the process.")
                        
                        if st.button("Process Uploaded Data"):
                            # Create progress tracking UI
                            progress_bar = st.progress(0)
                            progress_text = st.empty()
                            
                            def update_progress(current, total, tournament_name):
                                if total == 0:
                                    progress_bar.progress(100)
                                    progress_text.text("⚠️ No tournaments found in uploaded file")
                                    return
                                progress_pct = int((current / total) * 100)
                                progress_bar.progress(progress_pct)
                                progress_text.text(f"Processing tournament {current}/{total}: {tournament_name}")
                            
                            processed, skipped = process_tournament_data(df, st.session_state.engine, progress_callback=update_progress)
                            
                            progress_bar.progress(100)
                            progress_text.text(f"✅ Complete! Processed {processed} tournaments (skipped {skipped} duplicates)")
                            
                            # Auto-trigger recalculation to ensure chronological accuracy
                            # Always recalculate when tournaments are uploaded (even duplicates, as they may update dates/metadata)
                            total_tournaments = processed + skipped
                            if total_tournaments > 0:
                                st.info("🔄 Recalculating all ratings in chronological order...")
                                recalc_progress_bar = st.progress(0)
                                recalc_progress_text = st.empty()
                                
                                def update_recalc_progress(current, total, tournament_name):
                                    if total == 0:
                                        recalc_progress_bar.progress(100)
                                        recalc_progress_text.text("⚠️ No tournaments to recalculate")
                                        return
                                    progress_pct = int((current / total) * 100)
                                    recalc_progress_bar.progress(progress_pct)
                                    recalc_progress_text.text(f"Recalculating {current}/{total}: {tournament_name}")
                                
                                result = st.session_state.engine.recalculate_all_ratings(progress_callback=update_recalc_progress)
                                
                                if result['status'] == 'success':
                                    recalc_progress_bar.progress(100)
                                    recalc_progress_text.text("✅ TrueSkill ratings complete!")
                                    
                                    # Now calculate season points
                                    st.info("🏆 Calculating season points...")
                                    points_progress_bar = st.progress(0)
                                    points_progress_text = st.empty()
                                    
                                    def update_points_progress(current, total, tournament_name):
                                        if total == 0:
                                            points_progress_bar.progress(100)
                                            points_progress_text.text("⚠️ No tournaments to calculate points")
                                            return
                                        progress_pct = int((current / total) * 100)
                                        points_progress_bar.progress(progress_pct)
                                        points_progress_text.text(f"Calculating points {current}/{total}: {tournament_name}")
                                    
                                    try:
                                        st.session_state.points_engine.recalculate_all(progress_callback=update_points_progress)
                                        points_progress_bar.progress(100)
                                        points_progress_text.text("✅ Season points complete!")
                                        st.success(f"✅ Uploaded {processed} new tournaments (skipped {skipped} duplicates) and recalculated all ratings & points chronologically!")
                                    except Exception as e:
                                        points_progress_text.text(f"❌ Points calculation error")
                                        st.error(f"❌ Season points error: {str(e)}\n\nTrueSkill ratings completed successfully. Retry points calculation from Data Management.")
                                else:
                                    st.error(f"❌ Recalculation error: {result['message']}")
                            else:
                                st.warning("⚠️ No tournaments found in uploaded file")
                            
                            invalidate_data_cache()
                            st.cache_data.clear()  # Force clear all cached data
                            st.rerun()
                else:
                    st.error(f"❌ Missing required columns. Found: {df.columns.tolist()}")
        except Exception as e:
            st.error(f"Error reading file: {str(e)}")
    
    st.divider()
    
    st.subheader("Export All Data")
    
    players = st.session_state.db.get_all_players()
    if len(players) > 0:
        col1, col2, col3 = st.columns(3)
        
        with col1:
            tournaments = st.session_state.db.get_all_tournaments()
            export_data = []
            
            for tournament in tournaments:
                results = st.session_state.db.get_rating_changes_for_tournament(tournament.id)
                for result in results:
                    if result.player:
                        export_data.append({
                            'season': tournament.season,
                            'event': tournament.event_name,
                            'tier': tournament.tier,
                            'place': result.place,
                            'player': result.player.name,
                            'tournament_date': tournament.tournament_date.strftime('%Y-%m-%d') if tournament.tournament_date else '',
                            'sequence_order': tournament.sequence_order if tournament.sequence_order else ''
                        })
            
            if len(export_data) > 0:
                export_df = pd.DataFrame(export_data)
                csv_export = export_df.to_csv(index=False)
                st.download_button(
                    label="📥 Export All Tournament Data",
                    data=csv_export,
                    file_name="nca_all_tournament_data.csv",
                    mime="text/csv",
                    help="Download all tournaments in import-ready format"
                )
                st.caption(f"📊 {len(tournaments)} tournaments, {len(export_data)} results")
            else:
                st.warning("⚠️ No tournament data available to export")
        
        with col2:
            st.markdown("### 🔄 Recalculate All Rankings")
            st.info("""
            **Use this button to recalculate all player ratings from scratch in chronological order.**
            
            This will:
            - Reset all players to default rating (μ=25.0)
            - Clear all rating history
            - Reprocess ALL tournaments starting from the OLDEST
            - Rebuild ratings chronologically
            """)
            
            # Initialize confirmation state
            if 'confirm_recalc_data_mgmt' not in st.session_state:
                st.session_state.confirm_recalc_data_mgmt = False
            
            if not st.session_state.confirm_recalc_data_mgmt:
                if st.button("🔄 Recalculate All Rankings", type="primary", use_container_width=True, key="recalc_main"):
                    st.session_state.confirm_recalc_data_mgmt = True
                    st.rerun()
            else:
                st.warning("⚠️ This will recalculate ALL ratings from scratch. Continue?")
                
                col_confirm, col_cancel = st.columns([1, 1])
                with col_confirm:
                    if st.button("✅ Yes, Recalculate", type="primary", key="recalc_confirm"):
                        st.session_state.confirm_recalc_data_mgmt = False
                        
                        recalc_progress_bar = st.progress(0)
                        recalc_progress_text = st.empty()
                        
                        def update_recalc_progress(current, total, tournament_name):
                            if total == 0:
                                recalc_progress_bar.progress(100)
                                recalc_progress_text.text("⚠️ No tournaments to recalculate")
                                return
                            progress_pct = int((current / total) * 100)
                            recalc_progress_bar.progress(progress_pct)
                            recalc_progress_text.text(f"Recalculating {current}/{total}: {tournament_name}")
                        
                        result = st.session_state.engine.recalculate_all_ratings(progress_callback=update_recalc_progress)
                        
                        if result['status'] == 'success':
                            recalc_progress_bar.progress(100)
                            recalc_progress_text.text("✅ TrueSkill ratings complete!")
                            
                            # Now calculate season points
                            st.info("🏆 Calculating season points...")
                            points_progress_bar = st.progress(0)
                            points_progress_text = st.empty()
                            
                            def update_points_progress(current, total, tournament_name):
                                if total == 0:
                                    points_progress_bar.progress(100)
                                    points_progress_text.text("⚠️ No tournaments to calculate points")
                                    return
                                progress_pct = int((current / total) * 100)
                                points_progress_bar.progress(progress_pct)
                                points_progress_text.text(f"Calculating points {current}/{total}: {tournament_name}")
                            
                            try:
                                st.session_state.points_engine.recalculate_all(progress_callback=update_points_progress)
                                points_progress_bar.progress(100)
                                points_progress_text.text("✅ Season points complete!")
                                st.success(f"✅ {result['message']} and calculated season points!")
                            except Exception as e:
                                points_progress_text.text(f"❌ Points calculation error")
                                st.error(f"❌ Season points error: {str(e)}\n\nTrueSkill ratings completed successfully.")
                            
                            # Reload engine from database to get fresh ratings
                            st.session_state.engine.reload_from_db()
                            invalidate_data_cache()
                            st.cache_data.clear()  # Force clear all cached data
                            st.rerun()
                        else:
                            st.error(f"❌ {result['message']}")
                            
                with col_cancel:
                    if st.button("❌ Cancel", key="recalc_cancel"):
                        st.session_state.confirm_recalc_data_mgmt = False
                        st.rerun()
        
        with col3:
            logs = st.session_state.engine.get_detailed_logs()
            
            all_changes = []
            for log in logs:
                for player, changes in log['rating_changes'].items():
                    all_changes.append({
                        'tournament': log['tournament'],
                        'season': log['season'],
                        'tier': log['tier'],
                        'player': player,
                        'place': changes['place'],
                        'before_mu': changes['before_mu'],
                        'after_mu': changes['after_mu'],
                        'mu_change': changes['mu_change'],
                        'before_sigma': changes['before_sigma'],
                        'after_sigma': changes['after_sigma'],
                        'sigma_change': changes['sigma_change']
                    })
            
            logs_df = pd.DataFrame(all_changes)
            csv = logs_df.to_csv(index=False)
            st.download_button(
                label="📥 Download Complete Logs CSV",
                data=csv,
                file_name="nca_complete_calculation_logs.csv",
                mime="text/csv"
            )
        
        with col3:
            tournament_df = st.session_state.engine.get_tournament_strength()
            csv_tournament = tournament_df.to_csv(index=False)
            st.download_button(
                label="📥 Download Tournament Strength CSV",
                data=csv_tournament,
                file_name="nca_tournament_strength.csv",
                mime="text/csv"
            )
    
    st.divider()
    
    st.subheader("🗑️ Clear All Data")
    
    st.warning("""
    ⚠️ **Warning**: This will permanently delete ALL data from the database:
    - All player ratings
    - All tournaments
    - All rating history
    - All calculation logs
    
    **Use this when:**
    - You want to import fresh data from production
    - You need to start over with a clean database
    
    **Make sure to export your data first if you need a backup!**
    """)
    
    # Initialize confirmation state
    if 'confirm_clear_data' not in st.session_state:
        st.session_state.confirm_clear_data = False
    
    if not st.session_state.confirm_clear_data:
        if st.button("🗑️ Clear All Data", type="secondary"):
            st.session_state.confirm_clear_data = True
            st.rerun()
    else:
        st.error("⚠️ Are you absolutely sure? This cannot be undone!")
        
        col_confirm, col_cancel = st.columns([1, 1])
        with col_confirm:
            if st.button("✅ Yes, Delete Everything", key="confirm_delete"):
                with st.spinner("Clearing all data..."):
                    st.session_state.db.clear_all_data()
                    # Reinitialize both db and engine
                    st.session_state.db = DatabaseService()
                    st.session_state.engine = TrueSkillRankingEngineDB(use_db_params=True)
                    st.session_state.confirm_clear_data = False
                st.success("✅ All data cleared! You can now import fresh data.")
                invalidate_data_cache()
                st.rerun()
        with col_cancel:
            if st.button("❌ Cancel", key="cancel_delete"):
                st.session_state.confirm_clear_data = False
                st.rerun()

def show_parameter_tuning():
    st.header("⚙️ TrueSkill Through Time Parameter Tuning")
    
    st.info("""
    This section allows you to experiment with different TTT parameters to see how they affect rankings.
    **Note:** Changing parameters requires recalculating all ratings, which will clear current data and reprocess tournaments.
    """)
    
    current_params = st.session_state.engine.get_parameters()
    
    st.subheader("Current Parameters")
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("μ (mu)", f"{current_params['mu']:.1f}")
    with col2:
        st.metric("σ (sigma)", f"{current_params['sigma']:.3f}")
    with col3:
        st.metric("β (beta)", f"{current_params['beta']:.3f}")
    with col4:
        st.metric("γ (gamma)", f"{current_params['gamma']:.3f}")
    with col5:
        st.metric("Draw Prob", "N/A")
    
    st.divider()
    
    st.subheader("Adjust Parameters")
    
    with st.form("parameter_tuning_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            st.info("Base Parameters")
            # Mu is fixed at 0 for TTT usually, but we can display it
            st.text_input("Initial μ (mu)", value="0.0", disabled=True, help="Fixed at 0.0 for TTT standard implementation.")
            
            new_sigma = st.number_input(
                "Initial σ (sigma) - Starting uncertainty",
                min_value=1.0,
                max_value=15.0,
                value=float(current_params['sigma']),
                step=0.1,
                help="Default: 6.0. Higher values mean more uncertainty about initial skill levels."
            )
            
            new_beta = st.number_input(
                "β (beta) - Skill class width",
                min_value=0.1,
                max_value=10.0,
                value=float(current_params['beta']),
                step=0.1,
                help="Default: 1.0. The range of performance variance."
            )
            
        with col2:
            st.info("TTT Dynamics")
            
            new_gamma = st.number_input(
                "γ (gamma) - Skill drift over time",
                min_value=0.000,
                max_value=0.300,
                value=float(current_params['gamma']),
                step=0.001,
                format="%.3f",
                help="Default: 0.03. Controls how much skill can change over time. Higher = more volatile."
            )
            
            st.caption("Note: TTT uses Gamma instead of Tau to model skill evolution.")
            
        st.divider()
        st.info("Field Strength Index (FSI) Parameters")
        
        # Get current points parameters
        points_params = st.session_state.engine.db.get_points_parameters()
        
        col3, col4, col5 = st.columns(3)
        with col3:
            new_fsi_min = st.number_input(
                "FSI Minimum Clamp",
                min_value=0.1,
                max_value=2.0,
                value=float(points_params.fsi_min),
                step=0.1,
                help="Minimum multiplier for any tournament (default 0.8)"
            )
        with col4:
            new_fsi_max = st.number_input(
                "FSI Maximum Clamp",
                min_value=0.5,
                max_value=3.0,
                value=float(points_params.fsi_max),
                step=0.1,
                help="Maximum multiplier for top-tier tournaments (default 1.6)"
            )
        with col5:
            new_fsi_scaling = st.number_input(
                "FSI Scaling Factor",
                min_value=1.0,
                max_value=50.0,
                value=float(getattr(points_params, 'fsi_scaling_factor', 5.0)),
                step=0.1,
                help="Divisor for Average Top Rating. TTT ratings: top players ~5-8, so 5.0 scales to ~1.0-1.6. Lower = higher FSI values."
            )
            
        submit = st.form_submit_button("🔄 Recalculate with New Parameters", type="primary")
        
    if submit:
        st.warning("⚠️ Recalculating ratings... this may take a moment.")
        
        with st.spinner("Updating parameters and recalculating all ratings..."):
            # Update TTT parameters
            st.session_state.engine.update_parameters(
                sigma=new_sigma,
                beta=new_beta,
                gamma=new_gamma
            )
            
            # Update Points parameters (FSI clamps + scaling)
            st.session_state.engine.db.save_points_parameters(
                fsi_min=new_fsi_min,
                fsi_max=new_fsi_max,
                fsi_scaling_factor=new_fsi_scaling
            )
            
            # Trigger recalculation
            result = st.session_state.engine.recalculate_all_ratings()
            
            if result['status'] == 'success':
                st.success("✅ Parameters updated and ratings recalculated!")
                invalidate_data_cache()
                st.rerun()
            else:
                st.error(f"❌ Error: {result['message']}")
    
    st.divider()
    
    st.subheader("Parameter Presets")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📊 Conservative"):
            st.session_state.engine.update_parameters(sigma=6.0, beta=1.0, gamma=0.01)
            st.session_state.engine.recalculate_all_ratings()
            st.rerun()
            
    with col2:
        if st.button("⚖️ Standard TTT"):
            st.session_state.engine.update_parameters(sigma=6.0, beta=1.0, gamma=0.03)
            st.session_state.engine.recalculate_all_ratings()
            st.rerun()

    with col3:
        if st.button("⚡ Dynamic"):
            st.session_state.engine.update_parameters(sigma=6.0, beta=1.0, gamma=0.06)
            st.session_state.engine.recalculate_all_ratings()
            st.rerun()
    
    st.divider()
    st.divider()
    
    # Season Points Parameter Tuning Section
    st.header("🏆 Season Points Parameter Tuning")
    
    st.info("""
    Configure the Field-Weighted Points (FWP) system that powers the season leaderboards.
    These parameters control how tournament points are calculated and aggregated across the season.
    """)
    
    # Get current points parameters
    if not hasattr(st.session_state, 'points_engine') or st.session_state.points_engine is None:
        st.warning("Points engine not initialized. Please load tournament data first.")
        return
    
    from database import get_db_session, PointsParameters
    with get_db_session() as session:
        points_params = session.query(PointsParameters).filter_by(is_active=1).first()
        if not points_params:
            st.error("No active points parameters found in database.")
            return
    
    st.subheader("Current Season Points Parameters")
    
    # Display current tiered base points
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("🔝 Top Tier Base Points", f"{points_params.top_tier_base_points:.1f}", 
                 delta=f"FSI ≥ {points_params.top_tier_fsi_threshold}")
    with col2:
        st.metric("⚖️ Normal Tier Base Points", f"{points_params.normal_tier_base_points:.1f}",
                 delta=f"{points_params.low_tier_fsi_threshold} ≤ FSI < {points_params.top_tier_fsi_threshold}")
    with col3:
        st.metric("📉 Low Tier Base Points", f"{points_params.low_tier_base_points:.1f}",
                 delta=f"FSI < {points_params.low_tier_fsi_threshold}")
    
    st.subheader("FSI Calculation Parameters")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("FSI Scaling Factor", f"{points_params.fsi_scaling_factor:.2f}",
                 help="FSI = avg_top_mu / scaling_factor")
    with col2:
        st.metric("FSI Min (Floor)", f"{points_params.fsi_min:.2f}")
    with col3:
        st.metric("FSI Max (Ceiling)", f"{points_params.fsi_max:.2f}")
    
    st.subheader("Other Parameters")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Alpha (α)", f"{points_params.alpha:.2f}")
    with col2:
        st.metric("Bonus Scale", f"{points_params.bonus_scale:.2f}")
    with col3:
        st.metric("Best Tournaments", f"{points_params.best_tournaments_per_season}")
    with col4:
        st.metric("Top N for FSI", f"{points_params.top_n_for_fsi}")
    
    st.divider()
    
    st.subheader("Adjust Season Points Parameters")
    
    with st.form("season_points_tuning_form"):
        st.markdown("### Tiered Base Points System")
        st.caption("Award different base points based on tournament field strength (FSI)")
        
        col1, col2 = st.columns(2)
        
        with col1:
            new_top_tier_threshold = st.number_input(
                "🔝 Top Tier FSI Threshold",
                min_value=1.0,
                max_value=2.0,
                value=float(points_params.top_tier_fsi_threshold),
                step=0.05,
                help="Tournaments with FSI at or above this value get top tier points. Default: 1.35 (elite field strength)"
            )
            
            new_top_tier_points = st.number_input(
                "🔝 Top Tier Base Points",
                min_value=10.0,
                max_value=100.0,
                value=float(points_params.top_tier_base_points),
                step=5.0,
                help="Maximum points available for winning a top tier tournament. Default: 60 points"
            )
            
            new_low_tier_threshold = st.number_input(
                "📉 Low Tier FSI Threshold",
                min_value=0.5,
                max_value=1.5,
                value=float(points_params.low_tier_fsi_threshold),
                step=0.05,
                help="Tournaments with FSI below this value get low tier points. Default: 1.0 (weaker field strength)"
            )
        
        with col2:
            new_normal_tier_points = st.number_input(
                "⚖️ Normal Tier Base Points",
                min_value=10.0,
                max_value=100.0,
                value=float(points_params.normal_tier_base_points),
                step=5.0,
                help="Maximum points available for winning a normal tournament. Default: 50 points"
            )
            
            new_low_tier_points = st.number_input(
                "📉 Low Tier Base Points",
                min_value=10.0,
                max_value=100.0,
                value=float(points_params.low_tier_base_points),
                step=5.0,
                help="Maximum points available for winning a low tier tournament. Default: 40 points"
            )
        
        st.divider()
        st.markdown("### Points Calculation Parameters")
        
        col1, col2 = st.columns(2)
        
        with col1:
            new_alpha = st.number_input(
                "Alpha (α) - Exponential Decay",
                min_value=1.0,
                max_value=3.0,
                value=float(points_params.alpha),
                step=0.1,
                help="Controls point distribution curve. Higher = more top-heavy (winner gets much more). Default: 1.4"
            )
            
            new_bonus_scale = st.number_input(
                "Bonus Scale - Overperformance Multiplier",
                min_value=0.0,
                max_value=10.0,
                value=float(points_params.bonus_scale),
                step=0.5,
                help="Multiplier for bonus points when beating expected placement. 0 = disabled. Default: 0.0"
            )
            
            new_fsi_scaling_factor = st.number_input(
                "FSI Scaling Factor",
                min_value=1.0,
                max_value=5.0,
                value=float(points_params.fsi_scaling_factor),
                step=0.1,
                help="Scaling factor for FSI calculation: FSI = avg_top_mu / scaling_factor. Lower = higher FSI values. Default: 2.2"
            )
            
            new_fsi_min = st.number_input(
                "FSI Minimum - Lower Clamp",
                min_value=0.3,
                max_value=1.0,
                value=float(points_params.fsi_min),
                step=0.05,
                help="Minimum FSI value (floor). Prevents weak tournaments from being too low. Default: 0.5"
            )
        
        with col2:
            new_fsi_max = st.number_input(
                "FSI Maximum - Upper Clamp",
                min_value=1.0,
                max_value=2.0,
                value=float(points_params.fsi_max),
                step=0.05,
                help="Maximum FSI value (ceiling). Prevents elite tournaments from being too high. Default: 1.5"
            )
            
            new_top_n = st.number_input(
                "Top N Players for FSI",
                min_value=5,
                max_value=50,
                value=int(points_params.top_n_for_fsi),
                step=5,
                help="Number of top-rated players to average for FSI calculation. Default: 20"
            )
            
            new_best_tournaments = st.number_input(
                "Best Tournaments Per Season",
                min_value=1,
                max_value=10,
                value=int(points_params.best_tournaments_per_season),
                step=1,
                help="Number of best tournament results that count toward season total. Default: 5"
            )
        
        st.divider()
        st.markdown("### Doubles Tournament Parameters")
        st.caption("Separate parameters for doubles tournaments (team-based FSI and steeper points dropoff)")
        
        col1, col2 = st.columns(2)
        
        with col1:
            new_doubles_top_n = st.number_input(
                "Top N Teams for Doubles FSI",
                min_value=5,
                max_value=30,
                value=int(points_params.doubles_top_n_for_fsi),
                step=1,
                help="Number of top-rated teams to average for doubles FSI calculation. Default: 8 (vs 20 for singles)"
            )
        
        with col2:
            new_doubles_alpha = st.number_input(
                "Doubles Alpha (α)",
                min_value=1.0,
                max_value=3.0,
                value=float(points_params.doubles_alpha),
                step=0.1,
                help="Exponential decay for doubles points. Higher = steeper dropoff. Default: 2.0 (vs 1.4 for singles)"
            )
        
        description = st.text_area(
            "Description (optional)",
            value=points_params.description or "",
            placeholder="Describe why you're adjusting these parameters...",
            help="Notes about this parameter configuration for future reference."
        )
        
        submit_points = st.form_submit_button("💾 Save & Recalculate Season Points", type="primary")
    
    if submit_points:
        # Validate parameters
        try:
            if new_low_tier_threshold >= new_top_tier_threshold:
                st.error("❌ Low tier FSI threshold must be less than top tier threshold!")
            elif new_fsi_min >= new_fsi_max:
                st.error("❌ FSI minimum must be less than FSI maximum!")
            elif new_top_tier_points <= 0 or new_normal_tier_points <= 0 or new_low_tier_points <= 0:
                st.error("❌ All base points values must be positive!")
            else:
                with st.spinner("Saving parameters and recalculating all season points..."):
                    # Update parameters in database
                    with get_db_session() as session:
                        # Deactivate old params
                        session.query(PointsParameters).update({PointsParameters.is_active: 0})
                        
                        # Create new params
                        new_params = PointsParameters(
                            max_points=new_normal_tier_points,  # Legacy
                            alpha=new_alpha,
                            bonus_scale=new_bonus_scale,
                            fsi_min=new_fsi_min,
                            fsi_max=new_fsi_max,
                            fsi_scaling_factor=new_fsi_scaling_factor,
                            top_n_for_fsi=new_top_n,
                            best_tournaments_per_season=new_best_tournaments,
                            top_tier_fsi_threshold=new_top_tier_threshold,
                            top_tier_base_points=new_top_tier_points,
                            normal_tier_base_points=new_normal_tier_points,
                            low_tier_base_points=new_low_tier_points,
                            low_tier_fsi_threshold=new_low_tier_threshold,
                            doubles_top_n_for_fsi=new_doubles_top_n,
                            doubles_alpha=new_doubles_alpha,
                            is_active=1,
                            description=description
                        )
                        session.add(new_params)
                        session.commit()
                    
                    # Reinitialize points engine with new parameters
                    from points_engine_db import PointsEngineDB
                    st.session_state.points_engine = PointsEngineDB(use_db_params=True)
                    
                    # Recalculate all points
                    progress_placeholder = st.empty()
                    def progress_callback(current, total, name):
                        progress_placeholder.progress(current / total, text=f"Processing {current}/{total}: {name}")
                    
                    st.session_state.points_engine.recalculate_all(progress_callback=progress_callback)
                    progress_placeholder.empty()
                    
                    st.success("✅ Parameters saved and season points recalculated successfully!")
                    invalidate_data_cache()
                    st.cache_data.clear()  # Force clear all cached data
                    st.rerun()
        except Exception as e:
            st.error(f"❌ Error: {str(e)}")

def show_tier_comparison():
    st.header("Tier Comparison: Geographic vs Skill-Based")
    st.markdown("""
    Compare the traditional geographic tier system with skill-based tier recommendations.
    This analysis shows how tournament tiers would change if assigned based on actual field strength instead of location.
    """)
    
    tournaments = st.session_state.db.get_all_tournaments()
    if len(tournaments) == 0:
        st.info("Please load tournament data in the Data Management section to see tier comparison.")
        return
    
    comparison_data = []
    
    for tournament in tournaments:
        rating_changes = st.session_state.db.get_rating_changes_for_tournament(tournament.id)
        
        if len(rating_changes) == 0:
            continue
        
        conservative_ratings = []
        mu_ratings = []
        
        for rc in rating_changes:
            conservative = rc.before_mu - 3 * rc.before_sigma
            conservative_ratings.append(conservative)
            mu_ratings.append(rc.before_mu)
        
        if len(conservative_ratings) < 4:
            continue
        
        avg_conservative = sum(conservative_ratings) / len(conservative_ratings)
        avg_mu = sum(mu_ratings) / len(mu_ratings)
        
        sorted_conservative = sorted(conservative_ratings, reverse=True)
        top_5_count = min(5, len(sorted_conservative))
        top_5_avg = sum(sorted_conservative[:top_5_count]) / top_5_count
        
        sorted_conservative_all = sorted(conservative_ratings)
        percentile_75 = sorted_conservative_all[int(0.75 * len(sorted_conservative_all))] if len(sorted_conservative_all) > 0 else 0
        
        composite_score = (
            avg_conservative * 0.4 +
            top_5_avg * 0.3 +
            percentile_75 * 0.2 +
            avg_mu * 0.1
        )
        
        if composite_score >= 20:
            skill_tier = "Major"
        elif composite_score >= 18:
            skill_tier = "Tier 1"
        elif composite_score >= 15:
            skill_tier = "Tier 2"
        elif composite_score >= 12:
            skill_tier = "Tier 3"
        elif composite_score >= 9:
            skill_tier = "Tier 4"
        else:
            skill_tier = "Tier 5"
        
        geographic_tier = tournament.tier
        
        tier_order = {"Major": 0, "Tier 1": 1, "Tier 2": 2, "Tier 3": 3, "Tier 4": 4, "Tier 5": 5}
        geo_order = tier_order.get(geographic_tier, 999)
        skill_order = tier_order.get(skill_tier, 999)
        
        if geo_order < skill_order:
            delta = "Overrated"
        elif geo_order > skill_order:
            delta = "Underrated"
        else:
            delta = "Correct"
        
        comparison_data.append({
            'Tournament': tournament.event_name,
            'Season': tournament.season,
            'Geographic Tier': geographic_tier,
            'Skill-Based Tier': skill_tier,
            'Field Size': tournament.num_players,
            'Composite Score': composite_score,
            'Avg Rating': tournament.avg_rating_before,
            'Assessment': delta
        })
    
    if len(comparison_data) == 0:
        st.warning("Not enough tournament data for comparison.")
        return
    
    comparison_df = pd.DataFrame(comparison_data)
    
    st.divider()
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        overrated = len(comparison_df[comparison_df['Assessment'] == 'Overrated'])
        st.metric("Overrated Tournaments", overrated, 
                 help="Tournaments assigned a higher tier than field strength suggests")
    
    with col2:
        correct = len(comparison_df[comparison_df['Assessment'] == 'Correct'])
        st.metric("Correctly Rated", correct,
                 help="Tournaments where geographic tier matches skill-based tier")
    
    with col3:
        underrated = len(comparison_df[comparison_df['Assessment'] == 'Underrated'])
        st.metric("Underrated Tournaments", underrated,
                 help="Tournaments assigned a lower tier than field strength suggests")
    
    st.divider()
    
    st.subheader("Tournament-by-Tournament Comparison")
    
    assessment_filter = st.selectbox(
        "Filter by Assessment",
        ["All", "Overrated", "Correct", "Underrated"]
    )
    
    if assessment_filter != "All":
        filtered_df = comparison_df[comparison_df['Assessment'] == assessment_filter]
    else:
        filtered_df = comparison_df
    
    def highlight_assessment(row):
        if row['Assessment'] == 'Overrated':
            return ['background-color: #ffcccc'] * len(row)
        elif row['Assessment'] == 'Underrated':
            return ['background-color: #ccffcc'] * len(row)
        else:
            return ['background-color: #e6f2ff'] * len(row)
    
    styled_df = filtered_df.style.apply(highlight_assessment, axis=1).format({
        'Composite Score': '{:.2f}',
        'Avg Rating': '{:.2f}'
    })
    
    st.dataframe(styled_df, use_container_width=True, hide_index=True)
    
    st.divider()
    
    st.subheader("Visualization")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Assessment Distribution**")
        assessment_counts = comparison_df['Assessment'].value_counts()
        fig_pie = px.pie(
            values=assessment_counts.values,
            names=assessment_counts.index,
            title='Tier Assessment Breakdown',
            color=assessment_counts.index,
            color_discrete_map={
                'Overrated': '#ff6666',
                'Correct': '#6666ff',
                'Underrated': '#66ff66'
            }
        )
        st.plotly_chart(fig_pie, use_container_width=True)
    
    with col2:
        st.markdown("**Field Strength vs Geographic Tier**")
        fig_scatter = px.scatter(
            comparison_df,
            x='Composite Score',
            y='Geographic Tier',
            size='Field Size',
            color='Assessment',
            hover_data=['Tournament', 'Season'],
            title='Composite Score by Geographic Tier',
            color_discrete_map={
                'Overrated': '#ff6666',
                'Correct': '#6666ff',
                'Underrated': '#66ff66'
            }
        )
        st.plotly_chart(fig_scatter, use_container_width=True)
    
    st.divider()
    
    st.subheader("Key Insights")
    
    with st.expander("Understanding the Comparison"):
        st.markdown(f"""
        **Analysis Summary:**
        - **Total Tournaments Analyzed**: {len(comparison_df)}
        - **Overrated**: {overrated} tournaments ({overrated/len(comparison_df)*100:.1f}%) - Geographic tier is higher than field strength suggests
        - **Correctly Rated**: {correct} tournaments ({correct/len(comparison_df)*100:.1f}%) - Geographic tier matches skill-based analysis
        - **Underrated**: {underrated} tournaments ({underrated/len(comparison_df)*100:.1f}%) - Geographic tier is lower than field strength suggests
        
        **Why This Matters:**
        The traditional geographic tier system assigns tournament levels based on location, event size, or organizer status.
        However, actual field strength can vary significantly regardless of these factors. A small regional tournament
        with many elite players may have stronger competition than a large geographic "Tier 1" event with fewer top players.
        
        **Skill-Based Tier Benefits:**
        - **Fair Competition**: Players compete against similarly skilled opponents regardless of location
        - **Accurate Recognition**: Strong tournament fields receive appropriate tier recognition
        - **Objective Criteria**: Data-driven tier assignments eliminate subjective judgments
        - **Player Development**: Clearer understanding of tournament difficulty helps players choose appropriate competitions
        
        **Methodology:**
        Each tournament's field strength is analyzed using the same composite score calculation as the Tier Prediction tool,
        considering average conservative rating (μ - 3σ), top-5 player strength, field depth, and overall skill distribution.
        """)




def show_tournament_sequencing():
    st.header("📅 Tournament Sequencing")
    
    st.info("""
    **Why Tournament Order Matters:** TrueSkill ratings are calculated sequentially - earlier tournaments affect later ones. 
    To ensure accurate rankings, tournaments must be processed in chronological order (the order they actually occurred).
    """)
    
    tournaments = st.session_state.db.get_tournaments_chronological()
    
    if len(tournaments) == 0:
        st.warning("No tournaments in database. Please load tournament data first.")
        return
    
    st.subheader(f"Current Tournament Sequence ({len(tournaments)} tournaments)")
    
    tournament_data = []
    for i, t in enumerate(tournaments, start=1):
        tournament_data.append({
            'Seq': t.sequence_order if t.sequence_order else i,
            'ID': t.id,
            'Season': t.season,
            'Event': t.event_name,
            'Tier': t.tier,
            'Players': t.num_players,
            'Date': t.tournament_date.strftime('%Y-%m-%d') if t.tournament_date else 'Not Set',
            'Created': t.created_at.strftime('%Y-%m-%d %H:%M')
        })
    
    df = pd.DataFrame(tournament_data)
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    st.divider()
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Set Tournament Date")
        
        selected_tournament = st.selectbox(
            "Select Tournament",
            options=[(t.id, f"{t.season} - {t.event_name} ({t.tier})") for t in tournaments],
            format_func=lambda x: x[1]
        )
        
        if selected_tournament:
            tournament_id = selected_tournament[0]
            selected_t = next((t for t in tournaments if t.id == tournament_id), None)
            
            current_date = selected_t.tournament_date if selected_t and selected_t.tournament_date else None
            
            new_date = st.date_input(
                "Tournament Date",
                value=current_date if current_date else None,
                help="Set the actual date this tournament occurred"
            )
            
            if st.button("💾 Save Date"):
                if new_date:
                    from datetime import datetime as dt_class
                    date_with_time = dt_class.combine(new_date, dt_class.min.time())
                    st.session_state.db.update_tournament_date(tournament_id, date_with_time)
                    st.success(f"✅ Date saved for {selected_tournament[1]}")
                    st.rerun()
                else:
                    st.error("❌ Please select a date")
    
    with col2:
        st.subheader("Manual Sequence Order")
        
        st.markdown("Set custom sequence number (1 = earliest, higher = later)")
        
        selected_tournament_seq = st.selectbox(
            "Select Tournament ",
            options=[(t.id, f"{t.season} - {t.event_name} ({t.tier})") for t in tournaments],
            format_func=lambda x: x[1],
            key="seq_select"
        )
        
        if selected_tournament_seq:
            tournament_id_seq = selected_tournament_seq[0]
            selected_t_seq = next((t for t in tournaments if t.id == tournament_id_seq), None)
            
            current_seq = selected_t_seq.sequence_order if selected_t_seq and selected_t_seq.sequence_order else 0
            
            new_seq = st.number_input(
                "Sequence Order",
                min_value=1,
                max_value=len(tournaments),
                value=current_seq if current_seq > 0 else 1,
                step=1
            )
            
            if st.button("💾 Save Sequence"):
                st.session_state.db.update_tournament_sequence(tournament_id_seq, new_seq)
                st.success(f"✅ Sequence saved for {selected_tournament_seq[1]}")
                st.rerun()
    
    st.divider()
    
    st.subheader("⚙️ Actions")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🔄 Auto-Assign Sequence Numbers", help="Automatically assigns sequence 1, 2, 3... based on current date order"):
            st.session_state.db.auto_assign_tournament_sequence()
            st.success("✅ Sequence numbers auto-assigned!")
            st.rerun()
    
    with col2:
        if st.button("🔁 Recalculate Rankings in Sequence", type="primary"):
            st.warning("⚠️ This will recalculate ALL ratings based on current tournament sequence. Continue?")
            
            if 'confirm_recalc' not in st.session_state:
                st.session_state.confirm_recalc = False
            
            col_a, col_b = st.columns([1, 1])
            with col_a:
                if st.button("✅ Yes, Recalculate"):
                    with st.spinner("Recalculating ratings in chronological order..."):
                        from datetime import datetime
                        existing_tournaments = st.session_state.db.get_tournaments_chronological()
                        
                        tournament_data_list = []
                        for tournament in existing_tournaments:
                            results = st.session_state.db.get_rating_changes_for_tournament(tournament.id)
                            tournament_data_list.append({
                                'id': tournament.id,
                                'season': tournament.season,
                                'event': tournament.event_name,
                                'tier': tournament.tier,
                                'date': tournament.tournament_date,
                                'sequence': tournament.sequence_order,
                                'results': [(rc.player.name, rc.place) for rc in results if rc.player]
                            })
                        
                        # DEBUG: Log tournament metadata before sorting
                        print("\n=== TOURNAMENTS BEFORE SORT ===")
                        for t in tournament_data_list:
                            print(f"{t['event']}: Date={t['date']}, ID={t['id']}")
                        
                        # EXPLICIT PYTHON SORT: Force chronological order by tournament_date ONLY
                        # Sort by: tournament_date (or max_date for NULL), then ID as tiebreaker
                        max_date = datetime(2099, 12, 31)
                        tournament_data_list.sort(key=lambda t: (
                            t['date'] if t['date'] else max_date,
                            t['id']
                        ))
                        
                        # DEBUG: Log tournament order after sorting
                        print("\n=== TOURNAMENTS AFTER SORT (PROCESSING ORDER) ===")
                        for i, t in enumerate(tournament_data_list, 1):
                            print(f"{i}. {t['event']}: Date={t['date']}, ID={t['id']}")
                        print()
                        
                        st.session_state.db.clear_all_data()
                        
                        st.session_state.engine = TrueSkillRankingEngineDB(use_db_params=False)
                        
                        processed = 0
                        for t_data in tournament_data_list:
                            df_recalc = pd.DataFrame([
                                {'player': player, 'place': place}
                                for player, place in t_data['results']
                            ])
                            result = st.session_state.engine.process_tournament(
                                df_recalc, t_data['event'], t_data['season'], t_data['tier']
                            )
                            if result['status'] == 'success':
                                tournament = st.session_state.db.get_tournament_details(result['tournament_id'])
                                if t_data['date']:
                                    st.session_state.db.update_tournament_date(result['tournament_id'], t_data['date'])
                                if t_data['sequence']:
                                    st.session_state.db.update_tournament_sequence(result['tournament_id'], t_data['sequence'])
                                processed += 1
                    
                    st.success(f"✅ Recalculated {processed} tournaments in chronological order!")
                    invalidate_data_cache()
                    st.rerun()
            with col_b:
                if st.button("❌ Cancel"):
                    st.rerun()
    
    with col3:
        st.markdown("")
    
    st.divider()
    
    st.subheader("ℹ️ How Sequencing Works")
    with st.expander("Learn more about tournament sequencing"):
        st.markdown("""
        **Tournament Processing Order (SIMPLIFIED):**
        1. **By Tournament Date** - Tournaments process in chronological order by their date
        2. **By Created Date** - Fallback order for tournaments without dates (not recommended)
        
        **Why This Matters:**
        - TrueSkill ratings update incrementally based on each tournament
        - A player's rating from Tournament A affects their rating going into Tournament B
        - Processing tournaments out of order can produce incorrect rankings
        
        **Best Practices:**
        1. Set tournament dates for all historical tournaments
        2. Use "Auto-Assign Sequence Numbers" to maintain chronological order
        3. Recalculate rankings after making sequence changes
        4. For new tournament uploads, set the date immediately
        
        **Example:**
        - Ontario Singles (Jan 15, 2024) should be processed BEFORE Charleston (Feb 20, 2024)
        - If they're out of order, player ratings won't accurately reflect their skill progression
        """)

if __name__ == "__main__":
    main()
