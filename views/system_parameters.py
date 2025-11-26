import streamlit as st
import pandas as pd

def render():
    """Render the System Parameters summary page."""
    st.header("⚙️ System Parameters")
    st.markdown("""
    This page shows all active system parameters used for ratings calculation and points allocation.
    These parameters control how player ratings are calculated and how tournament points are awarded.
    """)
    
    # Get parameters from session state
    # Admin site uses: ranking_engine and points_engine
    # Public site uses: engine (TTTRankingEngine) and points_engine (PointsEngineDB)
    
    # Get TrueSkill parameters
    if 'ranking_engine' in st.session_state and st.session_state.ranking_engine:
        # Admin site
        ranking_engine = st.session_state.ranking_engine
        mu = ranking_engine.mu
        sigma = ranking_engine.sigma
        beta = ranking_engine.beta
        gamma = ranking_engine.gamma
        draw_probability = ranking_engine.draw_probability
    elif 'engine' in st.session_state and st.session_state.engine:
        # Public site
        engine = st.session_state.engine
        mu = engine.mu
        sigma = engine.sigma
        beta = engine.beta
        gamma = engine.gamma
        draw_probability = getattr(engine, 'draw_probability', 0.0)  # Default to 0.0 for crokinole
    else:
        st.error("Rating engine not initialized. Please load data first.")
        return
    
    # Get Points/FSI parameters
    if 'points_engine' not in st.session_state or not st.session_state.points_engine:
        st.error("Points engine not initialized. Please load data first.")
        return
    
    points_engine = st.session_state.points_engine
    
    st.divider()
    
    # === RATING SYSTEM PARAMETERS ===
    st.subheader("🎯 TrueSkill Through Time (TTT) Rating Parameters")
    st.markdown("*Controls how player skill ratings are calculated and updated after each tournament*")
    
    rating_params = {
        "Parameter": ["Initial μ (Mu)", "Initial σ (Sigma)", "β (Beta)", "γ (Gamma)", "Draw Probability"],
        "Value": [
            f"{mu:.3f}",
            f"{sigma:.3f}",
            f"{beta:.3f}",
            f"{gamma:.3f}",
            f"{draw_probability:.3f}"
        ],
        "Description": [
            "Starting skill rating for new players (mean)",
            "Starting uncertainty for new players (standard deviation)",
            "Skill difference that gives 76% win probability",
            "Dynamics factor - controls how much σ increases over time between events",
            "Probability of a draw occurring (0.0 = no draws in crokinole)"
        ]
    }
    
    st.dataframe(
        pd.DataFrame(rating_params),
        width="stretch",
        hide_index=True,
        column_config={
            "Parameter": st.column_config.TextColumn("Parameter", width="medium"),
            "Value": st.column_config.TextColumn("Value", width="small"),
            "Description": st.column_config.TextColumn("Description", width="large")
        }
    )
    
    st.divider()
    
    # === FSI PARAMETERS ===
    st.subheader("📊 Field Strength Index (FSI) Parameters")
    st.markdown("*Controls how tournament field strength is measured*")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Singles FSI**")
        singles_fsi_params = {
            "Parameter": ["Top N Players", "Scaling Factor", "Min FSI", "Max FSI"],
            "Value": [
                f"{points_engine.top_n_for_fsi}",
                f"{points_engine.fsi_scaling_factor:.1f}",
                f"{points_engine.fsi_min:.1f}",
                f"{points_engine.fsi_max:.1f}"
            ],
            "Description": [
                "Number of top players used to calculate FSI",
                "Divisor to normalize average rating to FSI range",
                "Minimum FSI value (floor)",
                "Maximum FSI value (ceiling)"
            ]
        }
        st.dataframe(
            pd.DataFrame(singles_fsi_params),
            width="stretch",
            hide_index=True,
            height=180
        )
    
    with col2:
        st.markdown("**Doubles FSI**")
        doubles_fsi_params = {
            "Parameter": ["Top N Teams", "Scaling Factor", "Min FSI", "Max FSI"],
            "Value": [
                f"{points_engine.doubles_top_n_for_fsi}",
                f"{points_engine.fsi_scaling_factor:.1f}",
                f"{points_engine.fsi_min:.1f}",
                f"{points_engine.fsi_max:.1f}"
            ],
            "Description": [
                "Number of top teams used to calculate FSI",
                "Divisor to normalize average rating to FSI range (shared)",
                "Minimum FSI value (floor, shared)",
                "Maximum FSI value (ceiling, shared)"
            ]
        }
        st.dataframe(
            pd.DataFrame(doubles_fsi_params),
            width="stretch",
            hide_index=True,
            height=180
        )
    
    st.divider()
    
    # === POINTS PARAMETERS ===
    st.subheader("🏆 Field-Weighted Points Parameters")
    st.markdown("*Controls how tournament points are calculated and awarded*")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Singles Points**")
        singles_points_params = {
            "Parameter": ["Alpha (α)", "Bonus Scale", "Top Tier Base", "Normal Tier Base", "Low Tier Base", "Best Events"],
            "Value": [
                f"{points_engine.alpha:.2f}",
                f"{getattr(points_engine, 'bonus_scale', 0.0):.1f}",
                f"{getattr(points_engine, 'top_tier_base_points', 50):.0f}",
                f"{getattr(points_engine, 'normal_tier_base_points', 50):.0f}",
                f"{getattr(points_engine, 'low_tier_base_points', 50):.0f}",
                f"{getattr(points_engine, 'best_tournaments_per_season', 5)}"
            ],
            "Description": [
                "Exponential decay rate for placement-based points (higher = more top-heavy)",
                "Multiplier for overperformance bonus (expected_rank - actual_place)",
                f"Base points for top tier tournaments (FSI ≥ {getattr(points_engine, 'top_tier_fsi_threshold', 1.35):.2f})",
                f"Base points for normal tier tournaments",
                f"Base points for low tier tournaments (FSI ≤ {getattr(points_engine, 'low_tier_fsi_threshold', 1.0):.2f})",
                "Number of best events counted per season"
            ]
        }
        st.dataframe(
            pd.DataFrame(singles_points_params),
            width="stretch",
            hide_index=True,
            height=240
        )
    
    with col2:
        st.markdown("**Doubles Points**")
        doubles_points_params = {
            "Parameter": ["Alpha (α)", "Bonus Scale", "Top Tier Base", "Normal Tier Base", "Low Tier Base", "Best Events"],
            "Value": [
                f"{points_engine.doubles_alpha:.2f}",
                f"{getattr(points_engine, 'bonus_scale', 0.0):.1f} (shared)",
                f"{getattr(points_engine, 'top_tier_base_points', 50):.0f} (shared)",
                f"{getattr(points_engine, 'normal_tier_base_points', 50):.0f} (shared)",
                f"{getattr(points_engine, 'low_tier_base_points', 50):.0f} (shared)",
                f"{getattr(points_engine, 'best_tournaments_per_season', 5)} (shared)"
            ],
            "Description": [
                "Exponential decay rate for placement-based points (higher = more top-heavy)",
                "Multiplier for overperformance bonus (expected_rank - actual_place)",
                f"Base points for top tier tournaments (FSI ≥ {getattr(points_engine, 'top_tier_fsi_threshold', 1.35):.2f})",
                f"Base points for normal tier tournaments",
                f"Base points for low tier tournaments (FSI ≤ {getattr(points_engine, 'low_tier_fsi_threshold', 1.0):.2f})",
                "Number of best events counted per season"
            ]
        }
        st.dataframe(
            pd.DataFrame(doubles_points_params),
            width="stretch",
            hide_index=True,
            height=240
        )
    
    st.divider()
    
    # === CALCULATION FORMULAS ===
    st.subheader("📐 Calculation Formulas")
    
    with st.expander("**FSI Calculation**", expanded=False):
        st.markdown("""
        ```
        1. Get top N players/teams by rating (μ)
        2. Calculate average rating: avg_top_μ = sum(top_N_ratings) / N
        3. Calculate raw FSI: fsi_raw = avg_top_μ / scaling_factor
        4. Clamp to range: fsi = max(fsi_min, min(fsi_raw, fsi_max))
        ```
        
        **Example (Singles with Top 20, Scaling 6.0):**
        - Top 20 average rating: 30.0
        - Raw FSI: 30.0 / 6.0 = 5.0
        - Clamped FSI: max(0.5, min(5.0, 1.5)) = **1.5**
        """)
    
    with st.expander("**Points Calculation**", expanded=False):
        st.markdown("""
        ```
        1. Base Points: base_points × fsi
        2. Overperformance Bonus: min(alpha × (expected_rank - actual_place), max_bonus_points) × fsi
        3. Total Points: base_points + bonus_points
        ```
        
        **Example (Singles, FSI=1.2, Expected Rank=10, Actual Place=5):**
        - Base: 100 × 1.2 = 120 points
        - Bonus: min(10 × (10-5), 200) × 1.2 = min(50, 200) × 1.2 = 60 points
        - Total: 120 + 60 = **180 points**
        """)
    
    with st.expander("**Conservative Rating**", expanded=False):
        st.markdown("""
        ```
        Conservative Rating = μ - 3σ
        ```
        
        This represents a 99.7% confidence lower bound on a player's true skill.
        - **μ (mu)**: Estimated skill level
        - **σ (sigma)**: Uncertainty in the estimate
        - **3σ**: Three standard deviations (99.7% confidence interval)
        
        **Example:**
        - μ = 25.0, σ = 2.5
        - Conservative Rating = 25.0 - (3 × 2.5) = **17.5**
        """)
    
    st.divider()
    
    # === NOTES ===
    st.info("""
    **📝 Notes:**
    - These parameters are loaded from the active `system_parameters` and `points_parameters` records in the database
    - Changes to parameters require a full recalculation to take effect
    - FSI and Points calculations use the same parameters for both singles and doubles where marked as "shared"
    """)
