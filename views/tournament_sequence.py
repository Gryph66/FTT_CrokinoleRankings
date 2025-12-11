"""
Tournament Sequence View (Public Site)
=======================================

Displays tournaments in their processing order for verification.
Read-only version for the public site.
"""

import streamlit as st
import pandas as pd
from database import engine as db_engine


def render():
    """Render the tournament sequence page."""
    st.header("Tournament Processing Sequence")
    
    st.markdown("""
    This page shows the exact order in which tournaments are processed for TTT calculations.
    The sequence determines the forward pass order and affects rating history.
    
    **Ordering Rules:**
    1. Primary: `sequence_order` (set by ordering algorithm)
    2. Fallback: Tournament date, then ID
    
    **Same-day ordering:**
    - WCC events: REC Doubles -> Main Doubles -> REC Singles -> Main Singles
    - Other events: Doubles before Singles
    - Same format: Alphabetical
    """)
    
    # Load tournaments
    sql = """
        SELECT 
            sequence_order,
            tournament_date,
            event_name,
            tournament_format,
            season,
            num_players,
            id
        FROM tournaments
        ORDER BY 
            sequence_order ASC NULLS LAST,
            tournament_date ASC NULLS LAST,
            id ASC
    """
    
    df = pd.read_sql(sql, db_engine)
    
    if df.empty:
        st.warning("No tournaments found.")
        return
    
    # Stats
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Tournaments", len(df))
    with col2:
        has_seq = df['sequence_order'].notna().sum()
        st.metric("With Sequence", has_seq)
    with col3:
        missing_seq = df['sequence_order'].isna().sum()
        st.metric("Missing Sequence", missing_seq)
    with col4:
        seasons = df['season'].nunique()
        st.metric("Seasons", seasons)
    
    # Filters
    st.subheader("Filters")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Sort numerically (16 before 9)
        seasons = ['All'] + sorted(df['season'].dropna().unique().tolist(), key=lambda x: int(x), reverse=True)
        selected_season = st.selectbox("Season", seasons)
    
    with col2:
        formats = ['All', 'singles', 'doubles']
        selected_format = st.selectbox("Format", formats)
    
    with col3:
        search = st.text_input("Search Event Name")
    
    # Apply filters
    filtered_df = df.copy()
    
    if selected_season != 'All':
        filtered_df = filtered_df[filtered_df['season'] == selected_season]
    
    if selected_format != 'All':
        filtered_df = filtered_df[filtered_df['tournament_format'] == selected_format]
    
    if search:
        filtered_df = filtered_df[filtered_df['event_name'].str.contains(search, case=False, na=False)]
    
    # Format date
    filtered_df['tournament_date'] = pd.to_datetime(filtered_df['tournament_date']).dt.strftime('%Y-%m-%d')
    
    # Display
    st.subheader(f"Tournament Order ({len(filtered_df)} shown)")
    
    # Add row number for display
    filtered_df = filtered_df.reset_index(drop=True)
    filtered_df.insert(0, '#', range(1, len(filtered_df) + 1))
    
    # Rename columns for display
    display_df = filtered_df.rename(columns={
        'sequence_order': 'Seq',
        'tournament_date': 'Date',
        'event_name': 'Event Name',
        'tournament_format': 'Format',
        'season': 'Season',
        'num_players': 'Players',
        'id': 'ID'
    })
    
    # Show table
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            '#': st.column_config.NumberColumn(width="small"),
            'Seq': st.column_config.NumberColumn(width="small"),
            'Date': st.column_config.TextColumn(width="medium"),
            'Event Name': st.column_config.TextColumn(width="large"),
            'Format': st.column_config.TextColumn(width="small"),
            'Season': st.column_config.TextColumn(width="small"),
            'Players': st.column_config.NumberColumn(width="small"),
            'ID': st.column_config.NumberColumn(width="small"),
        }
    )
    
    # Show same-day tournaments highlight
    st.subheader("Same-Day Tournament Groups")
    st.markdown("These tournaments occur on the same date and their order matters:")
    
    # Find same-day groups
    date_counts = df.groupby('tournament_date').size()
    same_day_dates = date_counts[date_counts > 1].index.tolist()
    
    if same_day_dates:
        for date in sorted(same_day_dates)[-10:]:  # Show last 10 same-day groups
            same_day_df = df[df['tournament_date'] == date].sort_values('sequence_order')
            
            if len(same_day_df) > 1:
                date_str = pd.to_datetime(date).strftime('%Y-%m-%d') if date else 'Unknown'
                with st.expander(f"**{date_str}** ({len(same_day_df)} tournaments)"):
                    for _, row in same_day_df.iterrows():
                        seq = row['sequence_order'] if pd.notna(row['sequence_order']) else '?'
                        fmt = row['tournament_format'] or 'singles'
                        st.write(f"{seq}. [{fmt.upper()}] {row['event_name']}")
    else:
        st.info("No same-day tournament groups found.")
