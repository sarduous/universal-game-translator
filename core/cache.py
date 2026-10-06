import os
import hashlib
import sqlite3
import logging
from pathlib import Path
from typing import Optional, Dict, List, Union

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CACHE_PATH = PROJECT_ROOT / "data" / "translations.db"


class TranslationCache:
    """
    Tekrar eden diyaloglar için SHA-256 tabanlı kalıcı SQLite önbellekleme sınıfı.
    Veritabanı PROJECT_ROOT / "data" / "translations.db" dizininde kalıcı olarak saklanır.
    Her kayıt sonrasında anında commit yapılarak veri kaybı önlenir.
    """

    def __init__(self, db_path: Optional[Union[str, Path]] = None):
        if db_path is None or str(db_path) in ("cache.db", "translation_cache.db", "translations.db"):
            self.db_path = DEFAULT_CACHE_PATH
        else:
            self.db_path = Path(db_path)

        # data/ klasörünü kesin olarak oluştur
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self._init_db()

    def _init_db(self):
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS translations (
                    text_hash TEXT PRIMARY KEY,
                    source_text TEXT NOT NULL,
                    translation TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_hash ON translations(text_hash)")
        self.conn.commit()

    @staticmethod
    def _compute_hash(text: str) -> str:
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    def get(self, source_text: str) -> Optional[str]:
        """
        Kaynak metin daha önce çevrilmişse çevirisini döndürür, aksi halde None döner.
        """
        if not source_text:
            return source_text

        text_hash = self._compute_hash(source_text)
        cursor = self.conn.cursor()
        cursor.execute("SELECT translation FROM translations WHERE text_hash = ?", (text_hash,))
        row = cursor.fetchone()
        return row[0] if row else None

    def get_batch(self, source_texts: List[str]) -> Dict[str, str]:
        """
        Liste halinde verilen metinlerin önbellekte olanlarını dict olarak döner.
        """
        result = {}
        for text in source_texts:
            cached = self.get(text)
            if cached is not None:
                result[text] = cached
        if result:
            msg = f"[INFO] [CACHE HIT] {len(result)} satır önbellekten okundu (0 token)"
            print(msg)
            logger.info(msg)
        return result

    def set(self, source_text: str, translation: str):
        """
        Metin ve çevirisini veritabanına kaydeder/günceller ve anında commit eder.
        """
        if not source_text:
            return

        text_hash = self._compute_hash(source_text)
        with self.conn:
            self.conn.execute("""
                INSERT INTO translations (text_hash, source_text, translation)
                VALUES (?, ?, ?)
                ON CONFLICT(text_hash) DO UPDATE SET translation = excluded.translation
            """, (text_hash, source_text, translation))
        self.conn.commit()

    def set_batch(self, pairs: Dict[str, str]):
        """
        Çoklu metin-çeviri çiftlerini toplu halde kaydeder ve anında commit eder.
        """
        with self.conn:
            for source, trans in pairs.items():
                if source:
                    text_hash = self._compute_hash(source)
                    self.conn.execute("""
                        INSERT INTO translations (text_hash, source_text, translation)
                        VALUES (?, ?, ?)
                        ON CONFLICT(text_hash) DO UPDATE SET translation = excluded.translation
                    """, (text_hash, source, trans))
        self.conn.commit()

    def clear(self):
        """
        Tüm önbelleği temizler.
        """
        with self.conn:
            self.conn.execute("DELETE FROM translations")
        self.conn.commit()

    def count(self) -> int:
        """
        Önbellekte kaydedilmiş toplam çeviri sayısını döner.
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM translations")
        return cursor.fetchone()[0]

    def close(self):
        if self.conn:
            try:
                self.conn.commit()
            except Exception:
                pass
            self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
