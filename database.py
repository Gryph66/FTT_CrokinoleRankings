import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import pandas as pd
import json

# Use SQLite for public site (data will be loaded from JSON)
# Use absolute path based on this file's location for Streamlit Cloud compatibility
import pathlib
_DB_DIR = pathlib.Path(__file__).parent.resolve()
DATABASE_URL = f'sqlite:///{_DB_DIR}/public_data.db'

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False}  # Needed for SQLite
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
Base = declarative_base()

# Function to load JSON data into SQLite
def load_json_to_db():
    """Load exported JSON data into SQLite database."""
    import glob
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    # Load JSON files and populate database
    # This will be called on startup
    pass

class Tournament(Base):
    __tablename__ = 'tournaments'
    
    id = Column(Integer, primary_key=True, index=True)
    season = Column(String, index=True)
    event_name = Column(String, index=True)
    tier = Column(String)
    tournament_group = Column(String, index=True, nullable=True)
    tournament_format = Column(String, default='singles', index=True)
    num_players = Column(Integer)
    avg_rating_before = Column(Float)
    avg_rating_after = Column(Float)
    tournament_date = Column(DateTime, nullable=True)
    sequence_order = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    results = relationship("TournamentResult", back_populates="tournament", cascade="all, delete-orphan")
    rating_changes = relationship("RatingChange", back_populates="tournament", cascade="all, delete-orphan")

class Player(Base):
    __tablename__ = 'players'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    current_rating_mu = Column(Float, default=0.0)  # TTT default (was 25.0)
    current_rating_sigma = Column(Float, default=1.667)  # TTT default (was 8.333)
    tournaments_played = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Multi-model rating storage (for Singles Only, Singles+Doubles, Doubles Only)
    current_rating_mu_singles = Column(Float, nullable=True)      # Singles-only model
    current_rating_sigma_singles = Column(Float, nullable=True)
    current_rating_mu_combined = Column(Float, nullable=True)     # Singles + Doubles model
    current_rating_sigma_combined = Column(Float, nullable=True)
    current_rating_mu_doubles = Column(Float, nullable=True)      # Doubles-only model
    current_rating_sigma_doubles = Column(Float, nullable=True)
    
    # Tournament counts per format
    singles_tournaments_played = Column(Integer, default=0)
    doubles_tournaments_played = Column(Integer, default=0)
    
    results = relationship("TournamentResult", back_populates="player")
    rating_history = relationship("RatingChange", back_populates="player")

class TournamentResult(Base):
    __tablename__ = 'tournament_results'
    
    id = Column(Integer, primary_key=True, index=True)
    tournament_id = Column(Integer, ForeignKey('tournaments.id'))
    player_id = Column(Integer, ForeignKey('players.id'))
    place = Column(Integer)
    
    # Rating snapshot for doubles tournaments (where TrueSkill doesn't update ratings)
    before_mu = Column(Float, nullable=True)
    before_sigma = Column(Float, nullable=True)
    
    # Team metadata for doubles tournaments
    team_key = Column(String, nullable=True, index=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    tournament = relationship("Tournament", back_populates="results")
    player = relationship("Player", back_populates="results")

class RatingChange(Base):
    __tablename__ = 'rating_changes'
    
    id = Column(Integer, primary_key=True, index=True)
    tournament_id = Column(Integer, ForeignKey('tournaments.id'))
    player_id = Column(Integer, ForeignKey('players.id'))
    place = Column(Integer)
    # Smoothed values (from TTT backward-forward smoothing)
    before_mu = Column(Float)
    before_sigma = Column(Float)
    after_mu = Column(Float)
    after_sigma = Column(Float)
    mu_change = Column(Float)
    sigma_change = Column(Float)
    conservative_rating_before = Column(Float)
    conservative_rating_after = Column(Float)
    # Forward-only values (no future information used)
    before_mu_forward = Column(Float, nullable=True)
    before_sigma_forward = Column(Float, nullable=True)
    after_mu_forward = Column(Float, nullable=True)
    after_sigma_forward = Column(Float, nullable=True)
    conservative_rating_forward = Column(Float, nullable=True)
    # Smoothed forward value (EMA of before_mu_forward for stable FSI)
    before_mu_forward_smoothed = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Rating model this change belongs to: 'singles_only', 'singles_doubles', 'doubles_only'
    rating_model = Column(String, default='singles_only', index=True)
    
    tournament = relationship("Tournament", back_populates="rating_changes")
    player = relationship("Player", back_populates="rating_history")

class SystemParameters(Base):
    __tablename__ = 'system_parameters'
    
    id = Column(Integer, primary_key=True, index=True)
    mu = Column(Float, default=25.0)
    sigma = Column(Float, default=8.333)
    beta = Column(Float, default=4.166)
    tau = Column(Float, default=0.083)
    gamma = Column(Float, default=0.03)  # TTT skill drift parameter
    draw_probability = Column(Float, default=0.0)
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    description = Column(Text, nullable=True)
    
    # Z-Score Baseline Parameters (Static Snapshot)
    z_score_baseline_mean = Column(Float, default=0.0)
    z_score_baseline_std = Column(Float, default=1.0)
    
    # Rating Model Selection (for FSI/FWP calculations)
    # Options: 'singles_only', 'singles_doubles', 'doubles_only'
    rating_mode = Column(String, default='singles_only')
    
    # Doubles contribution weight: how much each partner contributes to team skill
    # 0.5 = equal contribution, 0.6 = stronger player contributes 60%
    doubles_contribution_weight = Column(Float, default=0.5)
    
    # FSI Rating Smoothing: Exponential Moving Average factor for forward ratings
    # 0.0 = no smoothing (raw forward value), higher values = more smoothing
    fsi_rating_smoothing_factor = Column(Float, default=2.0)

class PointsParameters(Base):
    __tablename__ = 'points_parameters'
    
    id = Column(Integer, primary_key=True, index=True)
    max_points = Column(Float, default=50.0)  # Legacy - kept for backward compatibility
    alpha = Column(Float, default=1.4)
    bonus_scale = Column(Float, default=0.0)
    fsi_min = Column(Float, default=0.8)
    fsi_max = Column(Float, default=1.6)
    fsi_scaling_factor = Column(Float, default=6.0) # New parameter for TTT scaling
    top_n_for_fsi = Column(Integer, default=20)
    best_tournaments_per_season = Column(Integer, default=5)
    
    # Tiered base points system
    top_tier_fsi_threshold = Column(Float, default=1.35)
    top_tier_base_points = Column(Float, default=60.0)
    normal_tier_base_points = Column(Float, default=50.0)
    low_tier_base_points = Column(Float, default=40.0)
    low_tier_fsi_threshold = Column(Float, default=1.0)
    
    # Doubles-specific parameters
    doubles_top_n_for_fsi = Column(Integer, default=8)
    doubles_alpha = Column(Float, default=2.0)
    doubles_weight_high = Column(Float, default=0.65)
    
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    description = Column(Text, nullable=True)

class TournamentFSI(Base):
    __tablename__ = 'tournament_fsi'
    
    id = Column(Integer, primary_key=True, index=True)
    tournament_id = Column(Integer, ForeignKey('tournaments.id'), unique=True)
    season = Column(String, index=True)
    fsi = Column(Float)
    avg_top_mu = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    tournament = relationship("Tournament")

class SeasonEventPoints(Base):
    __tablename__ = 'season_event_points'
    
    id = Column(Integer, primary_key=True, index=True)
    tournament_id = Column(Integer, ForeignKey('tournaments.id'), index=True)
    player_id = Column(Integer, ForeignKey('players.id'), index=True)
    season = Column(String, index=True)
    place = Column(Integer)
    field_size = Column(Integer)
    pre_mu = Column(Float)
    pre_sigma = Column(Float)
    post_mu = Column(Float)
    post_sigma = Column(Float)
    display_rating = Column(Float)
    fsi = Column(Float)
    raw_points = Column(Float)
    base_points = Column(Float)
    expected_rank = Column(Integer)
    overperformance = Column(Float)
    bonus_points = Column(Float)
    total_points = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    tournament = relationship("Tournament")
    player = relationship("Player")

class SeasonLeaderboard(Base):
    __tablename__ = 'season_leaderboards'
    
    id = Column(Integer, primary_key=True, index=True)
    season = Column(String, index=True)
    player_id = Column(Integer, ForeignKey('players.id'), index=True)
    total_points = Column(Float)
    events_counted = Column(Integer)
    top_five_event_ids = Column(JSON, nullable=True)
    final_display_rating = Column(Float)
    rank = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    player = relationship("Player")

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_db_session():
    return SessionLocal()
