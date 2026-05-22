from typing import Optional

from app.extensions import db
from app.domain.aggregates.charging_session import ChargingSession, SessionNotFound


class SessionRepository:
    def get(self, session_id: str) -> Optional[ChargingSession]:
        return db.session.get(ChargingSession, session_id)

    def get_or_raise(self, session_id: str) -> ChargingSession:
        session = self.get(session_id)
        if not session:
            raise SessionNotFound(session_id)
        return session

    def add(self, session: ChargingSession) -> None:
        db.session.add(session)

    def save(self) -> None:
        db.session.commit()

    def list_all(self) -> list[ChargingSession]:
        return ChargingSession.query.order_by(ChargingSession.created_at.desc()).all()
