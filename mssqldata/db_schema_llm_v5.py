import json
import logging
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pyodbc


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

DRIVER = "{ODBC Driver 17 for SQL Server}"
SERVER = "cw-002918"              # update if needed
DATABASE = "arif_recruitment"     # update if needed
TRUSTED_CONNECTION = "yes"

OUTPUT_DIR = Path("./output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

LOG_LEVEL = logging.INFO

# Optional table filter. Keep None for all user tables.
TARGET_TABLES: Optional[set[str]] = None

# Profiling / sampling
MAX_SAMPLE_VALUES = 5
MAX_TEXT_SAMPLE_LENGTH = 180
TEXT_SAMPLE_SCAN_LIMIT = 1500
CATEGORICAL_TOP_SCAN_LIMIT = 1000

# Pattern profiling
PROFILE_RANDOM_POOL_SIZE = 1200
REPRESENTATIVE_EXAMPLE_COUNT = 5
ANOMALY_EXAMPLE_COUNT = 5
DOMINANT_PATTERN_MIN_RATIO = 0.40

# Chunking
MAX_TABLES_PER_CHUNK = 8
MAX_RELATIONSHIPS_PER_CHUNK = 25

# Text cleaning heuristics
COMMON_EMPTY_STRINGS = {"", "-", "--", "---", ".", "..", "...", "n/a", "na", "null", "none", "unknown", "nil"}
MIN_ALNUM_RATIO = 0.35
VERY_SPECIAL_RATIO_THRESHOLD = 0.45


# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("generic_schema_extractor_v5")


# -----------------------------------------------------------------------------
# DB helpers
# -----------------------------------------------------------------------------

def open_db_connection() -> pyodbc.Connection:
    conn_str = (
        f"DRIVER={DRIVER};"
        f"SERVER={SERVER};"
        f"DATABASE={DATABASE};"
        f"Trusted_Connection={TRUSTED_CONNECTION};"
        "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str)


def quote_ident(name: str) -> str:
    return f"[{name.replace(']', ']]')}]"


def fetch_all_dicts(conn: pyodbc.Connection, sql: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
    cur = conn.cursor()
    cur.execute(sql, params or [])
    columns = [col[0] for col in cur.description]
    rows = cur.fetchall()
    return [{columns[i]: row[i] for i in range(len(columns))} for row in rows]


def fetch_scalar(conn: pyodbc.Connection, sql: str, params: Optional[List[Any]] = None) -> Any:
    cur = conn.cursor()
    cur.execute(sql, params or [])
    row = cur.fetchone()
    return row[0] if row else None


def to_json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool, list, dict)):
        return value
    return str(value)


# -----------------------------------------------------------------------------
# Text helpers
# -----------------------------------------------------------------------------

ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")
LETTER_RE = re.compile(r"[A-Za-z]")
ALNUM_RE = re.compile(r"[A-Za-z0-9]")
SPECIAL_RE = re.compile(r"[^A-Za-z0-9\s]")
WHITESPACE_RE = re.compile(r"\s+")


def normalize_space(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text).strip()


def safe_str(value: Any) -> str:
    return "" if value is None else normalize_space(str(value))


def contains_arabic(text: str) -> bool:
    return bool(ARABIC_RE.search(text or ""))


def has_english_letters(text: str) -> bool:
    return bool(LETTER_RE.search(text or ""))


def alnum_ratio(text: str) -> float:
    if not text:
        return 0.0
    return len(ALNUM_RE.findall(text)) / max(1, len(text))


def special_ratio(text: str) -> float:
    if not text:
        return 1.0
    return len(SPECIAL_RE.findall(text)) / max(1, len(text))


def looks_emptyish(text: str) -> bool:
    if text is None:
        return True
    t = normalize_space(str(text)).strip().lower()
    return t in COMMON_EMPTY_STRINGS or len(t) == 0


def looks_mostly_junk(text: str) -> bool:
    if not text:
        return True

    t = normalize_space(str(text))

    if looks_emptyish(t):
        return True
    if len(t) <= 1:
        return True
    if contains_arabic(t):
        return True
    if alnum_ratio(t) < MIN_ALNUM_RATIO:
        return True
    if special_ratio(t) > VERY_SPECIAL_RATIO_THRESHOLD:
        return True

    unique_chars = set(t)
    if len(t) >= 3 and len(unique_chars) <= 2:
        return True

    return False


def clean_example_text(text: str, max_len: int = MAX_TEXT_SAMPLE_LENGTH) -> str:
    t = normalize_space(str(text))
    if len(t) > max_len:
        t = t[:max_len].rstrip() + "..."
    return t


def random_sample_list(items: List[str], n: int) -> List[str]:
    if len(items) <= n:
        return items[:]
    return random.sample(items, n)


def choose_best_examples(values: List[str], max_values: int = MAX_SAMPLE_VALUES) -> List[str]:
    cleaned = []
    seen = set()

    for raw in values:
        if raw is None:
            continue
        text = clean_example_text(raw)
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        if looks_mostly_junk(text):
            continue
        cleaned.append(text)

    def score(val: str) -> Tuple[int, int, int]:
        english_score = 1 if has_english_letters(val) else 0
        length = len(val)
        if 5 <= length <= 60:
            length_score = 3
        elif 3 <= length <= 120:
            length_score = 2
        else:
            length_score = 1
        special_penalty = int(special_ratio(val) * 100)
        return (english_score, length_score, -special_penalty)

    cleaned.sort(key=score, reverse=True)
    return cleaned[:max_values]


# -----------------------------------------------------------------------------
# Pattern detection
# -----------------------------------------------------------------------------

def looks_like_integer(text: str) -> bool:
    return bool(re.fullmatch(r"\d+", text))


def looks_like_decimal(text: str) -> bool:
    return bool(re.fullmatch(r"\d+\.\d+", text))


def looks_like_signed_decimal(text: str) -> bool:
    return bool(re.fullmatch(r"-?\d+(\.\d+)?", text))


def looks_like_email(text: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", text))


def looks_like_phoneish(text: str) -> bool:
    cleaned = re.sub(r"[^\d+]", "", text)
    digits = re.sub(r"\D", "", cleaned)
    return 7 <= len(digits) <= 15


def char_shape(text: str) -> str:
    out = []
    for ch in text:
        if ch.isdigit():
            out.append("D")
        elif ch.isalpha():
            out.append("A")
        elif ch.isspace():
            out.append(" ")
        else:
            out.append(ch)
    shape = "".join(out)
    shape = re.sub(r"A{4,}", "A+", shape)
    shape = re.sub(r"D{4,}", "D+", shape)
    shape = re.sub(r"\s+", " ", shape)
    return shape[:60]


def detect_value_pattern(text: str) -> Dict[str, Any]:
    t = safe_str(text)

    if not t:
        return {"pattern": "EMPTY", "family": "empty", "description": "empty value"}

    if looks_like_email(t):
        return {
            "pattern": "EMAIL",
            "family": "email",
            "description": "email-like value"
        }

    if looks_like_integer(t):
        desc = f"digits length {len(t)}"
        prefix = t[:1] if t else ""
        return {
            "pattern": f"DIGITS_LEN_{len(t)}_PREFIX_{prefix}",
            "family": "integer_string",
            "description": desc
        }

    if looks_like_decimal(t) or looks_like_signed_decimal(t):
        try:
            value = float(t)
        except Exception:
            value = None

        bucket = None
        if value is not None:
            if 0 <= value <= 4:
                bucket = "RANGE_0_4"
            elif 0 <= value <= 5:
                bucket = "RANGE_0_5"
            elif 0 <= value <= 100:
                bucket = "RANGE_0_100"
            elif value > 100:
                bucket = "GT_100"
            elif value < 0:
                bucket = "LT_0"
            else:
                bucket = "OTHER"

        decimals = len(t.split(".")[1]) if "." in t else 0
        return {
            "pattern": f"DECIMAL_{bucket}_DP_{decimals}",
            "family": "decimal_string",
            "description": f"decimal value, bucket={bucket}, decimals={decimals}"
        }

    if looks_like_phoneish(t):
        digits = re.sub(r"\D", "", t)
        return {
            "pattern": f"PHONEISH_DIGITS_{len(digits)}",
            "family": "phoneish",
            "description": f"phone-like value with {len(digits)} digits"
        }

    shape = char_shape(t)
    length = len(t)

    if has_english_letters(t) and any(ch.isdigit() for ch in t):
        return {
            "pattern": f"ALNUM_LEN_{length}_SHAPE_{shape}",
            "family": "alphanumeric_code",
            "description": f"alphanumeric code, shape={shape}"
        }

    if has_english_letters(t):
        word_count = len(t.split())
        return {
            "pattern": f"TEXT_WORDS_{min(word_count, 10)}",
            "family": "text",
            "description": f"text value with about {word_count} words"
        }

    return {
        "pattern": f"OTHER_LEN_{length}_SHAPE_{shape}",
        "family": "other",
        "description": f"other structured value, shape={shape}"
    }


def build_pattern_profile(values: List[str]) -> Dict[str, Any]:
    cleaned = []
    for v in values:
        if looks_emptyish(v):
            continue
        if contains_arabic(v):
            continue
        if looks_mostly_junk(v):
            continue
        cleaned.append(clean_example_text(v, 200))

    if not cleaned:
        return {
            "dominant_pattern": None,
            "dominant_pattern_ratio": None,
            "pattern_summary": [],
            "representative_values": [],
            "anomaly_examples": [],
            "value_interpretation": "no usable sample values found"
        }

    classified = []
    for v in cleaned:
        pattern_info = detect_value_pattern(v)
        classified.append({
            "value": v,
            "pattern": pattern_info["pattern"],
            "family": pattern_info["family"],
            "description": pattern_info["description"]
        })

    pattern_counts = Counter(item["pattern"] for item in classified)
    total = len(classified)

    dominant_pattern, dominant_count = pattern_counts.most_common(1)[0]
    dominant_ratio = dominant_count / total if total else 0.0

    dominant_values = [x["value"] for x in classified if x["pattern"] == dominant_pattern]
    anomaly_values = [x["value"] for x in classified if x["pattern"] != dominant_pattern]

    pattern_summary = []
    for pattern, count in pattern_counts.most_common(10):
        example_item = next((x for x in classified if x["pattern"] == pattern), None)
        pattern_summary.append({
            "pattern": pattern,
            "count": count,
            "ratio": round(count / total, 4) if total else None,
            "description": example_item["description"] if example_item else None
        })

    interpretation = "mixed values"
    if dominant_ratio >= 0.8:
        interpretation = "very strong dominant format"
    elif dominant_ratio >= 0.6:
        interpretation = "strong dominant format"
    elif dominant_ratio >= 0.4:
        interpretation = "moderate dominant format"

    return {
        "dominant_pattern": dominant_pattern,
        "dominant_pattern_ratio": round(dominant_ratio, 4),
        "pattern_summary": pattern_summary,
        "representative_values": random_sample_list(list(dict.fromkeys(dominant_values)), REPRESENTATIVE_EXAMPLE_COUNT),
        "anomaly_examples": random_sample_list(list(dict.fromkeys(anomaly_values)), ANOMALY_EXAMPLE_COUNT),
        "value_interpretation": interpretation
    }


def infer_value_semantics_from_pattern(pattern_profile: Optional[Dict[str, Any]]) -> Optional[str]:
    if not pattern_profile:
        return None

    p = pattern_profile.get("dominant_pattern") or ""

    if p.startswith("DIGITS_LEN_"):
        return "structured_numeric_identifier"
    if p.startswith("DECIMAL_RANGE_0_4") or p.startswith("DECIMAL_RANGE_0_5"):
        return "score_like_value"
    if p.startswith("EMAIL"):
        return "email_like_value"
    if p.startswith("PHONEISH"):
        return "phone_like_value"
    if p.startswith("ALNUM_LEN_"):
        return "alphanumeric_code"
    if p.startswith("TEXT_WORDS_"):
        return "free_text"
    return "generic_text"


# -----------------------------------------------------------------------------
# Type helpers
# -----------------------------------------------------------------------------

def infer_is_textual_type(data_type: str) -> bool:
    dt = (data_type or "").lower()
    return any(x in dt for x in ["varchar", "nvarchar", "text", "ntext", "xml"])


def infer_is_numeric_type(data_type: str) -> bool:
    dt = (data_type or "").lower()
    return any(x in dt for x in ["int", "bigint", "smallint", "tinyint", "decimal", "numeric", "float", "real", "money"])


def infer_is_date_type(data_type: str) -> bool:
    dt = (data_type or "").lower()
    return any(x in dt for x in ["date", "datetime", "datetime2", "smalldatetime", "time"])


def infer_is_boolean_type(data_type: str) -> bool:
    return (data_type or "").lower() == "bit"


def should_run_pattern_analysis(data_type: str, distinct_count: Optional[int]) -> bool:
    if not infer_is_textual_type(data_type):
        return False
    if distinct_count is None:
        return True
    return distinct_count >= 20


# -----------------------------------------------------------------------------
# Metadata extraction
# -----------------------------------------------------------------------------

def get_all_user_tables(conn: pyodbc.Connection) -> List[Dict[str, Any]]:
    sql = """
    SELECT
        s.name AS schema_name,
        t.name AS table_name,
        t.object_id
    FROM sys.tables t
    JOIN sys.schemas s
        ON t.schema_id = s.schema_id
    WHERE t.is_ms_shipped = 0
    ORDER BY s.name, t.name;
    """
    rows = fetch_all_dicts(conn, sql)
    if TARGET_TABLES:
        rows = [r for r in rows if r["table_name"] in TARGET_TABLES]
    log.info("Found %s user tables.", len(rows))
    return rows


def get_schema_metadata(conn: pyodbc.Connection) -> List[Dict[str, Any]]:
    sql = """
    SELECT
        DB_NAME() AS database_name,
        s.name AS schema_name,
        t.name AS table_name,
        t.object_id,
        c.column_id,
        c.name AS column_name,
        ty.name AS base_type,
        CASE
            WHEN ty.name IN ('varchar', 'char', 'varbinary', 'binary')
                THEN ty.name + '(' + CASE WHEN c.max_length = -1 THEN 'max' ELSE CAST(c.max_length AS varchar(10)) END + ')'
            WHEN ty.name IN ('nvarchar', 'nchar')
                THEN ty.name + '(' + CASE WHEN c.max_length = -1 THEN 'max' ELSE CAST(c.max_length / 2 AS varchar(10)) END + ')'
            WHEN ty.name IN ('decimal', 'numeric')
                THEN ty.name + '(' + CAST(c.precision AS varchar(10)) + ',' + CAST(c.scale AS varchar(10)) + ')'
            WHEN ty.name IN ('datetime2', 'datetimeoffset', 'time')
                THEN ty.name + '(' + CAST(c.scale AS varchar(10)) + ')'
            ELSE ty.name
        END AS data_type,
        c.max_length,
        c.precision,
        c.scale,
        c.is_nullable,
        c.is_identity,
        c.is_computed,
        dc.definition AS default_definition,
        CAST(CASE WHEN pk.column_id IS NOT NULL THEN 1 ELSE 0 END AS bit) AS is_primary_key,
        CAST(CASE WHEN fk.parent_column_id IS NOT NULL THEN 1 ELSE 0 END AS bit) AS is_foreign_key,
        rs.name AS referenced_schema_name,
        rt.name AS referenced_table_name,
        rc.name AS referenced_column_name
    FROM sys.tables t
    JOIN sys.schemas s
        ON t.schema_id = s.schema_id
    JOIN sys.columns c
        ON t.object_id = c.object_id
    JOIN sys.types ty
        ON c.user_type_id = ty.user_type_id
    LEFT JOIN sys.default_constraints dc
        ON c.default_object_id = dc.object_id
    LEFT JOIN (
        SELECT
            ic.object_id,
            ic.column_id
        FROM sys.indexes i
        JOIN sys.index_columns ic
            ON i.object_id = ic.object_id
           AND i.index_id = ic.index_id
        WHERE i.is_primary_key = 1
    ) pk
        ON c.object_id = pk.object_id
       AND c.column_id = pk.column_id
    LEFT JOIN sys.foreign_key_columns fk
        ON c.object_id = fk.parent_object_id
       AND c.column_id = fk.parent_column_id
    LEFT JOIN sys.tables rt
        ON fk.referenced_object_id = rt.object_id
    LEFT JOIN sys.schemas rs
        ON rt.schema_id = rs.schema_id
    LEFT JOIN sys.columns rc
        ON fk.referenced_object_id = rc.object_id
       AND fk.referenced_column_id = rc.column_id
    WHERE t.is_ms_shipped = 0
    ORDER BY s.name, t.name, c.column_id;
    """
    rows = fetch_all_dicts(conn, sql)
    if TARGET_TABLES:
        rows = [r for r in rows if r["table_name"] in TARGET_TABLES]
    log.info("Extracted metadata for %s columns.", len(rows))
    return rows


# -----------------------------------------------------------------------------
# Profiling
# -----------------------------------------------------------------------------

def get_table_row_count(conn: pyodbc.Connection, schema_name: str, table_name: str) -> int:
    sql = f"SELECT COUNT(*) FROM {quote_ident(schema_name)}.{quote_ident(table_name)};"
    return int(fetch_scalar(conn, sql) or 0)


def get_null_count(conn: pyodbc.Connection, schema_name: str, table_name: str, column_name: str) -> int:
    sql = f"""
    SELECT COUNT(*)
    FROM {quote_ident(schema_name)}.{quote_ident(table_name)}
    WHERE {quote_ident(column_name)} IS NULL;
    """
    return int(fetch_scalar(conn, sql) or 0)


def get_distinct_count(conn: pyodbc.Connection, schema_name: str, table_name: str, column_name: str) -> int:
    sql = f"""
    SELECT COUNT(DISTINCT TRY_CONVERT(nvarchar(4000), {quote_ident(column_name)}))
    FROM {quote_ident(schema_name)}.{quote_ident(table_name)};
    """
    return int(fetch_scalar(conn, sql) or 0)


def get_numeric_examples(conn: pyodbc.Connection, schema_name: str, table_name: str, column_name: str) -> List[str]:
    sql = f"""
    SELECT TOP ({MAX_SAMPLE_VALUES})
        TRY_CONVERT(varchar(100), {quote_ident(column_name)}) AS val
    FROM {quote_ident(schema_name)}.{quote_ident(table_name)}
    WHERE {quote_ident(column_name)} IS NOT NULL
    GROUP BY TRY_CONVERT(varchar(100), {quote_ident(column_name)})
    ORDER BY COUNT(*) DESC, TRY_CONVERT(varchar(100), {quote_ident(column_name)});
    """
    rows = fetch_all_dicts(conn, sql)
    return [str(r["val"]) for r in rows if r.get("val") is not None]


def get_date_examples(conn: pyodbc.Connection, schema_name: str, table_name: str, column_name: str) -> List[str]:
    sql = f"""
    SELECT TOP ({MAX_SAMPLE_VALUES})
        CONVERT(varchar(19), {quote_ident(column_name)}, 120) AS val
    FROM {quote_ident(schema_name)}.{quote_ident(table_name)}
    WHERE {quote_ident(column_name)} IS NOT NULL
    GROUP BY CONVERT(varchar(19), {quote_ident(column_name)}, 120)
    ORDER BY CONVERT(varchar(19), {quote_ident(column_name)}, 120) DESC;
    """
    rows = fetch_all_dicts(conn, sql)
    return [r["val"] for r in rows if r.get("val") is not None]


def get_long_text_metrics(conn: pyodbc.Connection, schema_name: str, table_name: str, column_name: str) -> Dict[str, Any]:
    sql = f"""
    SELECT
        AVG(CAST(LEN(TRY_CONVERT(nvarchar(4000), {quote_ident(column_name)})) AS float)) AS avg_length,
        MAX(LEN(TRY_CONVERT(nvarchar(4000), {quote_ident(column_name)}))) AS max_length_nonnull,
        SUM(CASE
            WHEN TRY_CONVERT(nvarchar(4000), {quote_ident(column_name)}) LIKE N'%[' + NCHAR(0x0600) + N'-' + NCHAR(0x06FF) + N']%'
                THEN 1 ELSE 0
        END) AS arabic_like_count,
        SUM(CASE
            WHEN TRY_CONVERT(nvarchar(4000), {quote_ident(column_name)}) LIKE '%[A-Za-z]%'
                THEN 1 ELSE 0
        END) AS english_like_count
    FROM {quote_ident(schema_name)}.{quote_ident(table_name)}
    WHERE {quote_ident(column_name)} IS NOT NULL;
    """
    row = fetch_all_dicts(conn, sql)[0]
    return {
        "avg_length": round(float(row["avg_length"]), 2) if row["avg_length"] is not None else None,
        "max_length_nonnull": int(row["max_length_nonnull"]) if row["max_length_nonnull"] is not None else None,
        "arabic_like_count": int(row["arabic_like_count"]) if row["arabic_like_count"] is not None else 0,
        "english_like_count": int(row["english_like_count"]) if row["english_like_count"] is not None else 0,
    }


def get_random_value_pool(
    conn: pyodbc.Connection,
    schema_name: str,
    table_name: str,
    column_name: str,
    limit: int = PROFILE_RANDOM_POOL_SIZE
) -> List[str]:
    sql = f"""
    SELECT TOP ({limit})
        TRY_CONVERT(nvarchar(4000), {quote_ident(column_name)}) AS val
    FROM {quote_ident(schema_name)}.{quote_ident(table_name)}
    WHERE {quote_ident(column_name)} IS NOT NULL
      AND LTRIM(RTRIM(TRY_CONVERT(nvarchar(4000), {quote_ident(column_name)}))) <> ''
    ORDER BY NEWID();
    """
    rows = fetch_all_dicts(conn, sql)
    return [safe_str(r["val"]) for r in rows if r.get("val") is not None]


def infer_text_profile_mode(column_name: str, data_type: str, distinct_count: Optional[int]) -> str:
    col = column_name.lower()
    dt = data_type.lower()

    if not infer_is_textual_type(dt):
        return "not_text"

    if "(max)" in dt or "text" in dt:
        return "long_text"

    if any(token in col for token in ["summary", "description", "comment", "note", "remarks", "details", "content", "text", "body"]):
        return "long_text"

    if distinct_count is not None and distinct_count <= 100:
        return "categorical_text"

    return "regular_text"


def get_column_profile(
    conn: pyodbc.Connection,
    schema_name: str,
    table_name: str,
    column_name: str,
    data_type: str,
    row_count: int
) -> Dict[str, Any]:
    try:
        null_count = get_null_count(conn, schema_name, table_name, column_name)
        distinct_count = get_distinct_count(conn, schema_name, table_name, column_name)

        sample_values: List[str] = []
        text_metrics: Optional[Dict[str, Any]] = None
        pattern_profile: Optional[Dict[str, Any]] = None

        if infer_is_numeric_type(data_type) or infer_is_boolean_type(data_type):
            sample_values = get_numeric_examples(conn, schema_name, table_name, column_name)

        elif infer_is_date_type(data_type):
            sample_values = get_date_examples(conn, schema_name, table_name, column_name)

        elif infer_is_textual_type(data_type):
            random_pool = get_random_value_pool(
                conn=conn,
                schema_name=schema_name,
                table_name=table_name,
                column_name=column_name,
                limit=PROFILE_RANDOM_POOL_SIZE
            )

            if should_run_pattern_analysis(data_type, distinct_count):
                pattern_profile = build_pattern_profile(random_pool)
                sample_values = pattern_profile["representative_values"]

            text_mode = infer_text_profile_mode(column_name, data_type, distinct_count)

            if text_mode == "long_text":
                text_metrics = get_long_text_metrics(conn, schema_name, table_name, column_name)
                if not sample_values:
                    sample_values = choose_best_examples(random_pool, 1)

            elif not sample_values:
                sample_values = choose_best_examples(random_pool, MAX_SAMPLE_VALUES)

        return {
            "row_count": row_count,
            "null_count": null_count,
            "null_ratio": round(null_count / row_count, 4) if row_count else None,
            "distinct_count": distinct_count,
            "sample_values": sample_values,
            "text_metrics": text_metrics,
            "pattern_profile": pattern_profile,
            "profile_error": None
        }

    except Exception as exc:
        log.warning("Profiling failed for %s.%s.%s: %s", schema_name, table_name, column_name, exc)
        return {
            "row_count": row_count,
            "null_count": None,
            "null_ratio": None,
            "distinct_count": None,
            "sample_values": [],
            "text_metrics": None,
            "pattern_profile": None,
            "profile_error": str(exc)
        }


# -----------------------------------------------------------------------------
# Generic semantic inference
# -----------------------------------------------------------------------------

def infer_column_role(column_meta: Dict[str, Any], profile: Dict[str, Any]) -> str:
    col = column_meta["column_name"].lower()
    dt = str(column_meta["data_type"]).lower()

    if column_meta.get("is_primary_key"):
        return "primary_key"
    if column_meta.get("is_foreign_key"):
        return "foreign_key"
    if infer_is_date_type(dt):
        return "date_or_time"
    if infer_is_boolean_type(dt):
        return "boolean"
    if infer_is_numeric_type(dt):
        if any(token in col for token in ["score", "amount", "total", "count", "qty", "quantity", "price", "rate", "percent", "age", "year", "years"]):
            return "numeric_measure"
        return "numeric_attribute"
    if infer_is_textual_type(dt):
        mode = infer_text_profile_mode(column_meta["column_name"], column_meta["data_type"], profile.get("distinct_count"))
        if mode == "long_text":
            return "long_text"
        if mode == "categorical_text":
            return "categorical_text"
        return "text"
    return "attribute"


def infer_searchability(column_meta: Dict[str, Any], profile: Dict[str, Any]) -> bool:
    if not infer_is_textual_type(column_meta["data_type"]):
        return False
    if profile.get("distinct_count") == 0:
        return False
    return True


def infer_filterability(column_meta: Dict[str, Any], profile: Dict[str, Any]) -> bool:
    dt = str(column_meta["data_type"]).lower()
    distinct_count = profile.get("distinct_count")
    row_count = profile.get("row_count")

    if column_meta.get("is_primary_key") or column_meta.get("is_foreign_key"):
        return True
    if infer_is_boolean_type(dt):
        return True
    if infer_is_date_type(dt):
        return True

    if distinct_count is not None and row_count:
        if 1 <= distinct_count <= 100 and distinct_count < row_count:
            return True

    return False


def infer_sortability(column_meta: Dict[str, Any]) -> bool:
    dt = str(column_meta["data_type"]).lower()
    return infer_is_numeric_type(dt) or infer_is_date_type(dt) or infer_is_boolean_type(dt)


def infer_aggregation_hint(column_meta: Dict[str, Any], profile: Dict[str, Any]) -> str:
    dt = str(column_meta["data_type"]).lower()

    if infer_is_numeric_type(dt):
        return "sum_avg_min_max"
    if infer_is_date_type(dt):
        return "min_max"
    if infer_is_boolean_type(dt):
        return "group_count"
    if infer_is_textual_type(dt):
        distinct_count = profile.get("distinct_count")
        if distinct_count is not None and distinct_count <= 100:
            return "group_count"
    return "count_only"


# -----------------------------------------------------------------------------
# Table indexing and entity analysis
# -----------------------------------------------------------------------------

def build_table_index(schema_rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    table_index: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in schema_rows:
        table_key = f"{row['schema_name']}.{row['table_name']}"
        table_index[table_key].append(row)
    return dict(table_index)


def infer_entity_keys_for_table(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    candidates = []

    for row in rows:
        col = row["column_name"]
        col_lower = col.lower()
        dt = str(row["data_type"]).lower()

        score = 0
        reasons = []

        if row.get("is_primary_key"):
            score += 100
            reasons.append("primary_key")

        if row.get("is_identity"):
            score += 30
            reasons.append("identity")

        if col_lower == "id":
            score += 40
            reasons.append("column_name_id")

        if col_lower.endswith("_id"):
            score += 25
            reasons.append("column_name_suffix_id")

        if infer_is_numeric_type(dt):
            score += 10
            reasons.append("numeric_type")

        if infer_is_textual_type(dt) and "(max)" not in dt:
            score += 5
            reasons.append("short_text_possible_business_key")

        if not row.get("is_nullable"):
            score += 5
            reasons.append("not_nullable")

        candidates.append({
            "column_name": col,
            "score": score,
            "reasons": reasons
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates


def infer_entity_key_map(table_index: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
    result = {}
    for table_key, rows in table_index.items():
        candidates = infer_entity_keys_for_table(rows)
        chosen = candidates[0] if candidates else None
        result[table_key] = {
            "likely_entity_key": chosen["column_name"] if chosen and chosen["score"] > 0 else None,
            "candidate_keys_ranked": candidates[:5]
        }
    return result


# -----------------------------------------------------------------------------
# Relationship analysis
# -----------------------------------------------------------------------------

def build_relationship_map(schema_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    relationships = []
    tables = set()

    for row in schema_rows:
        source = f"{row['schema_name']}.{row['table_name']}"
        tables.add(source)

        if row.get("is_foreign_key"):
            target_schema = row.get("referenced_schema_name")
            target_table = row.get("referenced_table_name")
            target_col = row.get("referenced_column_name")

            if target_schema and target_table and target_col:
                target = f"{target_schema}.{target_table}"
                tables.add(target)

                relationships.append({
                    "from_table": source,
                    "from_column": row["column_name"],
                    "to_table": target,
                    "to_column": target_col,
                    "join_sql": f"{source}.{row['column_name']} = {target}.{target_col}",
                    "relationship_type": "foreign_key"
                })

    return {
        "tables_in_relationships": sorted(tables),
        "relationships": relationships
    }


def build_join_hints(schema_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    hints = []
    seen = set()

    for row in schema_rows:
        if not row.get("is_foreign_key"):
            continue

        left_table = f"{row['schema_name']}.{row['table_name']}"
        right_schema = row.get("referenced_schema_name")
        right_table = row.get("referenced_table_name")
        right_column = row.get("referenced_column_name")

        if not right_schema or not right_table or not right_column:
            continue

        right_table_full = f"{right_schema}.{right_table}"
        key = (left_table, row["column_name"], right_table_full, right_column)
        if key in seen:
            continue
        seen.add(key)

        hints.append({
            "left_table": left_table,
            "right_table": right_table_full,
            "left_column": row["column_name"],
            "right_column": right_column,
            "recommended_join_type": "INNER JOIN",
            "join_condition": f"{left_table}.{row['column_name']} = {right_table_full}.{right_column}",
            "usage_note": f"Join {left_table} to {right_table_full} using discovered foreign key metadata."
        })

    return hints


def infer_table_roles(
    table_index: Dict[str, List[Dict[str, Any]]],
    entity_key_map: Dict[str, Dict[str, Any]],
    relationship_map: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    inbound_count = defaultdict(int)
    outbound_count = defaultdict(int)

    for rel in relationship_map["relationships"]:
        outbound_count[rel["from_table"]] += 1
        inbound_count[rel["to_table"]] += 1

    result = {}

    for table_key, rows in table_index.items():
        textual_cols = sum(1 for r in rows if infer_is_textual_type(r["data_type"]))
        non_fk_cols = sum(1 for r in rows if not r.get("is_foreign_key"))
        out_fk = outbound_count.get(table_key, 0)
        in_fk = inbound_count.get(table_key, 0)

        role = "standalone"
        reasons = []

        if out_fk == 0 and in_fk > 0:
            role = "root_like"
            reasons.append("referenced_by_other_tables")
        elif out_fk >= 1 and in_fk == 0:
            role = "child_like"
            reasons.append("contains_outbound_foreign_keys")
        elif out_fk >= 2 and non_fk_cols <= 4:
            role = "bridge_like"
            reasons.append("multiple_foreign_keys_few_descriptive_columns")
        elif out_fk >= 1 and in_fk >= 1:
            role = "intermediate_like"
            reasons.append("has_inbound_and_outbound_relationships")

        if entity_key_map.get(table_key, {}).get("likely_entity_key"):
            reasons.append("entity_key_discovered")

        result[table_key] = {
            "role": role,
            "inbound_relationship_count": in_fk,
            "outbound_relationship_count": out_fk,
            "textual_column_count": textual_cols,
            "reasons": reasons
        }

    return result


def build_generic_count_rules(
    table_index: Dict[str, List[Dict[str, Any]]],
    entity_key_map: Dict[str, Dict[str, Any]],
    table_roles: Dict[str, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    rules = []

    for table_key, _rows in table_index.items():
        role = table_roles.get(table_key, {}).get("role")
        entity_key = entity_key_map.get(table_key, {}).get("likely_entity_key")

        rules.append({
            "table": table_key,
            "rule_type": "raw_row_count",
            "guidance": f"Use COUNT(*) when the user asks for raw row count of {table_key}."
        })

        if entity_key:
            rules.append({
                "table": table_key,
                "rule_type": "entity_count",
                "guidance": f"Use COUNT(DISTINCT {entity_key}) when the user asks for distinct entities represented by {table_key}."
            })

        if role in {"child_like", "bridge_like", "intermediate_like"} and entity_key:
            rules.append({
                "table": table_key,
                "rule_type": "duplicate_risk_after_join",
                "guidance": (
                    f"{table_key} may duplicate rows after joins. Prefer COUNT(DISTINCT {entity_key}) "
                    f"or aggregate before joining when the question is about unique entities."
                )
            })

    return rules


def build_table_guidance(
    table_index: Dict[str, List[Dict[str, Any]]],
    profiles_by_key: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    result = {}

    for table_key, rows in table_index.items():
        recommended_search_columns = []
        recommended_filter_columns = []
        recommended_sort_columns = []
        aggregation_candidates = []

        schema_name, table_name = table_key.split(".", 1)

        for row in rows:
            key = f"{schema_name}.{table_name}.{row['column_name']}"
            profile = profiles_by_key.get(key, {})

            if infer_searchability(row, profile):
                recommended_search_columns.append(row["column_name"])
            if infer_filterability(row, profile):
                recommended_filter_columns.append(row["column_name"])
            if infer_sortability(row):
                recommended_sort_columns.append(row["column_name"])

            agg = infer_aggregation_hint(row, profile)
            if agg != "count_only":
                aggregation_candidates.append({
                    "column_name": row["column_name"],
                    "aggregation_hint": agg
                })

        result[table_key] = {
            "recommended_search_columns": recommended_search_columns,
            "recommended_filter_columns": recommended_filter_columns,
            "recommended_sort_columns": recommended_sort_columns,
            "aggregation_candidates": aggregation_candidates
        }

    return result


# -----------------------------------------------------------------------------
# Query templates
# -----------------------------------------------------------------------------

def pick_first_matching_column(rows: List[Dict[str, Any]], predicate) -> Optional[str]:
    for row in rows:
        if predicate(row):
            return row["column_name"]
    return None


def build_table_query_templates(
    table_key: str,
    rows: List[Dict[str, Any]],
    table_guidance: Dict[str, Any],
    entity_key_map: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    schema_name, table_name = table_key.split(".", 1)
    quoted_table = f"{quote_ident(schema_name)}.{quote_ident(table_name)}"

    entity_key = entity_key_map.get(table_key, {}).get("likely_entity_key")
    filter_cols = table_guidance.get(table_key, {}).get("recommended_filter_columns", [])
    sort_cols = table_guidance.get(table_key, {}).get("recommended_sort_columns", [])

    date_col = pick_first_matching_column(rows, lambda r: infer_is_date_type(r["data_type"]))
    numeric_col = pick_first_matching_column(rows, lambda r: infer_is_numeric_type(r["data_type"]) and not r.get("is_primary_key"))
    text_col = pick_first_matching_column(rows, lambda r: infer_is_textual_type(r["data_type"]))
    group_col = filter_cols[0] if filter_cols else text_col
    order_col = date_col or (sort_cols[0] if sort_cols else entity_key)

    templates: Dict[str, str] = {}

    templates["basic_select_top_100"] = f"SELECT TOP 100 * FROM {quoted_table};"
    templates["row_count"] = f"SELECT COUNT(*) AS row_count FROM {quoted_table};"

    if entity_key:
        templates["distinct_entity_count"] = (
            f"SELECT COUNT(DISTINCT {quote_ident(entity_key)}) AS distinct_entity_count "
            f"FROM {quoted_table};"
        )

    if group_col:
        templates["grouped_count"] = (
            f"SELECT TOP 50 {quote_ident(group_col)} AS group_value, COUNT(*) AS row_count\n"
            f"FROM {quoted_table}\n"
            f"WHERE {quote_ident(group_col)} IS NOT NULL\n"
            f"GROUP BY {quote_ident(group_col)}\n"
            f"ORDER BY COUNT(*) DESC;"
        )

    if date_col:
        templates["latest_records"] = (
            f"SELECT TOP 100 *\n"
            f"FROM {quoted_table}\n"
            f"WHERE {quote_ident(date_col)} IS NOT NULL\n"
            f"ORDER BY {quote_ident(date_col)} DESC;"
        )

    if numeric_col:
        templates["top_by_numeric_metric"] = (
            f"SELECT TOP 100 *\n"
            f"FROM {quoted_table}\n"
            f"WHERE {quote_ident(numeric_col)} IS NOT NULL\n"
            f"ORDER BY {quote_ident(numeric_col)} DESC;"
        )

        if group_col:
            templates["grouped_numeric_summary"] = (
                f"SELECT TOP 50 {quote_ident(group_col)} AS group_value,\n"
                f"       COUNT(*) AS row_count,\n"
                f"       AVG(CAST({quote_ident(numeric_col)} AS float)) AS avg_value,\n"
                f"       MIN({quote_ident(numeric_col)}) AS min_value,\n"
                f"       MAX({quote_ident(numeric_col)}) AS max_value\n"
                f"FROM {quoted_table}\n"
                f"WHERE {quote_ident(group_col)} IS NOT NULL\n"
                f"  AND {quote_ident(numeric_col)} IS NOT NULL\n"
                f"GROUP BY {quote_ident(group_col)}\n"
                f"ORDER BY AVG(CAST({quote_ident(numeric_col)} AS float)) DESC;"
            )

    if text_col:
        templates["text_search_like"] = (
            f"SELECT TOP 100 *\n"
            f"FROM {quoted_table}\n"
            f"WHERE {quote_ident(text_col)} LIKE '%search_text%';"
        )

    if order_col:
        templates["ordered_sample"] = (
            f"SELECT TOP 100 *\n"
            f"FROM {quoted_table}\n"
            f"ORDER BY {quote_ident(order_col)} DESC;"
        )

    return templates


def build_join_query_templates(join_hints: List[Dict[str, Any]], entity_key_map: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    templates = []

    for hint in join_hints:
        left_table = hint["left_table"]
        right_table = hint["right_table"]
        left_col = hint["left_column"]
        right_col = hint["right_column"]

        left_schema, left_name = left_table.split(".", 1)
        right_schema, right_name = right_table.split(".", 1)

        left_q = f"{quote_ident(left_schema)}.{quote_ident(left_name)}"
        right_q = f"{quote_ident(right_schema)}.{quote_ident(right_name)}"

        left_entity = entity_key_map.get(left_table, {}).get("likely_entity_key")
        right_entity = entity_key_map.get(right_table, {}).get("likely_entity_key")

        item = {
            "left_table": left_table,
            "right_table": right_table,
            "join_condition": hint["join_condition"],
            "templates": {
                "basic_join_top_100": (
                    f"SELECT TOP 100 *\n"
                    f"FROM {left_q} AS l\n"
                    f"INNER JOIN {right_q} AS r\n"
                    f"    ON l.{quote_ident(left_col)} = r.{quote_ident(right_col)};"
                ),
                "joined_row_count": (
                    f"SELECT COUNT(*) AS joined_row_count\n"
                    f"FROM {left_q} AS l\n"
                    f"INNER JOIN {right_q} AS r\n"
                    f"    ON l.{quote_ident(left_col)} = r.{quote_ident(right_col)};"
                )
            }
        }

        if left_entity:
            item["templates"]["distinct_left_entity_count_after_join"] = (
                f"SELECT COUNT(DISTINCT l.{quote_ident(left_entity)}) AS distinct_left_entity_count\n"
                f"FROM {left_q} AS l\n"
                f"INNER JOIN {right_q} AS r\n"
                f"    ON l.{quote_ident(left_col)} = r.{quote_ident(right_col)};"
            )

        if right_entity:
            item["templates"]["distinct_right_entity_count_after_join"] = (
                f"SELECT COUNT(DISTINCT r.{quote_ident(right_entity)}) AS distinct_right_entity_count\n"
                f"FROM {left_q} AS l\n"
                f"INNER JOIN {right_q} AS r\n"
                f"    ON l.{quote_ident(left_col)} = r.{quote_ident(right_col)};"
            )

        templates.append(item)

    return templates


def build_query_template_pack(
    table_index: Dict[str, List[Dict[str, Any]]],
    table_guidance: Dict[str, Any],
    entity_key_map: Dict[str, Dict[str, Any]],
    join_hints: List[Dict[str, Any]]
) -> Dict[str, Any]:
    table_templates = {}
    for table_key, rows in table_index.items():
        table_templates[table_key] = build_table_query_templates(
            table_key=table_key,
            rows=rows,
            table_guidance=table_guidance,
            entity_key_map=entity_key_map
        )

    join_templates = build_join_query_templates(join_hints, entity_key_map)

    return {
        "table_templates": table_templates,
        "join_templates": join_templates
    }


# -----------------------------------------------------------------------------
# Chunking
# -----------------------------------------------------------------------------

def chunk_list(items: List[Any], chunk_size: int) -> List[List[Any]]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


def build_chunked_payloads(full_payload: Dict[str, Any]) -> Dict[str, Any]:
    tables = full_payload.get("tables", [])
    relationships = full_payload.get("relationship_map", {}).get("relationships", [])
    join_hints = full_payload.get("join_hints", [])
    count_rules = full_payload.get("count_rules", [])
    table_guidance = full_payload.get("table_guidance", {})
    query_templates = full_payload.get("query_templates", {})
    global_analysis = full_payload.get("global_analysis", {})

    table_chunks = chunk_list(tables, MAX_TABLES_PER_CHUNK)
    relationship_chunks = chunk_list(relationships, MAX_RELATIONSHIPS_PER_CHUNK)
    join_hint_chunks = chunk_list(join_hints, MAX_RELATIONSHIPS_PER_CHUNK)

    overview = {
        "database_name": full_payload.get("database_name"),
        "version": full_payload.get("version"),
        "generator_type": full_payload.get("generator_type"),
        "table_count": len(tables),
        "relationship_count": len(relationships),
        "count_rule_count": len(count_rules),
        "chunking": {
            "max_tables_per_chunk": MAX_TABLES_PER_CHUNK,
            "max_relationships_per_chunk": MAX_RELATIONSHIPS_PER_CHUNK,
            "table_chunk_count": len(table_chunks),
            "relationship_chunk_count": len(relationship_chunks),
            "join_hint_chunk_count": len(join_hint_chunks)
        },
        "global_analysis": global_analysis,
        "guidance_for_llm": full_payload.get("guidance_for_llm", {})
    }

    table_payloads = []
    for idx, chunk in enumerate(table_chunks, start=1):
        chunk_tables = {t["full_table_name"]: t for t in chunk}
        chunk_guidance = {k: v for k, v in table_guidance.items() if k in chunk_tables}
        chunk_templates = {
            "table_templates": {
                k: v
                for k, v in query_templates.get("table_templates", {}).items()
                if k in chunk_tables
            }
        }

        table_payloads.append({
            "payload_type": "table_chunk",
            "chunk_index": idx,
            "chunk_count": len(table_chunks),
            "database_name": full_payload.get("database_name"),
            "tables": chunk,
            "table_guidance": chunk_guidance,
            "query_templates": chunk_templates
        })

    relationship_payloads = []
    for idx, rel_chunk in enumerate(relationship_chunks, start=1):
        relationship_payloads.append({
            "payload_type": "relationship_chunk",
            "chunk_index": idx,
            "chunk_count": len(relationship_chunks),
            "database_name": full_payload.get("database_name"),
            "relationships": rel_chunk
        })

    join_payloads = []
    for idx, join_chunk in enumerate(join_hint_chunks, start=1):
        related_join_templates = []
        for jt in query_templates.get("join_templates", []):
            for hint in join_chunk:
                if jt["left_table"] == hint["left_table"] and jt["right_table"] == hint["right_table"]:
                    related_join_templates.append(jt)
                    break

        join_payloads.append({
            "payload_type": "join_chunk",
            "chunk_index": idx,
            "chunk_count": len(join_hint_chunks),
            "database_name": full_payload.get("database_name"),
            "join_hints": join_chunk,
            "join_templates": related_join_templates
        })

    return {
        "overview": overview,
        "table_payloads": table_payloads,
        "relationship_payloads": relationship_payloads,
        "join_payloads": join_payloads
    }


# -----------------------------------------------------------------------------
# Final payload builder
# -----------------------------------------------------------------------------

def build_llm_metadata(
    database_name: str,
    schema_rows: List[Dict[str, Any]],
    profiles_by_key: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    table_index = build_table_index(schema_rows)
    entity_key_map = infer_entity_key_map(table_index)
    relationship_map = build_relationship_map(schema_rows)
    join_hints = build_join_hints(schema_rows)
    table_roles = infer_table_roles(table_index, entity_key_map, relationship_map)
    count_rules = build_generic_count_rules(table_index, entity_key_map, table_roles)
    table_guidance = build_table_guidance(table_index, profiles_by_key)

    tables = []

    for table_key, rows in table_index.items():
        schema_name, table_name = table_key.split(".", 1)
        first_profile = profiles_by_key.get(f"{table_key}.{rows[0]['column_name']}", {}) if rows else {}

        table_obj = {
            "schema_name": schema_name,
            "table_name": table_name,
            "full_table_name": table_key,
            "row_count": first_profile.get("row_count"),
            "table_role": table_roles.get(table_key, {}),
            "entity_key_analysis": entity_key_map.get(table_key, {}),
            "primary_keys": [],
            "foreign_keys": [],
            "searchable_columns": [],
            "likely_filter_columns": [],
            "likely_sort_columns": [],
            "columns": []
        }

        for row in rows:
            profile_key = f"{table_key}.{row['column_name']}"
            profile = profiles_by_key.get(profile_key, {})

            col_obj = {
                "column_order": row["column_id"],
                "column_name": row["column_name"],
                "data_type": row["data_type"],
                "base_type": row["base_type"],
                "nullable": bool(row["is_nullable"]),
                "identity": bool(row["is_identity"]),
                "computed": bool(row["is_computed"]),
                "default_definition": to_json_safe(row["default_definition"]),
                "primary_key": bool(row["is_primary_key"]),
                "foreign_key": bool(row["is_foreign_key"]),
                "referenced_schema_name": to_json_safe(row["referenced_schema_name"]),
                "referenced_table_name": to_json_safe(row["referenced_table_name"]),
                "referenced_column_name": to_json_safe(row["referenced_column_name"]),
                "row_count": to_json_safe(profile.get("row_count")),
                "null_count": to_json_safe(profile.get("null_count")),
                "null_ratio": to_json_safe(profile.get("null_ratio")),
                "distinct_count": to_json_safe(profile.get("distinct_count")),
                "sample_values": [to_json_safe(v) for v in profile.get("sample_values", [])],
                "text_metrics": to_json_safe(profile.get("text_metrics")),
                "pattern_profile": to_json_safe(profile.get("pattern_profile")),
                "value_semantics": infer_value_semantics_from_pattern(profile.get("pattern_profile")),
                "profile_error": to_json_safe(profile.get("profile_error")),
                "semantic_role": infer_column_role(row, profile),
                "searchable": infer_searchability(row, profile),
                "likely_filter_column": infer_filterability(row, profile),
                "likely_sort_column": infer_sortability(row),
                "aggregation_hint": infer_aggregation_hint(row, profile),
            }

            table_obj["columns"].append(col_obj)

            if col_obj["primary_key"]:
                table_obj["primary_keys"].append(row["column_name"])

            if col_obj["foreign_key"]:
                table_obj["foreign_keys"].append({
                    "column_name": row["column_name"],
                    "references": {
                        "schema_name": to_json_safe(row["referenced_schema_name"]),
                        "table_name": to_json_safe(row["referenced_table_name"]),
                        "column_name": to_json_safe(row["referenced_column_name"]),
                    }
                })

            if col_obj["searchable"]:
                table_obj["searchable_columns"].append(row["column_name"])

            if col_obj["likely_filter_column"]:
                table_obj["likely_filter_columns"].append(row["column_name"])

            if col_obj["likely_sort_column"]:
                table_obj["likely_sort_columns"].append(row["column_name"])

        tables.append(table_obj)

    query_templates = build_query_template_pack(
        table_index=table_index,
        table_guidance=table_guidance,
        entity_key_map=entity_key_map,
        join_hints=join_hints
    )

    payload = {
        "database_name": database_name,
        "extracted_for_llm": True,
        "version": 5,
        "generator_type": "generic_sql_server_schema_extractor",
        "table_count": len(tables),
        "tables": tables,
        "relationship_map": relationship_map,
        "join_hints": join_hints,
        "count_rules": count_rules,
        "table_guidance": table_guidance,
        "global_analysis": {
            "entity_key_map": entity_key_map,
            "table_roles": table_roles
        },
        "query_templates": query_templates,
        "guidance_for_llm": {
            "rules": [
                "Only generate SQL against listed tables and columns.",
                "Prefer explicit joins using discovered foreign keys and join_hints.",
                "Use entity_key_analysis to decide when COUNT(DISTINCT ...) is safer than COUNT(*).",
                "Use count_rules to avoid duplicate counting after joins.",
                "Use query_templates as safe starting patterns.",
                "Use recommended_filter_columns for WHERE clauses when appropriate.",
                "Use recommended_search_columns for text search when appropriate.",
                "Pattern profiles describe the typical structure of text values.",
                "Sample values intentionally exclude poor-quality and Arabic-script examples."
            ]
        }
    }

    payload["chunked_payloads"] = build_chunked_payloads(payload)
    return payload


# -----------------------------------------------------------------------------
# Prompt context
# -----------------------------------------------------------------------------

def build_compact_prompt_context(llm_json: Dict[str, Any]) -> str:
    lines: List[str] = []

    lines.append(f"DATABASE: {llm_json['database_name']}")
    lines.append(f"SCHEMA VERSION: {llm_json.get('version')}")
    lines.append(f"GENERATOR: {llm_json.get('generator_type')}")
    lines.append("")

    lines.append("JOIN HINTS:")
    for hint in llm_json.get("join_hints", []):
        lines.append(f"- {hint['left_table']} JOIN {hint['right_table']} ON {hint['join_condition']}")

    lines.append("")
    lines.append("COUNT RULES:")
    for rule in llm_json.get("count_rules", []):
        lines.append(f"- {rule['table']}: {rule['guidance']}")

    lines.append("")
    lines.append("TABLES:")

    for table in llm_json["tables"]:
        lines.append(
            f"- {table['full_table_name']} "
            f"(rows={table.get('row_count')}, role={table.get('table_role', {}).get('role')})"
        )

        entity_key = table.get("entity_key_analysis", {}).get("likely_entity_key")
        if entity_key:
            lines.append(f"  Likely entity key: {entity_key}")

        if table["primary_keys"]:
            lines.append(f"  PK: {', '.join(table['primary_keys'])}")

        if table["foreign_keys"]:
            for fk in table["foreign_keys"]:
                ref = fk["references"]
                lines.append(
                    f"  FK: {fk['column_name']} -> {ref.get('schema_name')}.{ref.get('table_name')}.{ref.get('column_name')}"
                )

        lines.append(f"  Searchable: {', '.join(table['searchable_columns']) or '-'}")
        lines.append(f"  Filterable: {', '.join(table['likely_filter_columns']) or '-'}")
        lines.append(f"  Sortable: {', '.join(table['likely_sort_columns']) or '-'}")

        for col in table["columns"]:
            sample_text = ", ".join([str(v) for v in col.get("sample_values", [])[:3]])
            dominant_pattern = None
            if col.get("pattern_profile"):
                dominant_pattern = col["pattern_profile"].get("dominant_pattern")

            lines.append(
                f"  - {col['column_name']} {col['data_type']}"
                f" | role={col['semantic_role']}"
                f" | nullable={col['nullable']}"
                f" | distinct={col.get('distinct_count')}"
                f" | null_ratio={col.get('null_ratio')}"
                f" | agg={col.get('aggregation_hint')}"
                f" | value_semantics={col.get('value_semantics')}"
                f" | dominant_pattern={dominant_pattern}"
                f" | samples=[{sample_text}]"
            )

    return "\n".join(lines)


# -----------------------------------------------------------------------------
# Pipeline
# -----------------------------------------------------------------------------

def run_schema_extraction_v5() -> Dict[str, Any]:
    conn = open_db_connection()

    try:
        db_name = str(fetch_scalar(conn, "SELECT DB_NAME();"))
        log.info("Connected to database: %s", db_name)

        tables = get_all_user_tables(conn)
        if not tables:
            raise RuntimeError("No user tables found after filtering.")

        schema_rows = get_schema_metadata(conn)

        row_count_map: Dict[str, int] = {}
        for tbl in tables:
            table_key = f"{tbl['schema_name']}.{tbl['table_name']}"
            row_count_map[table_key] = get_table_row_count(conn, tbl["schema_name"], tbl["table_name"])

        profiles_by_key: Dict[str, Dict[str, Any]] = {}
        for row in schema_rows:
            table_key = f"{row['schema_name']}.{row['table_name']}"
            row_count = row_count_map.get(table_key, 0)

            profiles_by_key[f"{table_key}.{row['column_name']}"] = get_column_profile(
                conn=conn,
                schema_name=row["schema_name"],
                table_name=row["table_name"],
                column_name=row["column_name"],
                data_type=row["data_type"],
                row_count=row_count
            )

        llm_json = build_llm_metadata(
            database_name=db_name,
            schema_rows=schema_rows,
            profiles_by_key=profiles_by_key
        )

        json_path = OUTPUT_DIR / f"{db_name}_llm_schema_metadata_v5.json"
        txt_path = OUTPUT_DIR / f"{db_name}_llm_schema_context_v5.txt"
        chunked_path = OUTPUT_DIR / f"{db_name}_llm_schema_chunks_v5.json"

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(llm_json, f, indent=2, ensure_ascii=False)

        compact_context = build_compact_prompt_context(llm_json)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(compact_context)

        with open(chunked_path, "w", encoding="utf-8") as f:
            json.dump(llm_json["chunked_payloads"], f, indent=2, ensure_ascii=False)

        log.info("Saved JSON metadata to: %s", json_path.resolve())
        log.info("Saved compact prompt context to: %s", txt_path.resolve())
        log.info("Saved chunked payloads to: %s", chunked_path.resolve())

        return llm_json

    finally:
        conn.close()


# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    metadata = run_schema_extraction_v5()

    print(json.dumps({
        "status": "ok",
        "database_name": metadata["database_name"],
        "version": metadata.get("version"),
        "generator_type": metadata.get("generator_type"),
        "table_count": metadata["table_count"],
        "json_output": str((OUTPUT_DIR / f"{metadata['database_name']}_llm_schema_metadata_v5.json").resolve()),
        "prompt_context_output": str((OUTPUT_DIR / f"{metadata['database_name']}_llm_schema_context_v5.txt").resolve()),
        "chunked_output": str((OUTPUT_DIR / f"{metadata['database_name']}_llm_schema_chunks_v5.json").resolve())
    }, indent=2))

