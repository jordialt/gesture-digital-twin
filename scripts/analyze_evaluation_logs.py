"""Summarise HRI evaluation CSV logs as LaTeX tables.

The script expects logs produced by ``RuntimeCsvLogger`` and reports:

* FPS mean/min/max.
* Processing latency mean/min/max.
* Recognised command counts by evaluation case and mode.

Example:
    python scripts/analyze_evaluation_logs.py data/raw_logs
    python scripts/analyze_evaluation_logs.py data/raw_logs --output results/evaluation_tables.tex
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import pandas as pd


REQUIRED_COLUMNS = {
    "fps",
    "processing_latency_ms",
    "current_mode",
}

DEFAULT_COMMAND_COLUMN = "emitted_command"
UNGROUPED_CASE = "Ungrouped"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create academic LaTeX tables from HRI evaluation CSV logs."
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        type=Path,
        default=[Path("data/raw_logs")],
        help="CSV file(s) or directories containing CSV logs. Defaults to data/raw_logs.",
    )
    parser.add_argument(
        "--command-column",
        default=DEFAULT_COMMAND_COLUMN,
        help=(
            "Column used for command counts. The default, emitted_command, counts "
            "one-shot stable recognitions rather than every frame a command is held."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional .tex file where the generated LaTeX tables will be written.",
    )
    parser.add_argument(
        "--digits",
        type=int,
        default=2,
        help="Number of decimal places for numeric metrics. Defaults to 2.",
    )
    return parser.parse_args()


def discover_csv_files(inputs: Iterable[Path]) -> list[Path]:
    csv_files: list[Path] = []

    for input_path in inputs:
        if input_path.is_dir():
            csv_files.extend(sorted(input_path.rglob("*.csv")))
        elif input_path.is_file() and input_path.suffix.lower() == ".csv":
            csv_files.append(input_path)
        else:
            raise FileNotFoundError(f"No CSV log found at: {input_path}")

    unique_files = sorted(dict.fromkeys(csv_files))
    if not unique_files:
        raise FileNotFoundError("No CSV files were found in the supplied input path(s).")

    return unique_files


def load_logs(csv_files: Iterable[Path], command_column: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    required_columns = REQUIRED_COLUMNS | {command_column}

    for csv_file in csv_files:
        frame = pd.read_csv(csv_file)
        missing_columns = sorted(required_columns - set(frame.columns))
        if missing_columns:
            missing = ", ".join(missing_columns)
            raise ValueError(f"{csv_file} is missing required column(s): {missing}")

        frame = frame.copy()
        frame["case"] = case_name_from_path(csv_file)
        frame["run"] = csv_file.stem
        frame["source_file"] = str(csv_file)
        frames.append(frame)

    logs = pd.concat(frames, ignore_index=True)
    logs["fps"] = pd.to_numeric(logs["fps"], errors="coerce")
    logs["processing_latency_ms"] = pd.to_numeric(
        logs["processing_latency_ms"], errors="coerce"
    )

    logs = logs.dropna(subset=["fps", "processing_latency_ms"])
    if logs.empty:
        raise ValueError("No valid numeric FPS or latency rows were found.")

    return logs


def case_name_from_path(csv_file: Path) -> str:
    parent_name = csv_file.parent.name
    if parent_name in {"", ".", "raw_logs"}:
        return UNGROUPED_CASE
    return format_case_name(parent_name)


def format_case_name(name: str) -> str:
    special_words = {
        "2d": "2D",
        "3d": "3D",
        "csv": "CSV",
        "fps": "FPS",
        "hri": "HRI",
        "id": "ID",
    }
    words = []
    for word in name.replace("-", "_").split("_"):
        if not word:
            continue
        words.append(special_words.get(word.lower(), word.capitalize()))
    return " ".join(words) or UNGROUPED_CASE


def latex_escape(value: object) -> str:
    text = str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in text)


def format_number(value: object, digits: int) -> str:
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return latex_escape(value)


def dataframe_to_latex_table(
    frame: pd.DataFrame,
    *,
    caption: str,
    label: str,
    alignment: str,
    digits: int,
) -> str:
    header = " & ".join(latex_escape(column) for column in frame.columns) + r" \\"
    lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        rf"\caption{{{latex_escape(caption)}}}",
        rf"\label{{{latex_escape(label)}}}",
        rf"\begin{{tabular}}{{{alignment}}}",
        r"\toprule",
        header,
        r"\midrule",
    ]

    for _, row in frame.iterrows():
        formatted_values = [format_number(value, digits) for value in row.to_list()]
        lines.append(" & ".join(formatted_values) + r" \\")

    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{table}",
        ]
    )
    return "\n".join(lines)


def build_performance_table(logs: pd.DataFrame, digits: int) -> str:
    grouped = (
        logs.groupby("case", sort=True)
        .agg(
            Runs=("source_file", "nunique"),
            Frames=("fps", "size"),
            **{
                "Average FPS": ("fps", "mean"),
                "Minimum FPS": ("fps", "min"),
                "Maximum FPS": ("fps", "max"),
                "Average Latency (ms)": ("processing_latency_ms", "mean"),
                "Minimum Latency (ms)": ("processing_latency_ms", "min"),
                "Maximum Latency (ms)": ("processing_latency_ms", "max"),
            },
        )
        .reset_index()
        .rename(columns={"case": "Case"})
    )

    overall = pd.DataFrame(
        [
            {
                "Case": "Overall",
                "Runs": logs["source_file"].nunique(),
                "Frames": len(logs),
                "Average FPS": logs["fps"].mean(),
                "Minimum FPS": logs["fps"].min(),
                "Maximum FPS": logs["fps"].max(),
                "Average Latency (ms)": logs["processing_latency_ms"].mean(),
                "Minimum Latency (ms)": logs["processing_latency_ms"].min(),
                "Maximum Latency (ms)": logs["processing_latency_ms"].max(),
            }
        ]
    )
    table = pd.concat([grouped, overall], ignore_index=True)

    return dataframe_to_latex_table(
        table,
        caption="Runtime performance metrics by physical evaluation case.",
        label="tab:runtime-performance",
        alignment="lrrrrrrrr",
        digits=digits,
    )


def build_command_count_table(
    logs: pd.DataFrame, command_column: str, digits: int
) -> str:
    commands = logs.copy()
    commands[command_column] = commands[command_column].fillna("").astype(str).str.strip()
    commands = commands[commands[command_column] != ""]

    if commands.empty:
        table = pd.DataFrame(
            columns=["Case", "Mode", "Recognized Command", "Count"],
            data=[[UNGROUPED_CASE, "No recognized commands", "-", 0]],
        )
    else:
        table = (
            commands.groupby(["case", "current_mode", command_column], sort=True)
            .size()
            .reset_index(name="Count")
            .rename(
                columns={
                    "case": "Case",
                    "current_mode": "Mode",
                    command_column: "Recognized Command",
                }
            )
        )

        totals = (
            commands.groupby(["case", "current_mode"], sort=True)
            .size()
            .reset_index(name="Count")
            .rename(columns={"case": "Case", "current_mode": "Mode"})
        )
        totals["Recognized Command"] = "Total"
        table = pd.concat([table, totals], ignore_index=True)
        table = table[["Case", "Mode", "Recognized Command", "Count"]].sort_values(
            ["Case", "Mode", "Recognized Command"]
        )

    return dataframe_to_latex_table(
        table,
        caption="Recognized command counts by evaluation case and control mode.",
        label="tab:recognized-commands-by-mode",
        alignment="lllr",
        digits=digits,
    )


def main() -> None:
    args = parse_args()
    csv_files = discover_csv_files(args.inputs)
    logs = load_logs(csv_files, args.command_column)

    latex_output = "\n\n".join(
        [
            build_performance_table(logs, args.digits),
            build_command_count_table(logs, args.command_column, args.digits),
        ]
    )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(latex_output + "\n", encoding="utf-8")

    print(latex_output)


if __name__ == "__main__":
    main()
