import streamlit as st
import pandas as pd
from typing import List, Tuple, Dict

def render():
    """Render the FSI Calculator and Pool Optimizer view."""
    st.header("Tournament FSI Calculator & Pool Optimizer")
    st.markdown("""
    Calculate the expected Field Strength Index (FSI) for your tournament and optimize pool assignments.
    """)
    
    # Get database and points engine from session state
    db = st.session_state.db
    points_engine = st.session_state.points_engine
    
    # Tournament format selection
    tournament_format = st.radio(
        "Tournament Format",
        options=["Singles", "Doubles"],
        horizontal=True
    )
    
    is_doubles = tournament_format == "Doubles"
    
    # Get parameters
    if is_doubles:
        top_n = points_engine.doubles_top_n_for_fsi
    else:
        top_n = points_engine.top_n_for_fsi
    
    scaling_factor = points_engine.fsi_scaling_factor
    fsi_min = points_engine.fsi_min
    fsi_max = points_engine.fsi_max
    
    st.divider()
    
    # Input section
    st.subheader("1. Enter Tournament Field")
    
    if is_doubles:
        st.info("For doubles, enter each team on a separate line using format: **Player 1 / Player 2**")
        placeholder = "Jon Beierling / Justin Slater\nAndrew Hutchinson / Devon Farthing\nJason Beierling / Tom Curry"
    else:
        st.info("Enter each player name on a separate line")
        placeholder = "Jon Beierling\nJustin Slater\nAndrew Hutchinson\nDevon Farthing"
    
    player_input = st.text_area(
        "Player/Team List",
        height=200,
        placeholder=placeholder,
        help="Paste or type player names (one per line)"
    )
    
    if not player_input.strip():
        st.info("Enter player names to calculate FSI and optimize pools.")
        return
    
    # Parse input
    lines = [line.strip() for line in player_input.strip().split('\n') if line.strip()]
    
    # Process based on format
    if is_doubles:
        teams, team_ratings = _process_doubles_input(lines, db)
        if not teams:
            return
        participants = teams
        ratings = [rating for rating, sigma in team_ratings]
    else:
        players, player_ratings = _process_singles_input(lines, db)
        if not players:
            return
        participants = players
        ratings = player_ratings
    
    st.success(f"✅ Found {len(participants)} {'teams' if is_doubles else 'players'}")
    
    st.divider()
    
    # FSI Calculation
    st.subheader("2. FSI Calculation")
    
    fsi, breakdown = _calculate_fsi(
        ratings, 
        top_n, 
        scaling_factor, 
        fsi_min, 
        fsi_max,
        is_doubles
    )
    
    # Display FSI result prominently
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Tournament FSI", f"{fsi:.4f}")
    with col2:
        st.metric(f"Top {breakdown['top_n_used']}", f"{breakdown['avg_top']:.4f}")
    with col3:
        st.metric("Scaling Factor", f"{scaling_factor:.1f}")
    with col4:
        st.metric("FSI Range", f"[{fsi_min}, {fsi_max}]")
    
    # Show calculation steps
    with st.expander("📊 Calculation Breakdown", expanded=True):
        st.markdown(f"""
        **Step-by-Step Calculation:**
        
        1. **Field Size**: {breakdown['field_size']} {'teams' if is_doubles else 'players'}
        2. **Top N for FSI**: {breakdown['top_n_used']} (configured: {top_n})
        3. **Average of Top {breakdown['top_n_used']}**: {breakdown['avg_top']:.4f}
        4. **Raw FSI** = {breakdown['avg_top']:.4f} ÷ {scaling_factor} = **{breakdown['fsi_raw']:.4f}**
        5. **Clamped FSI** = max({fsi_min}, min({breakdown['fsi_raw']:.4f}, {fsi_max})) = **{fsi:.4f}**
        """)
        
        # Show top players/teams
        st.markdown(f"**Top {breakdown['top_n_used']} {'Teams' if is_doubles else 'Players'}:**")
        top_df = pd.DataFrame({
            'Rank': range(1, len(breakdown['top_ratings']) + 1),
            'Name': [participants[i] for i in breakdown['top_indices']],
            'Rating (μ)': breakdown['top_ratings']
        })
        st.dataframe(top_df, width="stretch", hide_index=True)
    
    st.divider()
    
    # Pool Optimization
    st.subheader("3. Pool Optimization")
    
    num_pools = st.number_input(
        "Number of Pools",
        min_value=2,
        max_value=min(20, len(participants)),
        value=min(4, len(participants) // 5 + 1),
        help="Divide participants into balanced pools for round-robin play"
    )
    
    if st.button("Generate Balanced Pools", type="primary"):
        pools = _optimize_pools(participants, ratings, num_pools)
        _display_pools(pools, is_doubles)


def _process_singles_input(lines: List[str], db) -> Tuple[List[str], List[float]]:
    """Process singles player input and return player names and ratings."""
    players = []
    ratings = []
    missing = []
    
    for line in lines:
        player_name = line.strip()
        if not player_name:
            continue
            
        # Look up player in database
        player = db.get_player_by_name(player_name)
        if player:
            players.append(player_name)
            ratings.append(player.current_rating_mu)
        else:
            missing.append(player_name)
    
    if missing:
        st.warning(f"⚠️ The following players were not found in the database: {', '.join(missing)}")
    
    if not players:
        st.error("❌ No valid players found. Please check names and try again.")
        return [], []
    
    return players, ratings


def _process_doubles_input(lines: List[str], db) -> Tuple[List[str], List[Tuple[float, float]]]:
    """Process doubles team input and return team names and (avg_mu, avg_sigma) tuples."""
    teams = []
    team_ratings = []
    missing = []
    
    for line in lines:
        if '/' not in line:
            st.error(f"❌ Invalid doubles format: '{line}'. Use 'Player 1 / Player 2'")
            continue
        
        parts = [p.strip() for p in line.split('/')]
        if len(parts) != 2:
            st.error(f"❌ Invalid doubles format: '{line}'. Use exactly 2 players separated by '/'")
            continue
        
        player1_name, player2_name = parts
        
        # Look up both players
        player1 = db.get_player_by_name(player1_name)
        player2 = db.get_player_by_name(player2_name)
        
        if not player1:
            missing.append(player1_name)
        if not player2:
            missing.append(player2_name)
        
        if player1 and player2:
            # Calculate team rating (average of both players)
            team_mu = (player1.current_rating_mu + player2.current_rating_mu) / 2.0
            team_sigma = (player1.current_rating_sigma + player2.current_rating_sigma) / 2.0
            
            teams.append(f"{player1_name} / {player2_name}")
            team_ratings.append((team_mu, team_sigma))
    
    if missing:
        st.warning(f"⚠️ The following players were not found in the database: {', '.join(set(missing))}")
    
    if not teams:
        st.error("❌ No valid teams found. Please check names and try again.")
        return [], []
    
    return teams, team_ratings


def _calculate_fsi(
    ratings: List[float],
    top_n: int,
    scaling_factor: float,
    fsi_min: float,
    fsi_max: float,
    is_doubles: bool
) -> Tuple[float, Dict]:
    """Calculate FSI and return result with breakdown."""
    field_size = len(ratings)
    
    # Get top N ratings
    sorted_ratings = sorted(ratings, reverse=True)
    top_n_used = min(top_n, field_size)
    top_ratings = sorted_ratings[:top_n_used]
    
    # Get indices of top players
    top_indices = sorted(
        range(len(ratings)),
        key=lambda i: ratings[i],
        reverse=True
    )[:top_n_used]
    
    # Calculate average
    avg_top = sum(top_ratings) / len(top_ratings) if top_ratings else 0.0
    
    # Apply scaling
    fsi_raw = avg_top / scaling_factor
    
    # Clamp
    fsi = max(fsi_min, min(fsi_raw, fsi_max))
    
    breakdown = {
        'field_size': field_size,
        'top_n_used': top_n_used,
        'avg_top': avg_top,
        'fsi_raw': fsi_raw,
        'top_ratings': top_ratings,
        'top_indices': top_indices
    }
    
    return fsi, breakdown


def _optimize_pools(participants: List[str], ratings: List[float], num_pools: int) -> List[List[Tuple[str, float]]]:
    """Optimize pool assignments using snake draft algorithm."""
    # Create list of (participant, rating) tuples and sort by rating
    player_ratings = list(zip(participants, ratings))
    player_ratings.sort(key=lambda x: x[1], reverse=True)
    
    # Initialize pools
    pools = [[] for _ in range(num_pools)]
    
    # Snake draft assignment
    for i, (player, rating) in enumerate(player_ratings):
        pool_index = i % num_pools
        
        # Reverse direction on odd passes
        if (i // num_pools) % 2 == 1:
            pool_index = num_pools - 1 - pool_index
        
        pools[pool_index].append((player, rating))
    
    return pools


def _display_pools(pools: List[List[Tuple[str, float]]], is_doubles: bool):
    """Display the optimized pools with fairness metrics."""
    st.markdown("### Pool Assignments")
    
    # Calculate fairness metrics
    pool_avgs = [sum(r for _, r in pool) / len(pool) if pool else 0 for pool in pools]
    overall_avg = sum(pool_avgs) / len(pool_avgs) if pool_avgs else 0
    max_deviation = max(abs(avg - overall_avg) for avg in pool_avgs) if pool_avgs else 0
    
    # Fairness score (0-100, higher is better)
    fairness_score = max(0, 100 - (max_deviation / overall_avg * 100)) if overall_avg > 0 else 100
    
    # Display fairness metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Fairness Score", f"{fairness_score:.1f}/100")
    with col2:
        st.metric("Overall Avg Rating", f"{overall_avg:.2f}")
    with col3:
        st.metric("Max Deviation", f"{max_deviation:.2f}")
    
    if fairness_score >= 90:
        st.success("✅ **Excellent Balance**: Pools are very evenly matched!")
    elif fairness_score >= 75:
        st.info("ℹ️ **Good Balance**: Pools are reasonably balanced.")
    else:
        st.warning("⚠️ **Fair Balance**: Some variation between pools, but acceptable.")
    
    st.divider()
    
    # Display each pool
    cols = st.columns(len(pools))
    for i, (col, pool) in enumerate(zip(cols, pools)):
        with col:
            pool_avg = pool_avgs[i]
            deviation = pool_avg - overall_avg
            deviation_text = f"{deviation:+.2f}" if deviation != 0 else "±0.00"
            
            st.markdown(f"#### Pool {i + 1}")
            st.caption(f"Avg: {pool_avg:.2f} ({deviation_text})")
            
            pool_df = pd.DataFrame({
                'Name': [name for name, _ in pool],
                'Rating': [f"{rating:.2f}" for _, rating in pool]
            })
            st.dataframe(pool_df, width="stretch", hide_index=True, height=min(400, len(pool) * 35 + 38))
