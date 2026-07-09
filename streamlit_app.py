from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="AAA Arbitration Data Explorer", layout="wide")
st.title("⚖️ AAA Arbitration Data Explorer")

SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".xlsm", ".xltx", ".xltm", ".json", ".parquet"}


def load_data(uploaded_file=None, file_path=None):
    if uploaded_file is not None:
        source_name = uploaded_file.name
        file_extension = Path(source_name).suffix.lower()
        file_handle = uploaded_file
    elif file_path is not None:
        source_name = Path(file_path).name
        file_extension = Path(file_path).suffix.lower()
        file_handle = file_path
    else:
        raise ValueError("No file provided.")

    if file_extension == ".csv":
        return pd.read_csv(file_handle), source_name
    if file_extension in {".xlsx", ".xlsm", ".xltx", ".xltm", ".xls"}:
        return pd.read_excel(file_handle), source_name
    if file_extension == ".json":
        return pd.read_json(file_handle), source_name
    if file_extension == ".parquet":
        return pd.read_parquet(file_handle), source_name

    raise ValueError("Unsupported file type. Please use a CSV, Excel, JSON, or Parquet file.")


def find_local_data_file(base_directory):
    search_directories = [
        base_directory,
        base_directory / "data",
        base_directory / "files",
    ]
    for directory in search_directories:
        if directory.exists():
            for candidate in sorted(directory.iterdir()):
                if candidate.is_file() and candidate.suffix.lower() in SUPPORTED_EXTENSIONS:
                    return candidate

    for candidate in sorted(base_directory.rglob("*")):
        if candidate.is_file() and candidate.suffix.lower() in SUPPORTED_EXTENSIONS:
            return candidate
    return None


workspace_root = Path(__file__).resolve().parent
local_data_file = find_local_data_file(workspace_root)

# Parquet cache directory and loader
CACHE_DIR = workspace_root / ".cache"
CACHE_DIR.mkdir(exist_ok=True)

@st.cache_data
def load_cached_table(excel_path_str: str, parquet_path_str: str, excel_mtime: float):
    """Load dataframe from Parquet if available, otherwise read from Excel and cache as Parquet."""
    excel_path = Path(excel_path_str)
    parquet_path = Path(parquet_path_str)

    if parquet_path.exists():
        try:
            df = pd.read_parquet(parquet_path)
            return df, parquet_path.name
        except Exception:
            pass

    if excel_path.exists():
        df = pd.read_excel(excel_path, engine="openpyxl")
        try:
            df.to_parquet(parquet_path, index=False)
        except Exception:
            pass
        return df, excel_path.name

    raise FileNotFoundError(f"No readable data file found at {excel_path} or {parquet_path}")

# Auto-load specific filename if present, preferring Parquet over Excel
auto_excel = workspace_root / ".devcontainer" / "aaa.xlsx"
auto_parquet = workspace_root / ".devcontainer" / "aaa.parquet"
if auto_parquet.exists() and auto_parquet.is_file():
    try:
        df = pd.read_parquet(auto_parquet)
        source_name = auto_parquet.name
    except Exception as exc:
        st.error(f"Unable to read auto-loaded Parquet file {auto_parquet}: {exc}")
        df = None
        source_name = None
elif auto_excel.exists() and auto_excel.is_file():
    parquet_file = CACHE_DIR / f"{auto_excel.stem}.parquet"
    excel_mtime = auto_excel.stat().st_mtime
    try:
        df, source_name = load_cached_table(str(auto_excel), str(parquet_file), excel_mtime)
    except Exception as exc:
        st.error(f"Unable to read auto-loaded file {auto_excel}: {exc}")
        df = None
        source_name = None
else:
    df = None
    source_name = None

if df is None:
    file_path_input = st.text_input(
        "Path to your file",
        value=str(local_data_file) if local_data_file else "",
        placeholder="/workspaces/AAAArbitrationData/your-file.xlsx",
    )
    load_file = st.button("Load file")

    if load_file and file_path_input:
        file_path = Path(file_path_input).expanduser().resolve()
        if file_path.exists() and file_path.is_file():
            parquet_file = CACHE_DIR / f"{file_path.stem}.parquet"
            excel_mtime = file_path.stat().st_mtime
            try:
                df, source_name = load_cached_table(str(file_path), str(parquet_file), excel_mtime)
            except Exception as exc:
                st.error(f"Unable to read the file at the provided path: {exc}")
                st.stop()

            st.success(f"Loaded {source_name} from the provided path (cached) with {len(df)} rows and {len(df.columns)} columns.")
        else:
            st.info("The file path you entered does not exist yet. Please verify it and try again.")
            st.stop()
    elif local_data_file is not None and not file_path_input:
        try:
            df, source_name = load_data(file_path=local_data_file)
        except Exception as exc:
            st.error(f"Unable to read the local file: {exc}")
            st.stop()

        st.success(f"Loaded {source_name} from the workspace with {len(df)} rows and {len(df.columns)} columns.")
    else:
        st.info("Enter the full path to your .xlsx file above and click Load file.")
        st.stop()

# Full-table search/filtering over text-like columns only
search_text = st.text_input("Search (substring across all columns)", value="Thomas James Homes")
if search_text:
    with st.spinner("Searching across all rows..."):
        s = search_text.strip()
        text_columns = [
            col
            for col in df.columns
            if pd.api.types.is_object_dtype(df[col])
            or pd.api.types.is_string_dtype(df[col])
            or pd.api.types.is_categorical_dtype(df[col])
        ]
        if not text_columns:
            df_filtered = df
        else:
            mask = pd.Series(False, index=df.index)
            for col in text_columns:
                mask |= df[col].fillna("").astype(str).str.contains(s, case=False, na=False, regex=False)
            df_filtered = df[mask]
    st.info(f"Showing {len(df_filtered)} of {len(df)} rows matching '{s}'")
else:
    df_filtered = df

st.subheader("Data preview")
show_all = st.checkbox("Show all rows (may be slow for large datasets)")
if show_all:
    st.warning("Rendering all rows may be slow in the browser — consider downloading or using filters.")
    st.dataframe(df_filtered, use_container_width=True)
else:
    rows = st.number_input("Preview rows", min_value=10, max_value=10000, value=100, step=10)
    st.dataframe(df_filtered.head(rows), use_container_width=True)

