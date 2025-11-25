from database import get_db_session, TournamentFSI, Tournament

with get_db_session() as session:
    doubles_fsi = session.query(TournamentFSI).join(Tournament).filter(Tournament.tournament_format == 'doubles').count()
    total_fsi = session.query(TournamentFSI).count()
    print(f"Total FSI records: {total_fsi}")
    print(f"Doubles FSI records: {doubles_fsi}")
    
    if doubles_fsi > 0:
        print("\nSample Doubles FSI:")
        sample = session.query(Tournament, TournamentFSI).join(TournamentFSI).filter(Tournament.tournament_format == 'doubles').first()
        print(f"Tournament: {sample.Tournament.event_name}, FSI: {sample.TournamentFSI.fsi}")
