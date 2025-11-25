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
            WHERE t.tournament_group = %(group)s
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
    """
    Cache season standings using SQL CTE to recompute best-5 totals per tournament group.
    
    Args:
        _cache_key: Cache invalidation key
        season: Optional season filter
        tournament_group: Optional tournament group filter ('NCA', 'UK', 'Other', or None for all)
    """
    # Build WHERE conditions
    where_conditions = []
    params = {}
    
    if season:
        where_conditions.append("t.season = %(season)s")
        params['season'] = season
    
    if tournament_group:
        where_conditions.append("t.tournament_group = %(tournament_group)s")
        params['tournament_group'] = tournament_group
    
    where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
    
    # SQL CTE to recompute best-5 totals with tournament_group filtering
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
            {where_clause}
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
            WHERE sep.tournament_id = %(tournament_id)s
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
            WHERE sep.season = %(season)s
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
            WHERE t.season = %(season)s
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
            WHERE p.name = %(player_name)s AND t.season = %(season)s
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
            WHERE p.name = %(player_name)s
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
            WHERE season = %(season)s
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
            WHERE t.tournament_group = %(tournament_group)s
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
        WHERE tr.tournament_id = %(tournament_id)s
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
            WHERE t.tournament_group = %(tournament_group)s
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
        
        # Add Refresh Button
        if st.button("🔄 Refresh Data", help="Clear cache and reload latest data from database"):
            invalidate_data_cache()
            st.rerun()
            
        page = st.radio(
            "Go to",
            [
                "📊 Player Rankings",
                "🏆 Tournament Analysis", 
                           "🎲 Tier Prediction", 
                           "📈 Tier Comparison",
                           "---",
                           "🌟 Season Standings",
                           "📊 Event Points",
                           "🎯 Player Top 5",
                           "📈 FSI Trends",
                           "---",
                           "📊 Data Crokinole",
                           "🎯 DataCrokinole FTT",
                           "📄 Technical Guide",
                           "---",
                           "🔧 Admin & Logs", 
                           "📤 Data Management", 
                           "⚙️ Parameter Tuning", 
                           "📅 Tournament Sequencing"
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
        show_tier_prediction()
    elif page == "📈 Tier Comparison":
        show_tier_comparison()
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
    elif page == "📊 Data Crokinole":
        from views import data_crokinole
        data_crokinole.render()
    elif page == "🎯 DataCrokinole FTT":
        from views import data_crokinole_ftt
        data_crokinole_ftt.render()
    elif page == "📄 Technical Guide":
        show_technical_guide()
    elif page == "🔧 Admin & Logs":
        show_admin_section()
    elif page == "📤 Data Management":
        show_data_management()
    elif page == "⚙️ Parameter Tuning":
        show_parameter_tuning()
    elif page == "📅 Tournament Sequencing":
        show_tournament_sequencing()
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
                    
                    # Round numeric columns
                    cols_to_round = ['after_mu', 'after_sigma', 
                                    'conservative_rating_before', 'conservative_rating', 'delta_cons']
                    for col in cols_to_round:
                        display_history[col] = display_history[col].round(2)
                    
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
    display_tournament_df['avg_rating_before'] = display_tournament_df['avg_rating_before'].round(2)
    display_tournament_df['avg_rating_after'] = display_tournament_df['avg_rating_after'].round(2)
    
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
    
    st.subheader("Tournament Strength by Tier")
    tier_comparison = tournament_df.groupby('tier').agg({
        'avg_rating_after': 'mean',
        'num_players': 'mean',
        'tournament': 'count'
    }).reset_index()
    tier_comparison.columns = ['tier', 'avg_strength', 'avg_field_size', 'count']
    
