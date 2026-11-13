"""Persistencia SQLite local en modo WAL.

La base guarda trabajos de análisis, clips normalizados, ajustes, feature flags,
auditoría y evaluaciones. Un solo proceso escribe; las lecturas también pasan
por la misma conexión protegida con un lock reentrante.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import AnalysisResult, Transcript

DEFAULT_DB_PATH = Path("data/viralclip.db")

DEFAULT_FLAGS: tuple[tuple[str, bool, str], ...] = (
    ("export_srt", True, "Exportación de subtítulos en SRT/VTT"),
    ("sse_progress", True, "Progreso por Server-Sent Events (Fase 8)"),
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'done', 'error')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    platform TEXT NOT NULL,
    max_clips INTEGER NOT NULL,
    min_duration REAL NOT NULL,
    max_duration REAL NOT NULL,
    use_llm INTEGER NOT NULL,
    transcript_json TEXT NOT NULL,
    result_json TEXT,
    engine_name TEXT,
    engine_model TEXT,
    degraded INTEGER,
    error_code TEXT,
    error_message TEXT,
    request_id TEXT,
    progress INTEGER NOT NULL DEFAULT 0,
    stage TEXT,
    source_path TEXT,
    transcription_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs (created_at DESC);

CREATE TABLE IF NOT EXISTS clips (
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    clip_id TEXT NOT NULL,
    rank INTEGER NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    hook TEXT NOT NULL,
    caption_text TEXT NOT NULL,
    hashtags_json TEXT NOT NULL,
    score REAL NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (job_id, clip_id)
);

CREATE INDEX IF NOT EXISTS idx_clips_job_rank ON clips (job_id, rank);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feature_flags (
    name TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL,
    owner TEXT,
    expires_at TEXT,
    description TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    action TEXT NOT NULL,
    resource TEXT NOT NULL,
    resource_id TEXT,
    request_id TEXT,
    detail TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_log (created_at DESC);

CREATE TABLE IF NOT EXISTS evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    model TEXT,
    prompt_version TEXT,
    case_id TEXT,
    score REAL,
    passed INTEGER,
    detail_json TEXT
);

CREATE TABLE IF NOT EXISTS transcriptions (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'done', 'error')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    source_path TEXT NOT NULL,
    filename TEXT NOT NULL,
    model TEXT NOT NULL,
    device TEXT NOT NULL,
    language TEXT,
    duration REAL,
    progress INTEGER NOT NULL DEFAULT 0,
    stage TEXT,
    error_code TEXT,
    error_message TEXT,
    transcript_json TEXT,
    request_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_transcriptions_created_at
    ON transcriptions (created_at DESC);

CREATE TABLE IF NOT EXISTS renders (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    clip_id TEXT NOT NULL,
    transcription_id TEXT,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'done', 'error')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    stage TEXT,
    progress INTEGER NOT NULL DEFAULT 0,
    source_path TEXT NOT NULL,
    output_path TEXT,
    thumbnail_path TEXT,
    width INTEGER,
    height INTEGER,
    duration REAL,
    size_bytes INTEGER,
    error_code TEXT,
    error_message TEXT,
    request_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_renders_created_at ON renders (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_renders_job_clip ON renders (job_id, clip_id);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _iso(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat()
    return value


@dataclass(frozen=True)
class JobRecord:
    """Fila de ``jobs`` con su resultado ya validado cuando existe."""

    id: str
    status: str
    created_at: str
    updated_at: str
    platform: str
    max_clips: int
    min_duration: float
    max_duration: float
    use_llm: bool
    transcript_json: str
    result_json: str | None = None
    engine_name: str | None = None
    engine_model: str | None = None
    degraded: bool | None = None
    error_code: str | None = None
    error_message: str | None = None
    request_id: str | None = None
    progress: int = 0
    stage: str | None = None
    source_path: str | None = None
    transcription_id: str | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in {"done", "error"}


@dataclass(frozen=True)
class RenderRecord:
    """Fila de ``renders`` con las rutas y el estado del MP4 generado."""

    id: str
    job_id: str
    clip_id: str
    status: str
    created_at: str
    updated_at: str
    source_path: str
    transcription_id: str | None = None
    stage: str | None = None
    progress: int = 0
    output_path: str | None = None
    thumbnail_path: str | None = None
    width: int | None = None
    height: int | None = None
    duration: float | None = None
    size_bytes: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    request_id: str | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in {"done", "error"}


@dataclass(frozen=True)
class TranscriptionRecord:
    """Fila de ``transcriptions`` con su resultado normalizado."""

    id: str
    status: str
    created_at: str
    updated_at: str
    source_path: str
    filename: str
    model: str
    device: str
    language: str | None = None
    duration: float | None = None
    progress: int = 0
    stage: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    transcript_json: str | None = None
    request_id: str | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in {"done", "error"}


class Storage:
    """Acceso a SQLite con esquema inicializado y consultas parametrizadas."""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute("PRAGMA busy_timeout=5000")
        self._create_schema()
        self._migrate()
        self.seed_default_flags()

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------
    def _create_schema(self) -> None:
        with self._lock, self._connection:
            self._connection.executescript(_SCHEMA)

    def _migrate(self) -> None:
        """Añade columnas nuevas a bases creadas por versiones anteriores."""

        with self._lock, self._connection:
            columns = {
                row["name"]
                for row in self._connection.execute("PRAGMA table_info(jobs)")
            }
            if "progress" not in columns:
                self._connection.execute(
                    "ALTER TABLE jobs ADD COLUMN progress INTEGER NOT NULL DEFAULT 0"
                )
            if "stage" not in columns:
                self._connection.execute("ALTER TABLE jobs ADD COLUMN stage TEXT")
            if "source_path" not in columns:
                self._connection.execute(
                    "ALTER TABLE jobs ADD COLUMN source_path TEXT"
                )
            if "transcription_id" not in columns:
                self._connection.execute(
                    "ALTER TABLE jobs ADD COLUMN transcription_id TEXT"
                )

    def ping(self) -> bool:
        with self._lock:
            row = self._connection.execute("SELECT 1").fetchone()
        return bool(row and row[0] == 1)

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> Storage:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Jobs
    # ------------------------------------------------------------------
    def create_job(
        self,
        *,
        job_id: str,
        transcript_json: str,
        platform: str,
        max_clips: int,
        min_duration: float,
        max_duration: float,
        use_llm: bool,
        request_id: str | None = None,
        source_path: str | None = None,
        transcription_id: str | None = None,
    ) -> None:
        now = _now()
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO jobs (
                    id, status, created_at, updated_at, platform, max_clips,
                    min_duration, max_duration, use_llm, transcript_json,
                    request_id, progress, stage, source_path, transcription_id
                ) VALUES (?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'queued', ?, ?)
                """,
                (
                    job_id,
                    now,
                    now,
                    platform,
                    max_clips,
                    min_duration,
                    max_duration,
                    int(use_llm),
                    transcript_json,
                    request_id,
                    source_path,
                    transcription_id,
                ),
            )

    def mark_running(self, job_id: str) -> bool:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                UPDATE jobs
                   SET status = 'running', updated_at = ?, progress = 5,
                       stage = 'validando'
                 WHERE id = ?
                """,
                (_now(), job_id),
            )
        return cursor.rowcount > 0

    def update_progress(self, job_id: str, progress: int, stage: str) -> bool:
        """Actualiza el avance de un trabajo en curso."""

        clamped = max(0, min(100, int(progress)))
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                UPDATE jobs
                   SET progress = ?, stage = ?, updated_at = ?
                 WHERE id = ?
                """,
                (clamped, stage, _now(), job_id),
            )
        return cursor.rowcount > 0

    def complete_job(self, job_id: str, result: AnalysisResult) -> None:
        result_json = result.model_dump_json()
        now = _now()
        with self._lock, self._connection:
            self._connection.execute(
                """
                UPDATE jobs
                   SET status = 'done', updated_at = ?, result_json = ?,
                       engine_name = ?, engine_model = ?, degraded = ?,
                       error_code = NULL, error_message = NULL,
                       progress = 100, stage = 'done'
                 WHERE id = ?
                """,
                (
                    now,
                    result_json,
                    result.engine.name,
                    result.engine.model,
                    int(result.engine.degraded),
                    job_id,
                ),
            )
            self._connection.execute("DELETE FROM clips WHERE job_id = ?", (job_id,))
            for clip in result.clips:
                self._connection.execute(
                    """
                    INSERT INTO clips (
                        job_id, clip_id, rank, start_time, end_time, hook,
                        caption_text, hashtags_json, score, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        clip.id,
                        clip.rank,
                        clip.start_time,
                        clip.end_time,
                        clip.hook,
                        clip.caption_text,
                        json.dumps(clip.hashtags, ensure_ascii=False),
                        clip.score,
                        json.dumps(
                            clip.model_dump(mode="json"), ensure_ascii=False
                        ),
                    ),
                )

    def fail_job(self, job_id: str, code: str, message: str) -> bool:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                UPDATE jobs
                   SET status = 'error', updated_at = ?, error_code = ?,
                       error_message = ?, result_json = NULL,
                       progress = 100, stage = 'error'
                 WHERE id = ?
                """,
                (_now(), code, message, job_id),
            )
        return cursor.rowcount > 0

    def mark_interrupted_jobs(self) -> int:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                UPDATE jobs
                   SET status = 'error', updated_at = ?, error_code = 'VC-5001',
                       error_message = ?, progress = 100, stage = 'error'
                 WHERE status IN ('queued', 'running')
                """,
                (
                    _now(),
                    "El análisis se interrumpió al reiniciar la aplicación",
                ),
            )
        return cursor.rowcount

    def get_job(self, job_id: str) -> JobRecord | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return self._row_to_job(row) if row else None

    def list_jobs(
        self, *, limit: int = 20, offset: int = 0
    ) -> tuple[list[JobRecord], int]:
        with self._lock:
            total = int(
                self._connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            )
            rows = self._connection.execute(
                """
                SELECT * FROM jobs
                 ORDER BY created_at DESC, id DESC
                 LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [self._row_to_job(row) for row in rows], total

    def delete_job(self, job_id: str) -> bool:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "DELETE FROM jobs WHERE id = ?", (job_id,)
            )
        return cursor.rowcount > 0

    def result_for(self, job: JobRecord) -> AnalysisResult | None:
        if not job.result_json:
            return None
        return AnalysisResult.model_validate_json(job.result_json)

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> JobRecord:
        degraded = row["degraded"]
        return JobRecord(
            id=row["id"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            platform=row["platform"],
            max_clips=row["max_clips"],
            min_duration=row["min_duration"],
            max_duration=row["max_duration"],
            use_llm=bool(row["use_llm"]),
            transcript_json=row["transcript_json"],
            result_json=row["result_json"],
            engine_name=row["engine_name"],
            engine_model=row["engine_model"],
            degraded=None if degraded is None else bool(degraded),
            error_code=row["error_code"],
            error_message=row["error_message"],
            request_id=row["request_id"],
            progress=int(row["progress"] or 0),
            stage=row["stage"],
            source_path=row["source_path"],
            transcription_id=row["transcription_id"],
        )

    # ------------------------------------------------------------------
    # Ajustes
    # ------------------------------------------------------------------
    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        now = _now()
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value, now),
            )

    def all_settings(self) -> dict[str, str]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT key, value FROM settings ORDER BY key"
            ).fetchall()
        return {row["key"]: row["value"] for row in rows}

    # ------------------------------------------------------------------
    # Feature flags
    # ------------------------------------------------------------------
    def seed_default_flags(self) -> None:
        now = _now()
        with self._lock, self._connection:
            for name, enabled, description in DEFAULT_FLAGS:
                self._connection.execute(
                    """
                    INSERT OR IGNORE INTO feature_flags
                        (name, enabled, owner, expires_at, description, updated_at)
                    VALUES (?, ?, NULL, NULL, ?, ?)
                    """,
                    (name, int(enabled), description, now),
                )

    def list_flags(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM feature_flags ORDER BY name"
            ).fetchall()
        return [self._flag_from_row(row) for row in rows]

    def get_flag(self, name: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM feature_flags WHERE name = ?", (name,)
            ).fetchone()
        return self._flag_from_row(row) if row else None

    def set_flag(
        self,
        name: str,
        enabled: bool,
        *,
        owner: str | None = None,
        expires_at: datetime | str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        existing = self.get_flag(name)
        if description is None and existing:
            description = existing["description"]
        if owner is None and existing:
            owner = existing["owner"]
        if expires_at is None and existing:
            expires_at = existing["expires_at"]

        now = _now()
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO feature_flags
                    (name, enabled, owner, expires_at, description, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    enabled = excluded.enabled,
                    owner = excluded.owner,
                    expires_at = excluded.expires_at,
                    description = excluded.description,
                    updated_at = excluded.updated_at
                """,
                (name, int(enabled), owner, _iso(expires_at), description, now),
            )
        flag = self.get_flag(name)
        assert flag is not None
        return flag

    def active_flags(self) -> list[str]:
        now = _now()
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT name FROM feature_flags
                 WHERE enabled = 1
                   AND (expires_at IS NULL OR expires_at > ?)
                 ORDER BY name
                """,
                (now,),
            ).fetchall()
        return [row["name"] for row in rows]

    @staticmethod
    def _flag_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "name": row["name"],
            "enabled": bool(row["enabled"]),
            "owner": row["owner"],
            "expires_at": row["expires_at"],
            "description": row["description"],
        }

    # ------------------------------------------------------------------
    # Auditoría y evaluaciones
    # ------------------------------------------------------------------
    def audit(
        self,
        *,
        action: str,
        resource: str,
        resource_id: str | None = None,
        request_id: str | None = None,
        detail: str | None = None,
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO audit_log
                    (created_at, action, resource, resource_id, request_id, detail)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (_now(), action, resource, resource_id, request_id, detail),
            )

    def list_audit(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM audit_log
                 ORDER BY created_at DESC, id DESC
                 LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Evaluaciones de calidad
    # ------------------------------------------------------------------
    def save_evaluation(
        self,
        *,
        case_id: str,
        score: float,
        passed: bool,
        model: str | None = None,
        prompt_version: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> int:
        """Guarda una evaluación y devuelve su id autoincremental."""

        detail_json = (
            json.dumps(detail, ensure_ascii=False, sort_keys=True)
            if detail is not None
            else None
        )
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO evaluations
                    (created_at, model, prompt_version, case_id, score, passed, detail_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _now(),
                    model,
                    prompt_version,
                    case_id,
                    float(score),
                    int(bool(passed)),
                    detail_json,
                ),
            )
        return int(cursor.lastrowid or 0)

    def list_evaluations(self, *, limit: int = 50) -> list[dict[str, Any]]:
        """Devuelve las evaluaciones más recientes con su detalle deserializado."""

        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM evaluations
                 ORDER BY created_at DESC, id DESC
                 LIMIT ?
                """,
                (limit,),
            ).fetchall()

        items: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            raw_detail = item.pop("detail_json", None)
            if raw_detail:
                try:
                    item["detail"] = json.loads(raw_detail)
                except (TypeError, ValueError):
                    item["detail"] = None
            else:
                item["detail"] = None
            item["passed"] = bool(item["passed"])
            items.append(item)
        return items

    # ------------------------------------------------------------------
    # Transcripciones
    # ------------------------------------------------------------------
    def create_transcription(
        self,
        *,
        transcription_id: str,
        source_path: str,
        filename: str,
        model: str,
        device: str,
        language: str | None = None,
        request_id: str | None = None,
    ) -> None:
        now = _now()
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO transcriptions (
                    id, status, created_at, updated_at, source_path, filename,
                    model, device, language, progress, stage, request_id
                ) VALUES (?, 'queued', ?, ?, ?, ?, ?, ?, ?, 0, 'queued', ?)
                """,
                (
                    transcription_id,
                    now,
                    now,
                    source_path,
                    filename,
                    model,
                    device,
                    language,
                    request_id,
                ),
            )

    def mark_transcription_running(self, transcription_id: str) -> bool:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                UPDATE transcriptions
                   SET status = 'running', updated_at = ?, progress = 5,
                       stage = 'extrayendo'
                 WHERE id = ?
                """,
                (_now(), transcription_id),
            )
        return cursor.rowcount > 0

    def update_transcription_progress(
        self, transcription_id: str, progress: int, stage: str
    ) -> bool:
        clamped = max(0, min(100, int(progress)))
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                UPDATE transcriptions
                   SET progress = ?, stage = ?, updated_at = ?
                 WHERE id = ?
                """,
                (clamped, stage, _now(), transcription_id),
            )
        return cursor.rowcount > 0

    def complete_transcription(
        self,
        transcription_id: str,
        transcript: Transcript,
        *,
        language: str | None = None,
        duration: float | None = None,
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                UPDATE transcriptions
                   SET status = 'done', updated_at = ?,
                       transcript_json = ?, language = ?, duration = ?,
                       error_code = NULL, error_message = NULL,
                       progress = 100, stage = 'done'
                 WHERE id = ?
                """,
                (
                    _now(),
                    transcript.model_dump_json(),
                    language or transcript.language,
                    duration if duration is not None else transcript.duration,
                    transcription_id,
                ),
            )

    def fail_transcription(
        self, transcription_id: str, code: str, message: str
    ) -> bool:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                UPDATE transcriptions
                   SET status = 'error', updated_at = ?, error_code = ?,
                       error_message = ?, transcript_json = NULL,
                       progress = 100, stage = 'error'
                 WHERE id = ?
                """,
                (_now(), code, message, transcription_id),
            )
        return cursor.rowcount > 0

    def mark_interrupted_transcriptions(self) -> int:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                UPDATE transcriptions
                   SET status = 'error', updated_at = ?,
                       error_code = 'VC-1104', error_message = ?,
                       progress = 100, stage = 'error'
                 WHERE status IN ('queued', 'running')
                """,
                (
                    _now(),
                    "La transcripción se interrumpió al reiniciar la aplicación",
                ),
            )
        return cursor.rowcount

    def get_transcription(self, transcription_id: str) -> TranscriptionRecord | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM transcriptions WHERE id = ?", (transcription_id,)
            ).fetchone()
        return self._row_to_transcription(row) if row else None

    def list_transcriptions(
        self, *, limit: int = 20, offset: int = 0
    ) -> tuple[list[TranscriptionRecord], int]:
        with self._lock:
            total = int(
                self._connection.execute(
                    "SELECT COUNT(*) FROM transcriptions"
                ).fetchone()[0]
            )
            rows = self._connection.execute(
                """
                SELECT * FROM transcriptions
                 ORDER BY created_at DESC, id DESC
                 LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [self._row_to_transcription(row) for row in rows], total

    def delete_transcription(self, transcription_id: str) -> bool:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "DELETE FROM transcriptions WHERE id = ?", (transcription_id,)
            )
        return cursor.rowcount > 0

    def transcript_for(self, record: TranscriptionRecord) -> Transcript | None:
        if not record.transcript_json:
            return None
        return Transcript.model_validate_json(record.transcript_json)

    @staticmethod
    def _row_to_transcription(row: sqlite3.Row) -> TranscriptionRecord:
        return TranscriptionRecord(
            id=row["id"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            source_path=row["source_path"],
            filename=row["filename"],
            model=row["model"],
            device=row["device"],
            language=row["language"],
            duration=row["duration"],
            progress=int(row["progress"] or 0),
            stage=row["stage"],
            error_code=row["error_code"],
            error_message=row["error_message"],
            transcript_json=row["transcript_json"],
            request_id=row["request_id"],
        )

    # ------------------------------------------------------------------
    # Renderizados
    # ------------------------------------------------------------------
    def create_render(
        self,
        *,
        render_id: str,
        job_id: str,
        clip_id: str,
        source_path: str,
        transcription_id: str | None = None,
        request_id: str | None = None,
    ) -> None:
        now = _now()
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO renders (
                    id, job_id, clip_id, transcription_id, status,
                    created_at, updated_at, stage, progress, source_path,
                    request_id
                ) VALUES (?, ?, ?, ?, 'queued', ?, ?, 'queued', 0, ?, ?)
                """,
                (
                    render_id,
                    job_id,
                    clip_id,
                    transcription_id,
                    now,
                    now,
                    source_path,
                    request_id,
                ),
            )

    def mark_render_running(self, render_id: str) -> bool:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                UPDATE renders
                   SET status = 'running', updated_at = ?, progress = 5,
                       stage = 'validando'
                 WHERE id = ?
                """,
                (_now(), render_id),
            )
        return cursor.rowcount > 0

    def update_render_progress(
        self, render_id: str, progress: int, stage: str
    ) -> bool:
        clamped = max(0, min(100, int(progress)))
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                UPDATE renders
                   SET progress = ?, stage = ?, updated_at = ?
                 WHERE id = ?
                """,
                (clamped, stage, _now(), render_id),
            )
        return cursor.rowcount > 0

    def complete_render(
        self,
        render_id: str,
        *,
        output_path: str,
        thumbnail_path: str | None,
        width: int,
        height: int,
        duration: float,
        size_bytes: int,
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                UPDATE renders
                   SET status = 'done', updated_at = ?, stage = 'done',
                       progress = 100, output_path = ?, thumbnail_path = ?,
                       width = ?, height = ?, duration = ?, size_bytes = ?,
                       error_code = NULL, error_message = NULL
                 WHERE id = ?
                """,
                (
                    _now(),
                    output_path,
                    thumbnail_path,
                    width,
                    height,
                    duration,
                    size_bytes,
                    render_id,
                ),
            )

    def fail_render(self, render_id: str, code: str, message: str) -> bool:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                UPDATE renders
                   SET status = 'error', updated_at = ?, error_code = ?,
                       error_message = ?, progress = 100, stage = 'error'
                 WHERE id = ?
                """,
                (_now(), code, message, render_id),
            )
        return cursor.rowcount > 0

    def mark_interrupted_renders(self) -> int:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                UPDATE renders
                   SET status = 'error', updated_at = ?,
                       error_code = 'VC-1203', error_message = ?,
                       progress = 100, stage = 'error'
                 WHERE status IN ('queued', 'running')
                """,
                (
                    _now(),
                    "El renderizado se interrumpió al reiniciar la aplicación",
                ),
            )
        return cursor.rowcount

    def get_render(self, render_id: str) -> RenderRecord | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM renders WHERE id = ?", (render_id,)
            ).fetchone()
        return self._row_to_render(row) if row else None

    def find_render(
        self, *, job_id: str, clip_id: str
    ) -> RenderRecord | None:
        """Devuelve el render más reciente de un clip."""

        with self._lock:
            row = self._connection.execute(
                """
                SELECT * FROM renders
                 WHERE job_id = ? AND clip_id = ?
                 ORDER BY created_at DESC, id DESC
                 LIMIT 1
                """,
                (job_id, clip_id),
            ).fetchone()
        return self._row_to_render(row) if row else None

    def find_active_render(
        self, *, job_id: str, clip_id: str
    ) -> RenderRecord | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT * FROM renders
                 WHERE job_id = ? AND clip_id = ?
                   AND status IN ('queued', 'running')
                 ORDER BY created_at DESC, id DESC
                 LIMIT 1
                """,
                (job_id, clip_id),
            ).fetchone()
        return self._row_to_render(row) if row else None

    def list_renders(
        self,
        *,
        job_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[RenderRecord], int]:
        where = " WHERE job_id = ?" if job_id else ""
        params: tuple[Any, ...] = (job_id,) if job_id else ()
        with self._lock:
            total = int(
                self._connection.execute(
                    f"SELECT COUNT(*) FROM renders{where}", params
                ).fetchone()[0]
            )
            rows = self._connection.execute(
                f"""
                SELECT * FROM renders{where}
                 ORDER BY created_at DESC, id DESC
                 LIMIT ? OFFSET ?
                """,
                (*params, limit, offset),
            ).fetchall()
        return [self._row_to_render(row) for row in rows], total

    def delete_render(self, render_id: str) -> bool:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "DELETE FROM renders WHERE id = ?", (render_id,)
            )
        return cursor.rowcount > 0

    @staticmethod
    def _row_to_render(row: sqlite3.Row) -> RenderRecord:
        return RenderRecord(
            id=row["id"],
            job_id=row["job_id"],
            clip_id=row["clip_id"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            source_path=row["source_path"],
            transcription_id=row["transcription_id"],
            stage=row["stage"],
            progress=int(row["progress"] or 0),
            output_path=row["output_path"],
            thumbnail_path=row["thumbnail_path"],
            width=row["width"],
            height=row["height"],
            duration=row["duration"],
            size_bytes=row["size_bytes"],
            error_code=row["error_code"],
            error_message=row["error_message"],
            request_id=row["request_id"],
        )
