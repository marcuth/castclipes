"""Estado em SQLite: o que já foi visto/publicado (evita reprocessar e controla a cota)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path


@dataclass(frozen=True)
class CrosspostJob:
    id: int
    source_id: str
    format: str
    network: str
    attempts: int
    payload: str


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
            CREATE TABLE IF NOT EXISTS crossposts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, source_id TEXT NOT NULL,
                format TEXT NOT NULL, start REAL NOT NULL, end REAL NOT NULL,
                network TEXT NOT NULL, status TEXT NOT NULL, due_at TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0, url TEXT, error TEXT,
                payload TEXT NOT NULL, updated_at TEXT NOT NULL,
                UNIQUE (source_id, format, start, end, network));
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

    # ---------- publicação cruzada ----------
    def enqueue_crosspost(
        self, source_id: str, fmt: str, start: float, end: float, network: str,
        due_at: datetime, payload: str,
    ) -> None:
        """Ignora se o mesmo corte já está (ou esteve) na fila daquela rede."""
        self._db.execute(
            "INSERT OR IGNORE INTO crossposts"
            "(source_id,format,start,end,network,status,due_at,payload,updated_at) "
            "VALUES(?,?,?,?,?,'pending',?,?,?)",
            (source_id, fmt, start, end, network, due_at.isoformat(), payload, self._now()),
        )
        self._db.commit()

    def due_crossposts(self, now: datetime) -> list[CrosspostJob]:
        rows = self._db.execute(
            "SELECT id,source_id,format,network,attempts,payload FROM crossposts "
            "WHERE status='pending' AND due_at <= ? ORDER BY due_at, id",
            (now.isoformat(),),
        ).fetchall()
        return [CrosspostJob(*row) for row in rows]

    def finish_crosspost(self, job_id: int, url: str) -> None:
        self._db.execute(
            "UPDATE crossposts SET status='done', url=?, error=NULL, updated_at=? WHERE id=?",
            (url, self._now(), job_id),
        )
        self._db.commit()

    def fail_crosspost(
        self, job_id: int, error: str, retry_at: datetime | None, attempts: int | None = None
    ) -> None:
        """`retry_at=None` desiste (status `failed`); senão reagenda."""
        self._db.execute(
            "UPDATE crossposts SET status=?, due_at=COALESCE(?, due_at), error=?, "
            "attempts=COALESCE(?, attempts), updated_at=? WHERE id=?",
            (
                "failed" if retry_at is None else "pending",
                retry_at.isoformat() if retry_at else None, error, attempts, self._now(), job_id,
            ),
        )
        self._db.commit()

    def crosspost_urls(self, source_id: str, fmt: str, start: float, end: float) -> dict[str, str]:
        rows = self._db.execute(
            "SELECT network,url FROM crossposts WHERE status='done' AND source_id=? AND format=? "
            "AND start=? AND end=?",
            (source_id, fmt, start, end),
        ).fetchall()
        return {network: url for network, url in rows if url}

    def close(self) -> None:
        self._db.close()
