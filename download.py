import csv
import argparse
import threading
import uuid
import re
import unicodedata
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from PIL import Image
from tqdm import tqdm


# ---------- Thread-local HTTP session ----------
_thread_local = threading.local()

def get_session() -> requests.Session:
    s = getattr(_thread_local, "session", None)
    if s is None:
        s = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(pool_connections=128, pool_maxsize=128, max_retries=retries)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        _thread_local.session = s
    return s


# ---------- IO helpers ----------
def fetch(url: str, out_file: Path) -> None:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:129.0) Gecko/20100101 Firefox/129.0",
        "Referer": "https://www.inaturalist.org/",
    }
    r = get_session().get(url, headers=headers, timeout=10)
    r.raise_for_status()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "wb") as f:
        f.write(r.content)


def convert_to_jpg(src: Path, dst_atomic: Path) -> None:
    with Image.open(src) as im:
        if im.mode in ("RGBA", "P"):
            im = im.convert("RGB")
        # пишем в .part, чтобы затем атомарно заменить
        dst_atomic.parent.mkdir(parents=True, exist_ok=True)
        im.save(dst_atomic, "JPEG", quality=95)


def read_csv(path_to_csv: Path) -> list[tuple[str, str]]:
    data = []
    with open(path_to_csv, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)  # пропускаем заголовок если есть
        for row in reader:
            if len(row) >= 2 and row[0] and row[1]:
                data.append((row[0], row[1]))
    return data


# ---------- Naming ----------
_slug_rx = re.compile(r"[^a-z0-9_-]+")

def slugify(text: str) -> str:
    # нормализуем юникод, приводим к нижнему, оставляем a-z0-9_-
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = text.replace(" ", "_")
    text = _slug_rx.sub("", text)
    return text or "unknown"


# ---------- Thread-safe class indexer ----------
class ClassIndexer:
    def __init__(self) -> None:
        self._counts: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def next(self, cls: str) -> int:
        with self._lock:
            self._counts[cls] += 1
            return self._counts[cls]


def process_item(
    num: str,
    cls_raw: str,
    output_dir: Path,
    fallback_exts: list[str],
    indexer: ClassIndexer,
) -> bool:
    cls = slugify(cls_raw)
    idx = indexer.next(cls)

    final_path = output_dir / f"{cls}_{idx}.jpg"
    atomic_part = output_dir / f".{cls}_{idx}.jpg.part"

    # уникальный tmp для загрузки исходника (во избежание гонок)
    def tmp_dl(ext: str) -> Path:
        return output_dir / f"tmp_{num}_{uuid.uuid4().hex}.{ext}"

    try:
        for ext in fallback_exts:
            tmp_src = tmp_dl(ext)
            try:
                url = f"https://inaturalist-open-data.s3.amazonaws.com/photos/{num}/medium.{ext}"
                fetch(url, tmp_src)
                convert_to_jpg(tmp_src, atomic_part)
                # атомарная замена итогового файла
                atomic_part.replace(final_path)
                return True
            except requests.exceptions.HTTPError:
                # формат не найден — пробуем следующий
                pass
            except Exception:
                # иные ошибки — тоже пробуем следующий формат
                pass
            finally:
                try:
                    tmp_src.unlink(missing_ok=True)
                except Exception:
                    pass
        return False
    finally:
        try:
            atomic_part.unlink(missing_ok=True)
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="Dataset downloader (thread-safe)")
    parser.add_argument("-i", required=True, type=Path, help="Path to the input .csv file")
    parser.add_argument("-o", required=True, type=Path, help="Path to the output folder to store images")
    parser.add_argument("--workers", type=int, default=16, help="Number of parallel workers")
    args = parser.parse_args()

    output_dir: Path = args.o
    output_dir.mkdir(parents=True, exist_ok=True)

    data = read_csv(args.i)
    fallback_exts = ["jpeg", "jpg", "png", "webp"]

    indexer = ClassIndexer()

    tasks = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for image_url, cls in data:
            # аккуратно достаём ID фото; ожидаем .../photos/<id>/...
            parts = image_url.strip("/").split("/")
            try:
                idx_photos = parts.index("photos")
                num = parts[idx_photos + 1]
            except (ValueError, IndexError):
                # если URL нестандартный — пропускаем
                continue

            tasks.append(
                executor.submit(
                    process_item,
                    num,
                    cls,
                    output_dir,
                    fallback_exts,
                    indexer,
                )
            )

        ok, fail = 0, 0
        for fut in tqdm(as_completed(tasks), total=len(tasks)):
            try:
                if fut.result():
                    ok += 1
                else:
                    fail += 1
            except Exception:
                fail += 1

    print(f"Done. Saved: {ok}, failed: {fail}")


if __name__ == "__main__":
    main()
