"""DDL for revision 0001_initial, written out as SQL so every STRICT table, CHECK and
trigger is exactly as DATABASE.md section 3 specifies. Migrations import this module's
constants for 0001 only; later revisions write their own changes (DATABASE 9.1)."""

PII_TYPES = (
    "EMAIL", "PHONE", "AADHAAR", "PAN", "IFSC", "CARD", "IP_ADDRESS", "GOV_ID",
    "PERSON", "LOCATION", "ADDRESS", "ORG", "DATE", "AGE", "GENDER",
)  # fmt: skip
ACTIONS = ("keep", "generalize", "mask", "pseudonymize", "redact")
SCAN_STATUSES = ("queued", "running", "needs_review", "done", "failed")
RISK_LEVELS = ("LOW", "MEDIUM", "HIGH", "DIRECT")
ROLES = ("user", "admin")
FORMATS = ("txt", "md", "pdf", "docx", "csv")
FILE_KINDS = ("original", "cleaned")
REASONS = ("utility", "override", "review", "risk", "business number")
AUDIT_EVENTS = (
    "scan_completed", "review", "reidentify", "reidentify_denied", "rules_changed",
    "beliefs_reset", "retention", "user_created", "user_disabled", "anchor_saved",
)  # fmt: skip


def _in(values: tuple[str, ...]) -> str:
    return "(" + ",".join(f"'{v}'" for v in values) + ")"


TABLES = [
    f"""CREATE TABLE users (
  id INTEGER PRIMARY KEY,
  email TEXT NOT NULL UNIQUE COLLATE NOCASE
    CHECK (length(email) BETWEEN 3 AND 254 AND instr(email, '@') > 1),
  password_hash TEXT NOT NULL CHECK (length(password_hash) = 60),
  role TEXT NOT NULL DEFAULT 'user' CHECK (role IN {_in(ROLES)}),
  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
  created_at TEXT NOT NULL
) STRICT""",
    """CREATE TABLE sessions (
  id_hash BLOB PRIMARY KEY CHECK (length(id_hash) = 32),
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
) STRICT""",
    f"""CREATE TABLE scans (
  id TEXT PRIMARY KEY CHECK (length(id) = 36),
  owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  filename TEXT NOT NULL CHECK (length(filename) BETWEEN 1 AND 255),
  format TEXT NOT NULL CHECK (format IN {_in(FORMATS)}),
  status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN {_in(SCAN_STATUSES)}),
  step INTEGER NOT NULL DEFAULT 0 CHECK (step BETWEEN 0 AND 5),
  round INTEGER NOT NULL DEFAULT 1 CHECK (round BETWEEN 1 AND 3),
  risk_level TEXT CHECK (risk_level IN {_in(RISK_LEVELS)}),
  est_matches REAL CHECK (est_matches >= 0),
  risk_clues TEXT CHECK (json_valid(risk_clues)),
  unresolved_leaks INTEGER NOT NULL DEFAULT 0 CHECK (unresolved_leaks >= 0),
  model_version TEXT,
  error_code TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  finished_at TEXT,
  expires_at TEXT NOT NULL,
  CHECK (status <> 'done' OR (risk_level IS NOT NULL AND est_matches IS NOT NULL
         AND risk_clues IS NOT NULL AND finished_at IS NOT NULL)),
  CHECK (status <> 'failed' OR (error_code IS NOT NULL AND finished_at IS NOT NULL)),
  CHECK (status NOT IN ('queued', 'running', 'needs_review') OR finished_at IS NULL),
  CHECK (expires_at > created_at)
) STRICT""",
    f"""CREATE TABLE scan_files (
  scan_id TEXT NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK (kind IN {_in(FILE_KINDS)}),
  content_type TEXT NOT NULL,
  size_bytes INTEGER NOT NULL CHECK (size_bytes BETWEEN 0 AND 10485760),
  key_id TEXT NOT NULL,
  nonce BLOB NOT NULL CHECK (length(nonce) = 12),
  created_at TEXT NOT NULL,
  PRIMARY KEY (scan_id, kind)
) STRICT""",
    """CREATE TABLE tokens (
  token TEXT PRIMARY KEY
    CHECK (token GLOB '[A-Z]*_[0-9a-f]*' AND length(token) BETWEEN 8 AND 80),
  full_mac TEXT NOT NULL CHECK (length(full_mac) = 64),
  key_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (full_mac, key_id)
) STRICT""",
    f"""CREATE TABLE decisions (
  scan_id TEXT NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
  idx INTEGER NOT NULL CHECK (idx >= 0),
  round INTEGER NOT NULL CHECK (round BETWEEN 1 AND 3),
  start_offset INTEGER NOT NULL CHECK (start_offset >= 0),
  end_offset INTEGER NOT NULL,
  pii_type TEXT NOT NULL CHECK (pii_type IN {_in(PII_TYPES)}),
  score REAL NOT NULL CHECK (score BETWEEN 0 AND 1),
  sources TEXT NOT NULL CHECK (sources GLOB '[a-z]*'),
  action TEXT NOT NULL CHECK (action IN {_in(ACTIONS)}),
  reason TEXT NOT NULL CHECK (reason IN {_in(REASONS)}),
  token TEXT REFERENCES tokens(token) ON DELETE RESTRICT,
  PRIMARY KEY (scan_id, idx),
  CHECK (end_offset > start_offset),
  CHECK (action <> 'pseudonymize' OR token IS NOT NULL)
) STRICT""",
    f"""CREATE TABLE vault (
  token TEXT PRIMARY KEY REFERENCES tokens(token) ON DELETE RESTRICT,
  pii_type TEXT NOT NULL CHECK (pii_type IN {_in(PII_TYPES)}),
  key_id TEXT NOT NULL,
  nonce BLOB NOT NULL CHECK (length(nonce) = 12),
  ciphertext BLOB NOT NULL,
  created_at TEXT NOT NULL
) STRICT""",
    f"""CREATE TABLE rules (
  pii_type TEXT PRIMARY KEY CHECK (pii_type IN {_in(PII_TYPES)}),
  action TEXT NOT NULL CHECK (action IN {_in(ACTIONS)}),
  updated_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  updated_at TEXT NOT NULL
) STRICT""",
    f"""CREATE TABLE beliefs (
  pii_type TEXT PRIMARY KEY CHECK (pii_type IN {_in(PII_TYPES)}),
  sens_alpha REAL NOT NULL CHECK (sens_alpha > 0),
  sens_beta REAL NOT NULL CHECK (sens_beta > 0),
  prec_alpha REAL NOT NULL CHECK (prec_alpha > 0),
  prec_beta REAL NOT NULL CHECK (prec_beta > 0),
  updated_at TEXT NOT NULL
) STRICT""",
    f"""CREATE TABLE audit_log (
  seq INTEGER PRIMARY KEY CHECK (seq >= 0),
  ts TEXT NOT NULL,
  actor TEXT NOT NULL CHECK (actor = 'system' OR actor GLOB 'user:[0-9]*'),
  event TEXT NOT NULL CHECK (event IN {_in(AUDIT_EVENTS)}),
  payload TEXT NOT NULL CHECK (json_valid(payload)),
  payload_hash TEXT NOT NULL CHECK (length(payload_hash) = 64),
  prev_mac TEXT NOT NULL CHECK (length(prev_mac) = 64),
  kid TEXT NOT NULL,
  mac TEXT NOT NULL UNIQUE CHECK (length(mac) = 64)
) STRICT""",
]

INDEXES = [
    "CREATE INDEX scans_owner_created ON scans (owner_id, created_at DESC)",
    "CREATE INDEX scans_expires ON scans (expires_at)",
    "CREATE INDEX sessions_expires ON sessions (expires_at)",
    "CREATE INDEX sessions_user ON sessions (user_id)",
    "CREATE INDEX decisions_token ON decisions (token) WHERE token IS NOT NULL",
]

TRIGGERS = [
    """CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END""",
    """CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END""",
]

TABLE_NAMES = [
    "audit_log",
    "beliefs",
    "rules",
    "vault",
    "decisions",
    "tokens",
    "scan_files",
    "scans",
    "sessions",
    "users",
]  # fmt: skip  (drop order: children first)
