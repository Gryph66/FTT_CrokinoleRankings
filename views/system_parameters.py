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
            "Parameter": ["Top N Teams", "Team Weight (High)", "Scaling Factor", "Min FSI", "Max FSI"],
            "Value": [
                f"{points_engine.doubles_top_n_for_fsi}",
                f"{getattr(points_engine, 'doubles_weight_high', 0.65):.2f}",
                f"{points_engine.fsi_scaling_factor:.1f}",
                f"{points_engine.fsi_min:.1f}",
                f"{points_engine.fsi_max:.1f}"
            ],
            "Description": [
                "Number of top teams used to calculate FSI",
                "Weight of higher-rated player in team strength (0.5=equal, 0.65=weighted)",
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
        **New Curve-Based Formula:**
        ```
        Points = (50 × FSI) ^ (1 - (Place - 1) / (FieldSize - 1))
        ```
        
        **Key Properties:**
        - **Winner (Place 1)**: Always gets `50 × FSI` points.
        - **Last Place**: Always gets `1` point (floor).
        - **Curve**: Points decay exponentially based on field size.
        
        **Example (FSI=1.2, Field Size=32):**
        - **Winner (1st)**: (50 × 1.2)¹ = **60 points**
        - **Middle (16th)**: (50 × 1.2)^(1 - 15/31) ≈ 60^0.516 ≈ **8.3 points**
        - **Last (32nd)**: (50 × 1.2)⁰ = **1 point**
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
    
    # === FSI VS POINTS MATRIX ===
    st.subheader("📊 FSI vs Points Matrix")
    st.markdown("*Points awarded for different placements across a range of Field Strength Indices (FSI).*")
    
    col1, col2 = st.columns(2)
    
    # Helper to generate matrix
    def generate_matrix_df(field_size, placements):
        fsi_values = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5]
        placement_labels = {
            1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th", 
            6: "6th", 7: "7th", 8: "8th", 9: "9th", 10: "10th",
            15: "15th", 20: "20th", 30: "30th", 40: "40th", 
            50: "50th", 60: "60th", 70: "70th", 90: "90th", 100: "100th"
        }
        
        matrix_data = []
        for place in placements:
            if place > field_size:
                continue
                
            label = placement_labels.get(place, f"{place}th")
            if place == field_size:
                label = f"Last ({place}th)"
                
            row = {"Place": label}
            for fsi in fsi_values:
                # Formula: (50 * FSI) ^ (1 - (Place - 1) / (FieldSize - 1))
                first_points = 50.0 * fsi
                if first_points <= 0:
                    points = 0.0
                else:
                    exponent = (place - 1) / (field_size - 1)
                    points = first_points ** (1.0 - exponent)
                
                # Floor safeguard and rounding
                points = max(1.0, round(points, 1))
                
                row[f"{fsi:.1f}"] = points
            matrix_data.append(row)
            
        df = pd.DataFrame(matrix_data)
        return df.set_index("Place")

    # Styling function
    def color_scale(val):
        norm = min(1.0, max(0.0, val / 75.0))
        if norm > 0.5:
            r = int(255 * (1 - (norm - 0.5) * 2))
            g = 255
            b = 0
        else:
            r = 255
            g = int(255 * (norm * 2))
            b = 0
        alpha = 0.6
        r = int(r + (255 - r) * (1 - alpha))
        g = int(g + (255 - g) * (1 - alpha))
        b = int(b + (255 - b) * (1 - alpha))
        return f'background-color: rgb({r}, {g}, {b})'

    with col1:
        st.markdown("**Singles** (Field Size: 100)")
        singles_placements = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 20, 30, 40, 50, 60, 70, 90, 100]
        singles_df = generate_matrix_df(100, singles_placements)
        st.dataframe(singles_df.style.map(color_scale).format("{:.1f}"), height=700)

    with col2:
        st.markdown("**Doubles** (Field Size: 50)")
        doubles_placements = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 20, 30, 40, 50]
        doubles_df = generate_matrix_df(50, doubles_placements)
        st.dataframe(doubles_df.style.map(color_scale).format("{:.1f}"), height=700)
    
    st.divider()
    
    # === NOTES ===
    st.info("""
    **📝 Notes:**
    - These parameters are loaded from the active `system_parameters` and `points_parameters` records in the database
    - Changes to parameters require a full recalculation to take effect
    - FSI and Points calculations use the same parameters for both singles and doubles where marked as "shared"
    """)
