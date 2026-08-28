"""Query and analysis helpers for Parts 2-4.

Shared by dashboard.py (live queries) and the CLI entry point below
(batch regeneration of everything under output/).
"""
import sqlite3
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from scipy.stats import mannwhitneyu

REPO_ROOT = Path(__file__).resolve().parent
DB_PATH = REPO_ROOT / "cell_counts.db"
OUTPUT_DIR = REPO_ROOT / "output"

POPULATIONS = ("b_cell", "cd8_t_cell", "cd4_t_cell", "nk_cell", "monocyte")

# Defaults matching the assignment's Part 3 / Part 4 cohort definition.
DEFAULT_CONDITION = "melanoma"
DEFAULT_TREATMENT = "miraclib"
DEFAULT_SAMPLE_TYPE = "PBMC"
DEFAULT_BASELINE_TIME = 0


def get_connection(db_path=DB_PATH):
    return sqlite3.connect(db_path)


def distinct_values(conn, table: str, column: str) -> list:
    rows = conn.execute(f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL ORDER BY {column}")
    return [row[0] for row in rows.fetchall()]


# --- Part 2: relative frequencies ------------------------------------------

def compute_frequencies(conn) -> pd.DataFrame:
    counts = pd.read_sql_query(
        "SELECT sample_id AS sample, population, count FROM cell_counts", conn
    )
    counts["total_count"] = counts.groupby("sample")["count"].transform("sum")
    counts["percentage"] = 100 * counts["count"] / counts["total_count"]
    ordered_cols = ["sample", "total_count", "population", "count", "percentage"]
    return counts[ordered_cols].sort_values(["sample", "population"]).reset_index(drop=True)


def filter_frequencies(freq_df: pd.DataFrame, meta_df: pd.DataFrame, **filters) -> pd.DataFrame:
    """Restrict a frequencies table to samples matching metadata filters.

    filters: any of project=, condition=, treatment=, sample_type= (value "All" is a no-op).
    """
    allowed_samples = meta_df
    for column, value in filters.items():
        if value and value != "All":
            allowed_samples = allowed_samples[allowed_samples[column] == value]
    return freq_df[freq_df["sample"].isin(allowed_samples["sample"])]


def sample_metadata(conn) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT s.sample_id AS sample, s.sample_type, s.time_from_treatment_start,
               sub.subject_id, sub.project, sub.condition, sub.treatment, sub.response, sub.sex, sub.age
        FROM samples s
        JOIN subjects sub ON sub.subject_id = s.subject_id
        """,
        conn,
    )


# --- Part 3: responders vs non-responders -----------------------------------

def responder_comparison_data(
    conn,
    freq_df: pd.DataFrame,
    condition: str = DEFAULT_CONDITION,
    treatment: str = DEFAULT_TREATMENT,
    sample_type: str = DEFAULT_SAMPLE_TYPE,
) -> pd.DataFrame:
    cohort_meta = pd.read_sql_query(
        """
        SELECT s.sample_id AS sample, sub.condition, sub.treatment, sub.response, s.sample_type
        FROM samples s
        JOIN subjects sub ON sub.subject_id = s.subject_id
        WHERE sub.condition = ?
          AND sub.treatment = ?
          AND s.sample_type = ?
        """,
        conn,
        params=(condition, treatment, sample_type),
    )
    return freq_df.merge(cohort_meta, on="sample", how="inner")


def run_statistics(merged: pd.DataFrame, populations=POPULATIONS) -> pd.DataFrame:
    results = []
    for population in populations:
        rows = merged[merged["population"] == population]
        responder_pct = rows.loc[rows["response"] == "yes", "percentage"]
        non_responder_pct = rows.loc[rows["response"] == "no", "percentage"]
        u_stat, p_value = mannwhitneyu(responder_pct, non_responder_pct, alternative="two-sided")
        results.append(
            {
                "population": population,
                "n_responders": responder_pct.size,
                "n_non_responders": non_responder_pct.size,
                "median_responder_pct": responder_pct.median(),
                "median_non_responder_pct": non_responder_pct.median(),
                "u_statistic": u_stat,
                "p_value": p_value,
                "significant_p<0.05": p_value < 0.05,
            }
        )
    return pd.DataFrame(results)


def plot_boxplots(merged: pd.DataFrame, destination: Path, populations=POPULATIONS):
    fig, axes = plt.subplots(1, len(populations), figsize=(4 * len(populations), 5), sharey=False)
    if len(populations) == 1:
        axes = [axes]
    for axis, population in zip(axes, populations):
        rows = merged[merged["population"] == population]
        grouped = [
            rows.loc[rows["response"] == "no", "percentage"],
            rows.loc[rows["response"] == "yes", "percentage"],
        ]
        axis.boxplot(grouped, tick_labels=["non-responder", "responder"])
        axis.set_title(population)
        axis.set_ylabel("% of total cells")
    fig.suptitle("Cell population frequencies: responders vs non-responders\n(melanoma, miraclib, PBMC)")
    fig.tight_layout()
    fig.savefig(destination, dpi=150)
    plt.close(fig)


# --- Part 4: baseline subset -------------------------------------------------

def baseline_subset(
    conn,
    condition: str = DEFAULT_CONDITION,
    treatment: str = DEFAULT_TREATMENT,
    sample_type: str = DEFAULT_SAMPLE_TYPE,
    time_from_treatment_start: int = DEFAULT_BASELINE_TIME,
) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT s.sample_id AS sample, sub.subject_id, sub.project, sub.condition,
               sub.treatment, sub.response, sub.sex, s.sample_type, s.time_from_treatment_start
        FROM samples s
        JOIN subjects sub ON sub.subject_id = s.subject_id
        WHERE sub.condition = ?
          AND sub.treatment = ?
          AND s.sample_type = ?
          AND s.time_from_treatment_start = ?
        """,
        conn,
        params=(condition, treatment, sample_type, time_from_treatment_start),
    )


def baseline_breakdown(subset: pd.DataFrame) -> dict:
    samples_per_project = (
        subset.groupby("project")["sample"].count().rename("sample_count").reset_index()
    )

    unique_subjects = subset.drop_duplicates("subject_id")
    subjects_by_response = (
        unique_subjects["response"].value_counts().rename_axis("response").reset_index(name="subject_count")
    )
    subjects_by_sex = (
        unique_subjects["sex"].value_counts().rename_axis("sex").reset_index(name="subject_count")
    )

    return {
        "by_project": samples_per_project,
        "by_response": subjects_by_response,
        "by_sex": subjects_by_sex,
    }


# --- CLI: regenerate everything under output/ -------------------------------

def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    conn = get_connection()

    freq_df = compute_frequencies(conn)
    freq_df.to_csv(OUTPUT_DIR / "frequencies.csv", index=False)
    print(f"Part 2: wrote {OUTPUT_DIR / 'frequencies.csv'} ({len(freq_df)} rows)")

    merged = responder_comparison_data(conn, freq_df)
    stats_df = run_statistics(merged)
    stats_df.to_csv(OUTPUT_DIR / "stats_summary.csv", index=False)
    plot_boxplots(merged, OUTPUT_DIR / "boxplots_responder_vs_nonresponder.png")
    significant = stats_df.loc[stats_df["significant_p<0.05"], "population"].tolist()
    print(f"Part 3: wrote stats_summary.csv and boxplot figure; significant populations: {significant or 'none'}")

    subset = baseline_subset(conn)
    subset.to_csv(OUTPUT_DIR / "baseline_subset.csv", index=False)
    breakdown = baseline_breakdown(subset)
    with open(OUTPUT_DIR / "baseline_breakdown.csv", "w") as handle:
        for section_name, section_df in breakdown.items():
            handle.write(f"# {section_name}\n")
            section_df.to_csv(handle, index=False)
            handle.write("\n")
    print(f"Part 4: wrote baseline_subset.csv ({len(subset)} rows) and baseline_breakdown.csv")

    conn.close()


if __name__ == "__main__":
    main()
