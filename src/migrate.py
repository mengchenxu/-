"""数据迁移 — 旧 JSON → 新 store.json（委托给 Store.migrate_from_old_files）"""
import logging

from src.store import Store

logger = logging.getLogger(__name__)


def migrate(data_dir: str = "data") -> Store:
    """从旧的 users.json / group_memories.json 迁移到 store.json。幂等。"""
    path = f"{data_dir}/store.json" if "/" in data_dir or "\\" in data_dir else f"{data_dir}/store.json".replace("\\", "/")
    return Store.migrate_from_old_files(f"{data_dir}/store.json")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    store = migrate()
    print(f"Migration complete: {len(store._people)} people, {len(store._groups)} groups")
