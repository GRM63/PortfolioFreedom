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
    target_path: str = "Trades_Freedom.xlsx",
    merge: bool = True
) -> Tuple[bool, str, Optional[pd.DataFrame]]:
    """
    Import a trades Excel file from upload.

    Args:
        uploaded_file: File-like object from Streamlit uploader
        target_path: Where to save the imported file
        merge: If True, merge with existing trades; if False, replace

    Returns:
        Tuple of (success, message, DataFrame or None)
    """
    try:
        from trades import load_trades, save_trades

        # Read the uploaded file
        new_df = pd.read_excel(uploaded_file)

        # Normalize columns
        new_df.columns = new_df.columns.str.strip().str.lower()

        # Validate structure
        required_cols = ["ticker", "direction", "price", "quantity"]
        alt_cols = {
            "ticker": ["ticker", "symbol", "instrument"],
            "direction": ["direction", "side", "type"],
            "price": ["price"],
            "quantity": ["quantity", "qty", "shares"],
        }

        # Try to find columns
        found_cols = {}
        for req, alts in alt_cols.items():
            for alt in alts:
                if alt in new_df.columns:
                    found_cols[alt] = req
                    break

        if len(found_cols) < len(required_cols):
            return False, f"Missing required columns. Found: {list(new_df.columns)}", None

        # Rename columns to standard names
        new_df = new_df.rename(columns=found_cols)

        if merge:
            # Load existing trades
            existing_df = load_trades(target_path)

            # Backup existing file
            backup = backup_file(target_path)
            backup_msg = f" (backup: {Path(backup).name})" if backup else ""

            # Merge - avoid duplicates based on trade_id if available
            if "trade#" in new_df.columns:
                new_df = new_df.rename(columns={"trade#": "trade_id"})

            if "trade_id" in new_df.columns and "trade_id" in existing_df.columns:
                existing_ids = set(existing_df["trade_id"].tolist())
                new_df = new_df[~new_df["trade_id"].isin(existing_ids)]

            # Concatenate
            merged_df = pd.concat([existing_df, new_df], ignore_index=True)

            # Save
            uploaded_file.seek(0)
            content = uploaded_file.read()
            with open(target_path, "wb") as f:
                f.write(content)

            added = len(new_df)
            return True, f"Imported {added} new trades{backup_msg}", merged_df
        else:
            # Replace entirely
            backup = backup_file(target_path)
            backup_msg = f" (backup: {Path(backup).name})" if backup else ""

            uploaded_file.seek(0)
            content = uploaded_file.read()
            with open(target_path, "wb") as f:
                f.write(content)

            return True, f"Trades file replaced{backup_msg}", new_df

    except Exception as e:
        return False, f"Import error: {str(e)}", None


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
    """
    Export trades DataFrame to Excel bytes for download.

    Args:
        df: Trades DataFrame

    Returns:
        Excel file as bytes
    """
    output = io.BytesIO()

    # Prepare export DataFrame
    export_df = df.copy()

    # Rename columns
    column_rename = {
        "trade_id": "Trade#",
        "order_id": "Order#",
        "timestamp": "Time",
        "ticker": "Ticker",
        "direction": "Direction",
        "price": "Price",
        "quantity": "Quantity",
        "amount": "Amount",
        "fee": "Fee",
        "profit": "Profit",
    }

    for old, new in column_rename.items():
        if old in export_df.columns:
            export_df = export_df.rename(columns={old: new})

    # Format timestamp
    if "Time" in export_df.columns:
        export_df["Time"] = pd.to_datetime(export_df["Time"]).dt.strftime("%d.%m.%Y %H:%M:%S")

    # Format currency columns
    if "Fee" in export_df.columns:
        export_df["Fee"] = export_df["Fee"].apply(lambda x: f"€{x:.2f}" if pd.notna(x) else "€0")
    if "Profit" in export_df.columns:
        export_df["Profit"] = export_df["Profit"].apply(lambda x: f"€{x:.2f}" if pd.notna(x) else "€0")

    # Sort by time
    if "Time" in export_df.columns:
        export_df = export_df.sort_values("Time", ascending=True)

    export_df.to_excel(output, index=False)
    output.seek(0)

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
