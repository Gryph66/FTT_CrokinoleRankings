import streamlit as st
import pandas as pd
import difflib
import random
import math
from typing import List, Tuple, Dict, Set

def render():
    """Render the FSI Calculator and Pool Optimizer view."""
    st.header("Tournament FSI Calculator & Pool Optimizer")
    st.markdown("""
    Calculate the expected Field Strength Index (FSI) for your tournament and optimize pool assignments.
    """)
    
    # Get database and points engine from session state
    db = st.session_state.db
    points_engine = st.session_state.points_engine
    
    # Initialize resolutions state if not present
    if 'tier_resolutions' not in st.session_state:
        st.session_state.tier_resolutions = {}
    
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
    
    col_input, col_res = st.columns([2, 1])
    
    with col_input:
        if is_doubles:
            st.info("For doubles, enter each team on a separate line using format: **Player 1 / Player 2**")
            placeholder = "Jon Beierling / Justin Slater\nAndrew Hutchinson / Devon Farthing\nJason Beierling / Tom Curry"
        else:
            st.info("Enter each player name on a separate line")
            placeholder = "Jon Beierling\nJustin Slater\nAndrew Hutchinson\nDevon Farthing"
        
        player_input = st.text_area(
            "Player/Team List",
            height=300,
            placeholder=placeholder,
            help="Paste or type player names (one per line)"
        )
        
        if st.session_state.tier_resolutions:
            if st.button("Clear Saved Resolutions"):
                st.session_state.tier_resolutions = {}
                st.rerun()
    
    if not player_input.strip():
        st.info("Enter player names to calculate FSI and optimize pools.")
        return
    
    # Parse input
    lines = [line.strip() for line in player_input.strip().split('\n') if line.strip()]
    
    # Process based on format
    if is_doubles:
        teams, team_ratings, missing = _process_doubles_input(lines, db, st.session_state.tier_resolutions, points_engine)
        if not teams and not missing:
            return
        participants = teams
        ratings = team_ratings
    else:
        participants, ratings, missing = _process_singles_input(lines, db, st.session_state.tier_resolutions)
    
    # Handle Missing Players
    if missing:
        with col_res:
            st.warning(f"⚠️ {len(missing)} Unknown Players")
            st.caption("Please resolve missing players to proceed.")
            
            # Get all player names for fuzzy matching
            all_players = [p.name for p in db.get_all_players()]
            
            for name in missing:
                st.markdown(f"**{name}**")
                
                # Find close matches
                matches = difflib.get_close_matches(name, all_players, n=5, cutoff=0.4)
                options = ["Select Action...", "New Player (Rating 0)"] + matches
                
                # Unique key for each selectbox
                key = f"resolve_{name}_{hash(name)}"
                selection = st.selectbox(
                    "Resolve as:",
                    options,
                    key=key,
                    label_visibility="collapsed"
                )
                
                if selection != "Select Action...":
                    if selection == "New Player (Rating 0)":
                        st.session_state.tier_resolutions[name] = "NEW_PLAYER"
                    else:
                        st.session_state.tier_resolutions[name] = selection
                    st.rerun()
                st.divider()
        
        # Don't show results until resolved
        st.info("👈 Please resolve all unknown players in the sidebar to calculate FSI.")
        return

    # If we have participants (and no missing), proceed
    if not participants:
        st.error("❌ No valid participants found.")
        return
        
    st.success(f"✅ Found {len(participants)} {'teams' if is_doubles else 'players'}")
    
    # --- Corrected List Display ---
    st.markdown("### ✅ Corrected Player List (Copy & Paste)")
    st.caption("Copy these names back to your spreadsheet to fix any typos.")
    
    clean_list = []
    for p in participants:
        # Remove " (New)" suffix if present
        clean_name = p.replace(" (New)", "")
        clean_list.append(clean_name)
        
    st.text_area(
        "Corrected List",
        value="\n".join(clean_list),
        height=200,
        label_visibility="collapsed"
    )
    # -----------------------------
    
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
    
    col_pools, col_method = st.columns(2)
    
    with col_pools:
        num_pools = st.number_input(
            "Number of Pools",
            min_value=2,
            max_value=min(20, len(participants)),
            value=min(4, len(participants) // 5 + 1),
            help="Divide participants into balanced pools for round-robin play"
        )
    
    with col_method:
        optimization_method = st.radio(
            "Optimization Method",
            options=["Snake Draft", "Simulated Annealing"],
            horizontal=True,
            help="Snake Draft is fast and simple. Simulated Annealing finds more optimal pool balance."
        )
    
    if st.button("Generate Balanced Pools", type="primary"):
        if optimization_method == "Snake Draft":
            pools = _optimize_pools_snake(participants, ratings, num_pools)
        else:
            pools = _optimize_pools_annealing(participants, ratings, num_pools)
        _display_pools(pools, is_doubles)


def _resolve_player(name: str, db, resolutions: Dict[str, str]) -> Tuple[str, float, bool]:
    """
    Resolve a player name to (display_name, rating, found).
    Returns found=False if not in DB and not in resolutions.
    """
    # Check resolutions first
    if name in resolutions:
        res = resolutions[name]
        if res == "NEW_PLAYER":
            return f"{name} (New)", 0.0, True
        else:
            # Mapped to existing player
            player = db.get_player_by_name(res)
            if player:
                return player.name, player.current_rating_mu, True
            # If mapped player not found (rare), treat as missing
            return name, 0.0, False
            
    # Check DB directly
    player = db.get_player_by_name(name)
    if player:
        return player.name, player.current_rating_mu, True
        
    return name, 0.0, False


def _process_singles_input(lines: List[str], db, resolutions: Dict[str, str]) -> Tuple[List[str], List[float], Set[str]]:
    """Process singles player input and return player names, ratings, and missing names."""
    players = []
    ratings = []
    missing = set()
    
    for line in lines:
        name = line.strip()
        if not name:
            continue
            
        display_name, rating, found = _resolve_player(name, db, resolutions)
        
        if found:
            players.append(display_name)
            ratings.append(rating)
        else:
            missing.add(name)
    
    return players, ratings, missing


def _process_doubles_input(lines: List[str], db, resolutions: Dict[str, str], points_engine) -> Tuple[List[str], List[float], Set[str]]:
    """Process doubles team input and return team names, avg_mu (weighted), and missing player names."""
    teams = []
    team_ratings = []
    missing = set()
    
    for line in lines:
        if '/' not in line:
            continue
        
        parts = [p.strip() for p in line.split('/')]
        if len(parts) != 2:
            continue
        
        p1_name, p2_name = parts
        if not p1_name or not p2_name:
            continue
            
        # Resolve both players
        p1_disp, p1_mu, p1_found = _resolve_player(p1_name, db, resolutions)
        p2_disp, p2_mu, p2_found = _resolve_player(p2_name, db, resolutions)
        
        if not p1_found:
            missing.add(p1_name)
        if not p2_found:
            missing.add(p2_name)
            
        if p1_found and p2_found:
            # Weighted average for doubles teams
            mus = [p1_mu, p2_mu]
            high_mu = max(mus)
            low_mu = min(mus)
            weight = getattr(points_engine, 'doubles_weight_high', 0.65)
            team_mu = (high_mu * weight) + (low_mu * (1.0 - weight))
            
            teams.append(f"{p1_disp} / {p2_disp}")
            team_ratings.append(team_mu)
            
    return teams, team_ratings, missing


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


def _optimize_pools_snake(participants: List[str], ratings: List[float], num_pools: int) -> List[List[Tuple[str, float]]]:
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


def _calculate_pool_variance(pools: List[List[Tuple[str, float]]]) -> float:
    """Calculate variance of pool averages."""
    if not pools:
        return 0.0
    pool_avgs = [sum(r for _, r in pool) / len(pool) if pool else 0 for pool in pools]
    overall_avg = sum(pool_avgs) / len(pool_avgs) if pool_avgs else 0
    variance = sum((avg - overall_avg) ** 2 for avg in pool_avgs) / len(pool_avgs)
    return variance


def _count_zero_rated(pool: List[Tuple[str, float]]) -> int:
    """Count players with 0 rating in a pool."""
    return sum(1 for _, rating in pool if rating == 0.0)


def _optimize_pools_annealing(participants: List[str], ratings: List[float], num_pools: int) -> List[List[Tuple[str, float]]]:
    """
    Optimize pool assignments using Simulated Annealing.
    Starts with snake draft and iteratively improves by swapping players.
    
    Constraint: No pool should have more than ceil(num_zero_rated / num_pools) 
    players with 0 rating, ensuring even distribution of new players.
    """
    # Count 0-rated players and calculate max per pool
    num_zero_rated = sum(1 for r in ratings if r == 0.0)
    max_zeros_per_pool = math.ceil(num_zero_rated / num_pools) if num_zero_rated > 0 else 0
    
    # Start with snake draft as initial solution
    pools = _optimize_pools_snake(participants, ratings, num_pools)
    
    # Simulated annealing parameters
    initial_temp = 1.0
    cooling_rate = 0.995
    min_temp = 0.001
    iterations_per_temp = 50
    
    current_variance = _calculate_pool_variance(pools)
    best_pools = [pool[:] for pool in pools]  # Deep copy
    best_variance = current_variance
    
    temperature = initial_temp
    
    while temperature > min_temp:
        for _ in range(iterations_per_temp):
            # Pick two different pools
            pool1_idx, pool2_idx = random.sample(range(num_pools), 2)
            
            if not pools[pool1_idx] or not pools[pool2_idx]:
                continue
            
            # Pick random players from each pool
            player1_idx = random.randint(0, len(pools[pool1_idx]) - 1)
            player2_idx = random.randint(0, len(pools[pool2_idx]) - 1)
            
            player1 = pools[pool1_idx][player1_idx]
            player2 = pools[pool2_idx][player2_idx]
            
            # Check if swap would violate 0-rated constraint
            # Only matters if one is 0-rated and the other isn't
            p1_is_zero = player1[1] == 0.0
            p2_is_zero = player2[1] == 0.0
            
            if p1_is_zero != p2_is_zero:
                # Check if the pool receiving the 0-rated player would exceed limit
                if p1_is_zero:
                    # Player 1 (0-rated) going to pool 2
                    if _count_zero_rated(pools[pool2_idx]) >= max_zeros_per_pool:
                        continue  # Skip this swap - would violate constraint
                else:
                    # Player 2 (0-rated) going to pool 1
                    if _count_zero_rated(pools[pool1_idx]) >= max_zeros_per_pool:
                        continue  # Skip this swap - would violate constraint
            
            # Swap players
            pools[pool1_idx][player1_idx], pools[pool2_idx][player2_idx] = \
                pools[pool2_idx][player2_idx], pools[pool1_idx][player1_idx]
            
            new_variance = _calculate_pool_variance(pools)
            
            # Accept or reject the swap
            delta = new_variance - current_variance
            
            if delta < 0 or random.random() < math.exp(-delta / temperature):
                # Accept the swap
                current_variance = new_variance
                
                if new_variance < best_variance:
                    best_variance = new_variance
                    best_pools = [pool[:] for pool in pools]
            else:
                # Reject - swap back
                pools[pool1_idx][player1_idx], pools[pool2_idx][player2_idx] = \
                    pools[pool2_idx][player2_idx], pools[pool1_idx][player1_idx]
        
        temperature *= cooling_rate
    
    # Sort each pool by rating (descending) for cleaner display
    for pool in best_pools:
        pool.sort(key=lambda x: x[1], reverse=True)
    
    return best_pools


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
            st.dataframe(pool_df, width="stretch", hide_index=True, height=len(pool) * 35 + 38)
