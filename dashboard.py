"""Streamlit dashboard for immune-cell analysis."""
import plotly.express as px
import streamlit as st

from analysis import (
    DB_PATH,
    DEFAULT_BASELINE_TIME,
    DEFAULT_CONDITION,
    DEFAULT_SAMPLE_TYPE,
    DEFAULT_TREATMENT,
    POPULATIONS,
    baseline_breakdown,
    baseline_subset,
    compute_frequencies,
    distinct_values,
    filter_frequencies,
    get_connection,
    responder_comparison_data,
    run_statistics,
    sample_metadata,
)

st.set_page_config(page_title="Immune Cell Population Dashboard", layout="wide")

if not DB_PATH.exists():
    st.error(f"Database not found at {DB_PATH}. Run `python load_data.py` first.")
    st.stop()

conn = get_connection()
st.title("Immune Cell Population Dashboard")


def option_select(label, options, default=None, key=None):
    choices = ["All"] + list(options)
    index = choices.index(default) if default in choices else 0
    return st.selectbox(label, choices, index=index, key=key)


frequencies_tab, response_tab, baseline_tab = st.tabs(
    ["Frequencies", "Responder Analysis", "Baseline Subset"]
)

with frequencies_tab:
    st.header("Relative frequency of each cell population per sample")

    meta_df = sample_metadata(conn)
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        project = option_select("Project", distinct_values(conn, "subjects", "project"), key="freq_project")
    with f2:
        condition = option_select("Condition", distinct_values(conn, "subjects", "condition"), key="freq_condition")
    with f3:
        treatment = option_select("Treatment", distinct_values(conn, "subjects", "treatment"), key="freq_treatment")
    with f4:
        sample_type = option_select("Sample type", distinct_values(conn, "samples", "sample_type"), key="freq_sample_type")

    freq_df = compute_frequencies(conn)
    freq_df = filter_frequencies(
        freq_df, meta_df, project=project, condition=condition, treatment=treatment, sample_type=sample_type
    )

    st.dataframe(freq_df, use_container_width=True)
    st.download_button("Download as CSV", freq_df.to_csv(index=False), "frequencies.csv")

    st.subheader("Population composition")
    population_choice = st.multiselect(
        "Populations to plot", POPULATIONS, default=list(POPULATIONS), key="freq_populations"
    )
    plot_df = freq_df[freq_df["population"].isin(population_choice)]
    if not plot_df.empty:
        fig = px.box(
            plot_df,
            x="population",
            y="percentage",
            points="all",
            hover_data=["sample", "count", "total_count"],
            labels={"percentage": "% of total cells", "population": "Population"},
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No samples match the selected filters.")

with response_tab:
    st.header("Responders vs Non-responders")
    st.caption("Defaults to the assignment cohort: melanoma, miraclib, PBMC.")

    c1, c2, c3 = st.columns(3)
    with c1:
        condition = st.selectbox(
            "Condition", distinct_values(conn, "subjects", "condition"),
            index=distinct_values(conn, "subjects", "condition").index(DEFAULT_CONDITION),
            key="resp_condition",
        )
    with c2:
        treatment = st.selectbox(
            "Treatment", distinct_values(conn, "subjects", "treatment"),
            index=distinct_values(conn, "subjects", "treatment").index(DEFAULT_TREATMENT),
            key="resp_treatment",
        )
    with c3:
        sample_type = st.selectbox(
            "Sample type", distinct_values(conn, "samples", "sample_type"),
            index=distinct_values(conn, "samples", "sample_type").index(DEFAULT_SAMPLE_TYPE),
            key="resp_sample_type",
        )

    population_choice = st.multiselect(
        "Populations to compare", POPULATIONS, default=list(POPULATIONS), key="resp_populations"
    )

    merged = responder_comparison_data(
        conn, compute_frequencies(conn), condition=condition, treatment=treatment, sample_type=sample_type
    )
    merged = merged[merged["population"].isin(population_choice)]

    if merged.empty or merged["response"].nunique() < 2:
        st.warning("Not enough responder/non-responder samples for this combination of filters.")
    else:
        st.subheader("Boxplots by population")
        fig = px.box(
            merged,
            x="population",
            y="percentage",
            color="response",
            points="all",
            hover_data=["sample"],
            category_orders={"response": ["no", "yes"]},
            labels={"percentage": "% of total cells", "response": "Response"},
        )
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Statistical significance (Mann-Whitney U)")
        alpha = st.slider("Significance threshold (alpha)", 0.01, 0.10, 0.05, 0.01, key="resp_alpha")
        stats_df = run_statistics(merged, populations=population_choice)
        stats_df["significant"] = stats_df["p_value"] < alpha
        st.dataframe(stats_df.drop(columns=["significant_p<0.05"]), use_container_width=True)

        significant = stats_df.loc[stats_df["significant"], "population"].tolist()
        if significant:
            st.success(f"Significant populations (p < {alpha}): {', '.join(significant)}")
        else:
            st.info(f"No populations reached significance at p < {alpha}.")

with baseline_tab:
    st.header("Baseline samples")

    b1, b2, b3, b4 = st.columns(4)
    with b1:
        condition = st.selectbox(
            "Condition", distinct_values(conn, "subjects", "condition"),
            index=distinct_values(conn, "subjects", "condition").index(DEFAULT_CONDITION),
            key="base_condition",
        )
    with b2:
        treatment = st.selectbox(
            "Treatment", distinct_values(conn, "subjects", "treatment"),
            index=distinct_values(conn, "subjects", "treatment").index(DEFAULT_TREATMENT),
            key="base_treatment",
        )
    with b3:
        sample_type = st.selectbox(
            "Sample type", distinct_values(conn, "samples", "sample_type"),
            index=distinct_values(conn, "samples", "sample_type").index(DEFAULT_SAMPLE_TYPE),
            key="base_sample_type",
        )
    with b4:
        time_options = distinct_values(conn, "samples", "time_from_treatment_start")
        time_point = st.selectbox(
            "Time from treatment start",
            time_options,
            index=time_options.index(DEFAULT_BASELINE_TIME) if DEFAULT_BASELINE_TIME in time_options else 0,
            key="base_time",
        )

    subset = baseline_subset(
        conn, condition=condition, treatment=treatment, sample_type=sample_type,
        time_from_treatment_start=time_point,
    )
    st.dataframe(subset, use_container_width=True)
    st.download_button("Download as CSV", subset.to_csv(index=False), "baseline_subset.csv")

    if subset.empty:
        st.info("No samples match the selected filters.")
    else:
        breakdown = baseline_breakdown(subset)
        project_col, response_col, sex_col = st.columns(3)
        with project_col:
            st.subheader("Samples per project")
            st.plotly_chart(
                px.bar(breakdown["by_project"], x="project", y="sample_count"),
                use_container_width=True,
            )
        with response_col:
            st.subheader("Subjects by response")
            st.plotly_chart(
                px.pie(breakdown["by_response"], names="response", values="subject_count"),
                use_container_width=True,
            )
        with sex_col:
            st.subheader("Subjects by sex")
            st.plotly_chart(
                px.pie(breakdown["by_sex"], names="sex", values="subject_count"),
                use_container_width=True,
            )
