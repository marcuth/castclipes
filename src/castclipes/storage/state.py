"""Estado em SQLite: o que já foi visto/publicado (evita reprocessar e controla a cota)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path


class StateStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS videos (
                id TEXT PRIMARY KEY, status TEXT NOT NULL, reason TEXT, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS clips (
                source_id TEXT NOT NULL, format TEXT NOT NULL, start REAL NOT NULL,
                end REAL NOT NULL, title TEXT, youtube_id TEXT, published_at TEXT,
                scheduled_for TEXT,
                PRIMARY KEY (source_id, format, start, end));
            """
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def seen(self, video_id: str) -> bool:
        row = self._db.execute("SELECT status FROM videos WHERE id=?", (video_id,)).fetchone()
        return row is not None and row[0] not in ("failed", "waiting")

    def mark(self, video_id: str, status: str, reason: str = "") -> None:
        self._db.execute(
            "INSERT INTO videos(id,status,reason,updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET status=excluded.status, reason=excluded.reason, "
            "updated_at=excluded.updated_at",
            (video_id, status, reason, self._now()),
        )
        self._db.commit()

    def mark_waiting(self, video_id: str, reason: str = "") -> None:
        """Marca como em espera sem alterar `updated_at` se já estava esperando."""
        self._db.execute(
            "INSERT INTO videos(id,status,reason,updated_at) VALUES(?, 'waiting', ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET status='waiting', reason=excluded.reason, "
            "updated_at=excluded.updated_at WHERE videos.status != 'waiting'",
            (video_id, reason, self._now()),
        )
        self._db.commit()

    def waiting_since(self, video_id: str) -> datetime | None:
        row = self._db.execute(
            "SELECT updated_at FROM videos WHERE id=? AND status='waiting'", (video_id,)
        ).fetchone()
        return datetime.fromisoformat(row[0]) if row else None

    def clip_done(self, source_id: str, fmt: str, start: float, end: float) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM clips WHERE source_id=? AND format=? AND start=? AND end=?",
            (source_id, fmt, start, end),
        ).fetchone()
        return row is not None

    def record_clip(
        self, source_id: str, fmt: str, start: float, end: float, title: str,
        youtube_id: str | None, scheduled_for: datetime | None = None,
    ) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO clips"
            "(source_id,format,start,end,title,youtube_id,published_at,scheduled_for) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (source_id, fmt, start, end, title, youtube_id, self._now(),
             scheduled_for.isoformat() if scheduled_for else None),
        )
        self._db.commit()

    def scheduled_times(self) -> list[datetime]:
        """Horários já ocupados na fila (agendamentos de hoje em diante)."""
        since = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        rows = self._db.execute(
            "SELECT scheduled_for FROM clips WHERE scheduled_for IS NOT NULL AND scheduled_for >= ?",
            (since,),
        ).fetchall()
        return [datetime.fromisoformat(r[0]) for r in rows]

    def published_today(self) -> int:
        today = datetime.now(UTC).date().isoformat()
        row = self._db.execute(
            "SELECT COUNT(*) FROM clips WHERE youtube_id IS NOT NULL AND published_at >= ?",
            (today,),
        ).fetchone()
        return int(row[0])

    def close(self) -> None:
        self._db.close()
