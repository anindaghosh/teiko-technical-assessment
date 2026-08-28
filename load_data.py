"""Build cell_counts.db from cell-count.csv (Part 1)."""
import csv
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
SOURCE_CSV = REPO_ROOT / "cell-count.csv"
DATABASE_FILE = REPO_ROOT / "cell_counts.db"

CELL_POPULATIONS = ("b_cell", "cd8_t_cell", "cd4_t_cell", "nk_cell", "monocyte")

DDL = """
CREATE TABLE subjects (
    subject_id  TEXT PRIMARY KEY,
    project     TEXT NOT NULL,
    condition   TEXT NOT NULL,
    age         INTEGER,
    sex         TEXT,
    treatment   TEXT,
    response    TEXT
);

CREATE TABLE samples (
    sample_id                  TEXT PRIMARY KEY,
    subject_id                 TEXT NOT NULL REFERENCES subjects(subject_id),
    sample_type                TEXT NOT NULL,
    time_from_treatment_start  INTEGER
);

CREATE TABLE cell_counts (
    sample_id   TEXT NOT NULL REFERENCES samples(sample_id),
    population  TEXT NOT NULL,
    count       INTEGER NOT NULL,
    PRIMARY KEY (sample_id, population)
);

CREATE INDEX idx_samples_subject ON samples(subject_id);
CREATE INDEX idx_cellcounts_sample ON cell_counts(sample_id);
CREATE INDEX idx_subjects_filters ON subjects(project, condition, treatment);
"""


def build_database():
    if DATABASE_FILE.exists():
        DATABASE_FILE.unlink()

    conn = sqlite3.connect(DATABASE_FILE)
    conn.executescript(DDL)

    seen_subjects = set()
    with open(SOURCE_CSV, newline="") as handle:
        for record in csv.DictReader(handle):
            subject_id = record["subject"]

            if subject_id not in seen_subjects:
                seen_subjects.add(subject_id)
                conn.execute(
                    """INSERT INTO subjects (subject_id, project, condition, age, sex, treatment, response)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        subject_id,
                        record["project"],
                        record["condition"],
                        int(record["age"]) if record["age"] else None,
                        record["sex"],
                        record["treatment"],
                        record["response"] or None,
                    ),
                )

            conn.execute(
                """INSERT INTO samples (sample_id, subject_id, sample_type, time_from_treatment_start)
                   VALUES (?, ?, ?, ?)""",
                (
                    record["sample"],
                    subject_id,
                    record["sample_type"],
                    int(record["time_from_treatment_start"])
                    if record["time_from_treatment_start"] != ""
                    else None,
                ),
            )

            conn.executemany(
                "INSERT INTO cell_counts (sample_id, population, count) VALUES (?, ?, ?)",
                [(record["sample"], population, int(record[population])) for population in CELL_POPULATIONS],
            )

    conn.commit()

    subject_count, sample_count, count_rows = (
        conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("subjects", "samples", "cell_counts")
    )
    conn.close()
    print(f"Loaded {subject_count} subjects, {sample_count} samples, {count_rows} cell count rows into {DATABASE_FILE.name}")


if __name__ == "__main__":
    build_database()
