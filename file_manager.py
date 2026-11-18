"""
File management module for importing and exporting Excel files.
Handles portfolio and trades data import/export.
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, BinaryIO
import shutil
import io

from trades import (
    TRADES_FILE,
    empty_trades,
    load_trades,
    normalize_trades,
    save_trades,
    to_export_frame,
)


def backup_file(file_path: str) -> Optional[str]:
    """
    Create a backup of an existing file.

    Args:
        file_path: Path to the file to backup

    Returns:
        Path to backup file, or None if original doesn't exist
    """
    path = Path(file_path)
    if not path.exists():
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = path.parent / f"{path.stem}_backup_{timestamp}{path.suffix}"

    shutil.copy2(file_path, backup_path)
    return str(backup_path)


def import_portfolio_excel(
    uploaded_file: BinaryIO,
    target_path: str = "Portfolio_22012026.xlsx"
) -> Tuple[bool, str, Optional[pd.DataFrame]]:
    """
    Import a portfolio Excel file from upload.

    Args:
        uploaded_file: File-like object from Streamlit uploader
        target_path: Where to save the imported file

    Returns:
        Tuple of (success, message, DataFrame or None)
    """
    try:
        # Read the uploaded file
        df = pd.read_excel(uploaded_file)

        # Validate structure - check for expected columns
        df.columns = df.columns.str.strip().str.lower()
        required_cols = ["ticker", "qty"]

        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            return False, f"Missing required columns: {missing}", None

        # Backup existing file
        backup = backup_file(target_path)
        backup_msg = f" (backup: {Path(backup).name})" if backup else ""

        # Save the new file
        # Re-read to preserve original formatting
        uploaded_file.seek(0)
        content = uploaded_file.read()

        with open(target_path, "wb") as f:
            f.write(content)

        return True, f"Portfolio imported successfully{backup_msg}", df

    except Exception as e:
        return False, f"Import error: {str(e)}", None


def import_trades_excel(
    uploaded_file: BinaryIO,
    target_path: str = TRADES_FILE,
    merge: bool = True
) -> Tuple[bool, str, Optional[pd.DataFrame]]:
    """
    Import a trades Excel file from upload.

    The upload is normalized (column aliases, dates, currency strings) and the
    result is written with save_trades, so the file on disk is always in the
    standard layout that load_trades expects.

    Args:
        uploaded_file: File-like object from Streamlit uploader
        target_path: Where to save the imported file
        merge: If True, merge with existing trades; if False, replace

    Returns:
        Tuple of (success, message, DataFrame or None)
    """
    try:
        new_df = normalize_trades(pd.read_excel(uploaded_file))
    except ValueError as e:
        return False, str(e), None
    except Exception as e:
        return False, f"Import error: {e}", None

    try:
        if merge:
            existing_df = load_trades(target_path)

            # Skip trades that already exist (matched on trade_id)
            if "trade_id" in new_df.columns and not existing_df.empty:
                known_ids = set(existing_df["trade_id"]) - {0}
                new_df = new_df[~new_df["trade_id"].isin(known_ids)]

            frames = [f for f in (existing_df, new_df) if not f.empty]
            result_df = pd.concat(frames, ignore_index=True) if frames else empty_trades()
            message = f"Imported {len(new_df)} new trades"
        else:
            result_df = new_df
            message = "Trades file replaced"

        backup = backup_file(target_path)
        if not save_trades(result_df, target_path):
            return False, "Failed to write trades file", None

        if backup:
            message += f" (backup: {Path(backup).name})"
        return True, message, result_df

    except Exception as e:
        return False, f"Import error: {e}", None


def export_portfolio_excel(df: pd.DataFrame) -> bytes:
    """
    Export portfolio DataFrame to Excel bytes for download.

    Args:
        df: Portfolio DataFrame

    Returns:
        Excel file as bytes
    """
    output = io.BytesIO()

    # Prepare export DataFrame
    export_df = df.copy()

    # Rename columns to user-friendly names
    column_rename = {
        "ticker": "Ticker",
        "quantity": "Qty",
        "entry_price": "Entry Price",
        "platform_price": "Price",
        "platform_value": "Value",
        "platform_profit": "Profit",
        "platform_growth": "Growth",
        "entry_value": "Entry Value",
    }

    for old, new in column_rename.items():
        if old in export_df.columns:
            export_df = export_df.rename(columns={old: new})

    # Remove internal columns
    cols_to_remove = ["yf_ticker", "platform_share"]
    for col in cols_to_remove:
        if col in export_df.columns:
            export_df = export_df.drop(columns=[col])

    export_df.to_excel(output, index=False)
    output.seek(0)

    return output.getvalue()


def export_trades_excel(df: pd.DataFrame) -> bytes:
    """Export trades DataFrame to Excel bytes for download."""
    output = io.BytesIO()
    to_export_frame(df).to_excel(output, index=False)
    return output.getvalue()


def get_file_info(file_path: str) -> Optional[dict]:
    """
    Get information about a file.

    Returns dict with:
    - exists: bool
    - size: file size in bytes
    - modified: last modified datetime
    - name: file name
    """
    path = Path(file_path)

    if not path.exists():
        return None

    stat = path.stat()

    return {
        "exists": True,
        "size": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime),
        "name": path.name,
    }


def list_backup_files(directory: str = ".") -> list:
    """
    List all backup files in a directory.

    Returns list of dicts with file info.
    """
    path = Path(directory)
    backups = []

    for f in path.glob("*_backup_*"):
        if f.is_file():
            stat = f.stat()
            backups.append({
                "name": f.name,
                "path": str(f),
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime),
            })

    # Sort by modified time descending
    backups.sort(key=lambda x: x["modified"], reverse=True)

    return backups
