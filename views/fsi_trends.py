"""FSI Trends Page - Visualizes Field Strength Index trends across tournaments."""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from db_service import normalize_season


def render():
    """Render the FSI Trends page."""
    st.title("📈 Field Strength Trends")
    
    # Import cached functions from app.py
    from app import (
        get_cached_points_by_place,
        get_cached_tournament_fsi,
        get_cached_tournament_groups,
        show_cache_freshness
    )
    
    # Get cache key from session state
    cache_key = st.session_state.get('data_cache_key', 0)
    
    st.info("""
    **Field Strength Index (FSI) visualization**
    
    FSI measures tournament quality based on the average TrueSkill rating of the top 20 players.  
    Higher FSI = stronger field = more points available.
    """)
    
    # Show cache freshness
    show_cache_freshness()
    
    # Get tournament groups for filter
    groups_df = get_cached_tournament_groups(cache_key)
    tournament_groups = ['All'] + groups_df['tournament_group'].tolist() if len(groups_df) > 0 else ['All']
    
    # ========== NEW SECTION: Points by Place Graph ==========
    st.divider()
    st.subheader("📊 Points Distribution by Place")
    st.caption("Analyze how points are allocated across finishing positions in different tournaments")
    
    # Tournament group filter (placed before getting data)
    selected_group_points = st.selectbox("Tournament Group", tournament_groups, index=0, key="fsi_trends_group")
    group_filter = None if selected_group_points == 'All' else selected_group_points
    
    # Get points data (cached with filter)
    points_df = get_cached_points_by_place(cache_key, tournament_group=group_filter)
    
    if len(points_df) == 0:
        st.warning("⚠️ No points data available. Please run recalculation from Data Management.")
    else:
        # Normalize seasons
        points_df['season'] = points_df['season'].apply(normalize_season)
        
        # Filters row
        col1, col2, col3 = st.columns([2, 2, 3])
        
        with col1:
            # Season filter - default to most recent
            seasons = sorted(points_df['season'].unique().tolist(), key=lambda x: int(x), reverse=True)
            selected_season = st.selectbox("Season", ["All Seasons"] + seasons, index=1 if len(seasons) > 0 else 0, key="points_season")
        
        with col2:
            # Format filter
            format_options = ["All Formats", "Singles", "Doubles"]
            selected_format = st.selectbox("Format", format_options, key="points_format")
        
        # Filter data
        filtered_points = points_df.copy()
        if selected_season != "All Seasons":
            filtered_points = filtered_points[filtered_points['season'] == selected_season]
        
        if selected_format == "Singles":
            filtered_points = filtered_points[filtered_points['tournament_format'] == 'singles']
        elif selected_format == "Doubles":
            filtered_points = filtered_points[filtered_points['tournament_format'] == 'doubles']
        
        if len(filtered_points) == 0:
            st.warning(f"⚠️ No data for {selected_season} / {selected_format}")
        else:
            # Get unique tournaments for dropdown
            tournament_options = filtered_points.groupby(['tournament_id', 'event_name', 'tournament_format', 'fsi']).first().reset_index()
            tournament_options['display_name'] = tournament_options.apply(
                lambda x: f"{x['event_name']} (Season {x['season']}) - {x['tournament_format'].upper()} - FSI: {x['fsi']:.2f}",
                axis=1
            )
            tournament_options = tournament_options.sort_values('tournament_date', ascending=False)
            
            with col3:
                # Tournament drill-down
                drill_down_options = ["All Tournaments"] + tournament_options['display_name'].tolist()
                selected_tournament = st.selectbox("Drill Down to Tournament", drill_down_options, key="points_tournament")
            
            # Apply drill-down filter
            if selected_tournament != "All Tournaments":
                selected_idx = tournament_options[tournament_options['display_name'] == selected_tournament].index[0]
                selected_id = tournament_options.loc[selected_idx, 'tournament_id']
                filtered_points = filtered_points[filtered_points['tournament_id'] == selected_id]
            
            # Create line graph
            fig = go.Figure()
            
            # Group by tournament
            for tournament_id in filtered_points['tournament_id'].unique():
                tournament_data = filtered_points[filtered_points['tournament_id'] == tournament_id].sort_values('place')
                
                # Create hover text
                hover_text = [
                    f"<b>{tournament_data.iloc[0]['event_name']}</b><br>" +
                    f"Season: {tournament_data.iloc[0]['season']}<br>" +
                    f"Format: {tournament_data.iloc[0]['tournament_format'].upper()}<br>" +
                    f"FSI: {tournament_data.iloc[0]['fsi']:.3f}<br>" +
                    f"Field Size: {tournament_data.iloc[0]['field_size']}<br>" +
                    f"Place: {row['place']}<br>" +
                    f"Points: {row['total_points']:.2f}"
                    for _, row in tournament_data.iterrows()
                ]
                
                # Add line for this tournament
                fig.add_trace(go.Scatter(
                    x=tournament_data['place'],
                    y=tournament_data['total_points'],
                    mode='lines+markers',
                    name=f"{tournament_data.iloc[0]['event_name']} (FSI: {tournament_data.iloc[0]['fsi']:.2f})",
                    hovertext=hover_text,
                    hoverinfo='text',
                    line=dict(width=2),
                    marker=dict(size=4)
                ))
            
            # Update layout
            fig.update_layout(
                xaxis_title="Finishing Place",
                yaxis_title="Total Points Awarded",
                height=600,
                hovermode='closest',
                legend=dict(
                    title="Tournament (FSI)",
                    yanchor="top",
                    y=0.99,
                    xanchor="right",
                    x=0.99,
                    bgcolor="rgba(255, 255, 255, 0.8)"
                ),
                margin=dict(r=20, t=20, b=50, l=60)
            )
            
            # Add grid
            fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='lightgray')
            fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='lightgray')
            
            st.plotly_chart(fig, width="stretch")
            
            # Summary stats
            st.caption(f"**Showing {len(filtered_points['tournament_id'].unique())} tournament(s)** | " +
                      f"FSI Range: {filtered_points['fsi'].min():.3f} - {filtered_points['fsi'].max():.3f} | " +
                      f"Avg Field Size: {filtered_points.groupby('tournament_id')['field_size'].first().mean():.0f}")
    
    st.divider()
    # ========== END NEW SECTION ==========
    
    # Get FSI data from database
    from app import get_cached_tournament_fsi
    fsi_df = get_cached_tournament_fsi(st.session_state.data_cache_key)
    
    if len(fsi_df) == 0:
        st.warning("⚠️ No FSI data available. Please run recalculation from Data Management.")
        return
    
    # Season filter - sort numerically so Season 16 comes before Season 9
    seasons = ["All Seasons"] + sorted(fsi_df['season'].unique().tolist(), key=lambda x: int(x) if x != "All Seasons" else 0, reverse=True)
    selected_season = st.selectbox("Filter by Season", seasons)
    
    if selected_season != "All Seasons":
        filtered_df = fsi_df[fsi_df['season'] == selected_season].copy()
    else:
        filtered_df = fsi_df.copy()
    
    if len(filtered_df) == 0:
        st.warning(f"⚠️ No data for {selected_season}")
        return
    
    # Convert tournament_date to datetime
    filtered_df['tournament_date'] = pd.to_datetime(filtered_df['tournament_date'])
    filtered_df = filtered_df.sort_values('tournament_date')
    
    # Add tournament index
    filtered_df['tournament_index'] = range(1, len(filtered_df) + 1)
    
    # Summary stats
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Tournaments", len(filtered_df))
    with col2:
        st.metric("Avg FSI", f"{filtered_df['fsi'].mean():.3f}")
    with col3:
        st.metric("Highest FSI", f"{filtered_df['fsi'].max():.3f}")
    with col4:
        st.metric("Lowest FSI", f"{filtered_df['fsi'].min():.3f}")
    
    st.divider()
    
    # FSI over time chart
    st.subheader("FSI Trends Over Time")
    
    # Create line chart with plotly
    if selected_season == "All Seasons":
        # Color by season
        fig = px.line(filtered_df, x='tournament_index', y='fsi', 
                     color='season',
                     hover_data=['event_name', 'avg_top_mu'],
                     labels={'tournament_index': 'Tournament #', 
                            'fsi': 'Field Strength Index',
                            'season': 'Season'},
                     title='FSI Trends Across All Seasons')
    else:
        # Single season
        fig = px.line(filtered_df, x='tournament_index', y='fsi',
                     hover_data=['event_name', 'avg_top_mu'],
                     labels={'tournament_index': 'Tournament #', 
                            'fsi': 'Field Strength Index'},
                     title=f'FSI Trends - Season {selected_season}')
        fig.update_traces(line_color='#1f77b4', mode='lines+markers')
    
    # Add reference line at FSI = 1.0 (baseline)
    fig.add_hline(y=1.0, line_dash="dash", line_color="gray", 
                  annotation_text="Baseline (FSI = 1.0)")
    
    fig.update_layout(height=500, hovermode='x unified')
    st.plotly_chart(fig, width="stretch")
    
    # Tournament table
    st.divider()
    st.subheader("Tournament FSI Details")
    
    # Format table
    display_df = filtered_df.copy()
    display_df['fsi'] = display_df['fsi'].round(2)
    display_df['avg_top_mu'] = display_df['avg_top_mu'].round(2)
    display_df['tournament_date'] = display_df['tournament_date'].dt.strftime('%Y-%m-%d')
    
    display_df = display_df[['event_name', 'season', 'tournament_date', 'fsi', 'avg_top_mu']]
    display_df = display_df.rename(columns={
        'event_name': 'Tournament',
        'season': 'Season',
        'tournament_date': 'Date',
        'fsi': 'FSI',
        'avg_top_mu': 'Avg Top-20 μ'
    })
    
    # Color-code FSI
    def highlight_fsi(row):
        colors = []
        for col in display_df.columns:
            if col == 'FSI':
                if row[col] >= 1.3:
                    colors.append('background-color: lightgreen')
                elif row[col] <= 0.9:
                    colors.append('background-color: lightcoral')
                else:
                    colors.append('')
            else:
                colors.append('')
        return colors
    
    styled_df = display_df.style.apply(highlight_fsi, axis=1)
    
    st.dataframe(styled_df, width="stretch", hide_index=True)

    # ========== FSI BREAKDOWN SECTION ==========
    st.divider()
    st.subheader("🧮 FSI Calculation Breakdown")
    st.caption("Select a tournament to see exactly how its Field Strength Index was calculated.")
    
    # Use filtered_df from above for options
    breakdown_options = filtered_df.sort_values('tournament_date', ascending=False)
    
    # Create display names with date
    breakdown_options['breakdown_label'] = breakdown_options.apply(
        lambda x: f"{x['event_name']} ({x['tournament_date'].strftime('%Y-%m-%d')}) - FSI: {x['fsi']:.3f}", 
        axis=1
    )
    
    selected_breakdown_label = st.selectbox(
        "Select Tournament for Breakdown",
        breakdown_options['breakdown_label'].tolist(),
        key="fsi_breakdown_select"
    )
    
    if selected_breakdown_label and 'points_engine' in st.session_state:
        # Get ID
        t_row = breakdown_options[breakdown_options['breakdown_label'] == selected_breakdown_label].iloc[0]
        t_id = int(t_row['id'])
        
        with st.spinner("Calculating breakdown..."):
            details = st.session_state.points_engine.get_fsi_details(t_id)
        
        if not details or 'error' in details:
            st.error(f"Could not calculate FSI breakdown: {details.get('error', 'Unknown error')}")
        else:
            # Display Top Players
            st.markdown(f"### 1. Top Players Used ({len(details['top_players'])})")
            st.markdown("The FSI is based on the average rating of the top players entering the tournament.")
            
            top_players_df = pd.DataFrame(details['top_players'])
            if not top_players_df.empty:
                top_players_df = top_players_df[['name', 'mu', 'sigma']]
                top_players_df.columns = ['Player', 'Entering Rating (μ)', 'Uncertainty (σ)']
                st.dataframe(top_players_df, width="stretch", hide_index=True)
            
            # Display Calculation
            st.markdown("### 2. Calculation Steps")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Avg Top Rating", f"{details['avg_top_mu']:.4f}")
            with col2:
                st.metric("Raw FSI", f"{details['fsi_raw']:.4f}")
            with col3:
                st.metric("Final FSI (Clamped)", f"{details['fsi_final']:.4f}")
            
            params = details['params']
            st.latex(r'''
            FSI_{raw} = \frac{Avg\mu}{Scaling\ Factor}
            ''')
            
            st.markdown(f"""
            **Parameters:**
            - $Avg\mu = {details['avg_top_mu']:.4f}$ (average rating of top players)
            - $Scaling\ Factor = {params['scaling_factor']:.2f}$ (tunable parameter)
            - $FSI_{{min}} = {params['fsi_min']}$ (floor)
            - $FSI_{{max}} = {params['fsi_max']}$ (ceiling)
            
            **Calculation:**
            $$
            FSI_{{raw}} = \\frac{{{details['avg_top_mu']:.4f}}}{{{params['scaling_factor']:.2f}}} = {details['fsi_raw']:.4f}
            $$
            """)
            
            if details['fsi_raw'] != details['fsi_final']:
                st.info(f"Note: The Raw FSI ({details['fsi_raw']:.4f}) was clamped to the allowed range [{params['fsi_min']}, {params['fsi_max']}].")

