"""Loads a world and splits it into per-bank partitions. A bank agent only ever receives its own BankView."""
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

from . import config


@dataclass(frozen=True)
class World:
    tx: pd.DataFrame
    accounts: pd.DataFrame  # indexed by account id
    rings: list


@dataclass(frozen=True)
class BankView:
    """One bank's data: its own customers, plus transactions touching them (counterparties are visible as raw IDs
    only inside this bank, the way a real bank sees the other side of a payment)."""
    bank: str
    accounts: pd.DataFrame  # own customers only, indexed by id
    tx: pd.DataFrame        # transactions where From Bank or To Bank is this bank
    start: pd.Timestamp


def world_from_frames(tx: pd.DataFrame, accounts: pd.DataFrame, rings: list) -> World:
    tx = tx.copy()
    tx["Timestamp"] = pd.to_datetime(tx["Timestamp"])
    return World(tx=tx, accounts=accounts.set_index("id") if "id" in accounts else accounts, rings=rings)


@lru_cache(maxsize=4)
def load_world(data_dir: Path = config.DATA_DIR) -> World:
    tx = pd.read_csv(data_dir / "transactions.csv")
    acc = pd.read_csv(data_dir / "accounts.csv")
    rings = json.loads((data_dir / "ground_truth_rings.json").read_text())
    return world_from_frames(tx, acc, rings)


def partition(world: World, bank: str) -> BankView:
    tx = world.tx
    view = tx[(tx["From Bank"] == bank) | (tx["To Bank"] == bank)].drop(columns=["Is Laundering", "Ring ID"],
                                                                        errors="ignore")
    own = world.accounts[world.accounts["bank"] == bank]
    return BankView(bank=bank, accounts=own, tx=view.reset_index(drop=True), start=tx["Timestamp"].min().normalize())
